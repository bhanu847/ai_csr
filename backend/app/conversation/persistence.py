import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.conversation_message import ConversationMessage, MessageRole
from app.models.tool_execution_log import ToolExecutionLog


def persist_message(
    db: Session,
    tenant_id: uuid.UUID,
    call_id: uuid.UUID,
    role: MessageRole,
    content: str,
    message_type: str = "text",
    confidence_score: float | None = None,
    citations: list[dict] | None = None,
) -> None:
    db.add(
        ConversationMessage(
            tenant_id=tenant_id,
            call_id=call_id,
            role=role,
            content=content,
            message_type=message_type,
            confidence_score=confidence_score,
            citations=citations,
            # Set explicitly rather than relying on the column default:
            # SQLAlchemy invokes Python-side defaults at flush time, not at
            # object construction, and a session with autoflush=False (see
            # app.db.session) batches inserts per-table — so two calls
            # persisting a message then a tool log within the same
            # transaction could get their default timestamps generated in
            # table-batch order instead of call order, scrambling
            # chronological ordering wherever messages and tool logs are
            # merged (transcript UI, QA transcript formatting).
            timestamp=datetime.now(timezone.utc),
        )
    )


def persist_tool_execution(
    db: Session,
    tenant_id: uuid.UUID,
    call_id: uuid.UUID,
    tool_name: str,
    input_data: dict,
    output: str,
    execution_time_ms: float,
) -> None:
    db.add(
        ToolExecutionLog(
            tenant_id=tenant_id,
            call_id=call_id,
            tool_name=tool_name,
            input=input_data,
            output=output,
            execution_time_ms=execution_time_ms,
            created_at=datetime.now(timezone.utc),  # see persist_message for why this is explicit
        )
    )
