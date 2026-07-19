import uuid

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
        )
    )
