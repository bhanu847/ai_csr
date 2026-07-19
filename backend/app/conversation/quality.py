import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.client import json_completion
from app.models.call import Call
from app.models.conversation_message import ConversationMessage, MessageRole
from app.models.tool_execution_log import ToolExecutionLog

logger = logging.getLogger("quality")

QA_PROMPT = """You are a contact-center QA analyst reviewing a completed AI-handled \
customer service call, transcript and tool calls included. Score it honestly — \
most calls should NOT all be 100s. Respond with ONLY a JSON object with these exact keys:

{
  "accuracy_score": integer 0-100 - were the AI's factual claims correct and properly grounded in retrieved knowledge, not invented?,
  "compliance_score": integer 0-100 - did the AI verify identity before discussing claims/benefits, avoid giving medical diagnoses, and follow escalation rules?,
  "empathy_score": integer 0-100 - did the AI acknowledge the caller's situation/frustration and communicate warmly, not just transactionally?,
  "resolution_score": integer 0-100 - was the caller's actual issue resolved by the end of the call?,
  "notes": "one or two sentences explaining the scores, calling out anything specific"
}

Base every score strictly on the transcript. If nothing warrants a deduction, say so — but don't inflate scores by default."""


@dataclass
class _TranscriptEntry:
    timestamp: datetime
    text: str


def _format_full_transcript(messages: list[ConversationMessage], tool_logs: list[ToolExecutionLog]) -> str:
    entries = [
        _TranscriptEntry(
            timestamp=m.timestamp,
            text=f"{'Customer' if m.role == MessageRole.CUSTOMER else 'Assistant'}: {m.content}",
        )
        for m in messages
        if m.role in (MessageRole.CUSTOMER, MessageRole.ASSISTANT)
    ]
    entries += [
        _TranscriptEntry(timestamp=t.created_at, text=f"[Tool call: {t.tool_name}({t.input}) -> {t.output}]")
        for t in tool_logs
    ]
    entries.sort(key=lambda e: e.timestamp)
    return "\n".join(e.text for e in entries)


def generate_and_store_quality_score(db: Session, call_id: uuid.UUID) -> None:
    """Independent QA review of a completed call — best-effort, same
    isolation pattern as app.conversation.summary: failures are logged and
    swallowed, never allowed to break call teardown."""
    messages = (
        db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.call_id == call_id)
            .order_by(ConversationMessage.timestamp)
        )
        .scalars()
        .all()
    )
    tool_logs = (
        db.execute(
            select(ToolExecutionLog)
            .where(ToolExecutionLog.call_id == call_id)
            .order_by(ToolExecutionLog.created_at)
        )
        .scalars()
        .all()
    )

    transcript = _format_full_transcript(messages, tool_logs)
    if not transcript.strip():
        return

    try:
        data = json_completion(
            [
                {"role": "system", "content": QA_PROMPT},
                {"role": "user", "content": transcript},
            ]
        )
    except Exception:
        logger.exception("QA scoring failed for call %s", call_id)
        return

    call = db.execute(select(Call).where(Call.id == call_id)).scalar_one_or_none()
    if call is None:
        return

    def _score(key: str) -> float | None:
        value = data.get(key)
        return float(value) if isinstance(value, int | float) else None

    call.accuracy_score = _score("accuracy_score")
    call.compliance_score = _score("compliance_score")
    call.empathy_score = _score("empathy_score")
    call.resolution_score = _score("resolution_score")
    call.qa_notes = (data.get("notes") or "").strip()[:2000] or None
