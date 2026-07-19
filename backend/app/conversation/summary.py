import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.client import json_completion
from app.models.call import Call
from app.models.conversation_message import ConversationMessage, MessageRole

logger = logging.getLogger("summary")

SUMMARY_PROMPT = """You are reviewing a completed customer service phone call transcript. \
Respond with ONLY a JSON object with these exact keys:

{
  "customer_issue": "one sentence describing what the customer called about",
  "resolution": "one sentence describing how it was resolved, or 'Not resolved' if it wasn't",
  "actions_performed": ["short action phrase", ...],
  "follow_up_required": "short description of follow-up needed, or null if none",
  "customer_sentiment": "positive" | "neutral" | "negative" | "frustrated",
  "ai_confidence": integer from 0 to 100 - how confident you are the AI handled this call correctly and completely
}

Base every field strictly on the transcript. Do not invent information that isn't in it."""


def _format_transcript(messages: list[ConversationMessage]) -> str:
    lines = []
    for m in messages:
        if m.role == MessageRole.TOOL:
            continue
        speaker = "Customer" if m.role == MessageRole.CUSTOMER else "Assistant"
        lines.append(f"{speaker}: {m.content}")
    return "\n".join(lines)


def _format_summary_text(data: dict) -> str:
    actions = data.get("actions_performed") or []
    actions_text = "; ".join(str(a) for a in actions) if actions else "None"
    follow_up = data.get("follow_up_required") or "None"
    return (
        f"Customer Issue: {data.get('customer_issue', 'Unknown')}\n"
        f"Resolution: {data.get('resolution', 'Unknown')}\n"
        f"Actions Performed: {actions_text}\n"
        f"Follow-up Required: {follow_up}"
    )


def generate_and_store_summary(db: Session, call_id: uuid.UUID) -> None:
    """Summarize a completed call's transcript with the LLM and store the
    result on the Call row. Best-effort: any failure is logged and
    swallowed so a flaky LLM call never breaks the call-status webhook
    that triggers it."""
    messages = (
        db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.call_id == call_id)
            .order_by(ConversationMessage.timestamp)
        )
        .scalars()
        .all()
    )

    transcript = _format_transcript(messages)
    if not transcript.strip():
        return

    try:
        data = json_completion(
            [
                {"role": "system", "content": SUMMARY_PROMPT},
                {"role": "user", "content": transcript},
            ]
        )
    except Exception:
        logger.exception("Call summary generation failed for call %s", call_id)
        return

    call = db.execute(select(Call).where(Call.id == call_id)).scalar_one_or_none()
    if call is None:
        return

    call.intent = (data.get("customer_issue") or "").strip()[:255] or None
    call.sentiment = (data.get("customer_sentiment") or "").strip()[:50] or None
    ai_confidence = data.get("ai_confidence")
    call.confidence_score = float(ai_confidence) if isinstance(ai_confidence, int | float) else None
    call.summary = _format_summary_text(data)
