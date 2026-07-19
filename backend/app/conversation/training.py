import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.confidence_service import LOW_THRESHOLD
from app.llm.client import json_completion
from app.models.call import Call, ResolutionStatus
from app.models.conversation_message import ConversationMessage, MessageRole
from app.models.training_insight import InsightCategory, TrainingInsight

logger = logging.getLogger("training")

SIGNAL_LIMIT = 40  # per signal type, most recent first — keeps the prompt bounded

TRAINING_PROMPT = """You are analyzing patterns across many customer service calls handled \
by an AI agent, looking for systemic issues worth fixing — not one-off incidents. \
You'll see three kinds of signals:

- LOW CONFIDENCE: topics where the AI could not find a reliable answer in its knowledge base
- ESCALATED: calls handed off to a human, with their topic
- LOW QA SCORE: calls a quality reviewer flagged, with the reviewer's notes

Respond with ONLY a JSON object:
{
  "insights": [
    {
      "category": "missing_knowledge" | "prompt_improvement" | "workflow_improvement",
      "title": "short actionable headline, e.g. 'Upload specialty medication policy'",
      "description": "1-2 sentences: the pattern, and what evidence supports it",
      "supporting_call_count": integer - how many of the provided examples relate to this insight
    }
  ]
}

Use "missing_knowledge" when the fix is uploading/updating a document. Use "prompt_improvement" \
when the fix is how the AI behaves (tone, missed steps, guardrails). Use "workflow_improvement" \
when the fix is a process/tool gap. Only report a theme with at least 2 supporting examples. \
Return an empty list if nothing rises to a real pattern — don't invent themes to fill the list."""


def _gather_signals(db: Session, tenant_id: uuid.UUID) -> str:
    low_confidence = (
        db.execute(
            select(ConversationMessage.content, Call.intent)
            .join(Call, Call.id == ConversationMessage.call_id)
            .where(
                ConversationMessage.tenant_id == tenant_id,
                ConversationMessage.role == MessageRole.ASSISTANT,
                ConversationMessage.confidence_score.is_not(None),
                ConversationMessage.confidence_score < LOW_THRESHOLD,
            )
            .order_by(ConversationMessage.timestamp.desc())
            .limit(SIGNAL_LIMIT)
        )
        .all()
    )
    escalated = (
        db.execute(
            select(Call.intent, Call.summary)
            .where(Call.tenant_id == tenant_id, Call.resolution_status == ResolutionStatus.ESCALATED)
            .order_by(Call.started_at.desc())
            .limit(SIGNAL_LIMIT)
        )
        .all()
    )
    low_qa = (
        db.execute(
            select(Call.intent, Call.qa_notes)
            .where(
                Call.tenant_id == tenant_id,
                Call.qa_notes.is_not(None),
                (Call.accuracy_score < LOW_THRESHOLD)
                | (Call.compliance_score < LOW_THRESHOLD)
                | (Call.empathy_score < LOW_THRESHOLD),
            )
            .order_by(Call.started_at.desc())
            .limit(SIGNAL_LIMIT)
        )
        .all()
    )

    lines: list[str] = []
    for content, intent in low_confidence:
        lines.append(f"LOW CONFIDENCE — topic: {intent or 'unknown'} — reply: {content[:200]}")
    for intent, summary in escalated:
        lines.append(f"ESCALATED — topic: {intent or 'unknown'} — {(summary or '')[:200]}")
    for intent, notes in low_qa:
        lines.append(f"LOW QA SCORE — topic: {intent or 'unknown'} — reviewer notes: {(notes or '')[:200]}")

    return "\n".join(lines)


def analyze_and_store_insights(db: Session, tenant_id: uuid.UUID) -> list[TrainingInsight]:
    """Best-effort batch analysis, triggered on demand (no scheduler in
    this codebase) rather than per-call — unlike summary/quality scoring,
    this needs many calls' worth of signal before a pattern means anything.
    Returns the newly created insights; raises on LLM failure so the API
    layer can surface it (unlike the per-call analyzers, there's a human
    waiting on this one, not a webhook that must not block)."""
    signals = _gather_signals(db, tenant_id)
    if not signals.strip():
        return []

    data = json_completion(
        [
            {"role": "system", "content": TRAINING_PROMPT},
            {"role": "user", "content": signals},
        ],
        max_tokens=1000,
    )

    created: list[TrainingInsight] = []
    for item in data.get("insights", []):
        try:
            category = InsightCategory(item["category"])
        except (KeyError, ValueError):
            logger.warning("Skipping training insight with unrecognized category: %r", item.get("category"))
            continue

        insight = TrainingInsight(
            tenant_id=tenant_id,
            category=category,
            title=str(item.get("title", ""))[:255],
            description=str(item.get("description", ""))[:2000],
            supporting_call_count=int(item["supporting_call_count"])
            if isinstance(item.get("supporting_call_count"), int | float)
            else 0,
        )
        db.add(insight)
        created.append(insight)

    db.flush()
    return created
