import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.knowledge import EMBEDDING_DIM


class LearnedAnswer(Base):
    """A question the agent has been taught the answer to by reviewer
    feedback (see app.rag.learning). Checked before the LLM on every turn,
    so a corrected answer is both right AND instant the next time anyone
    asks the same thing.

    answer=None is a deliberate "veto": a fast answer for this question was
    marked wrong and no better one could be found in the documents, so the
    question must always take the full LLM/tool path instead."""

    __tablename__ = "learned_answers"
    __table_args__ = (UniqueConstraint("agent_id", "question_norm", name="uq_learned_answers_agent_question"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    question: Mapped[str] = mapped_column(String, nullable=False)
    # app.fastpath.textnorm.normalize(question) -- the exact-match key.
    question_norm: Mapped[str] = mapped_column(String, nullable=False)
    # Null if the embedding service was down when this was learned; the row
    # then still works for exact matches, just not near-duplicate ones.
    question_embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    answer: Mapped[str | None] = mapped_column(String, nullable=True)
    citations: Mapped[list | None] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=True)
    # "correction" (written by a reviewer), "regenerated" (re-answered from
    # the documents after a thumbs-down), "confirmed" (a thumbs-up on the
    # agent's own grounded answer), "unanswered" (a veto -- answer is None).
    origin: Mapped[str] = mapped_column(String(20), nullable=False)
    positive: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    negative: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))


class AnswerFeedback(Base):
    """One thumbs-up/down on an assistant reply -- the raw reward log behind
    LearnedAnswer and KnowledgeChunk.feedback_score. Append-only, same
    reasoning as ConversationMessage: it's the evidence trail for why the
    agent's behaviour changed."""

    __tablename__ = "answer_feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    # No FK: conversation_messages is append-only and this log should
    # outlive any one transcript's retention.
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    question: Mapped[str] = mapped_column(String, nullable=False)
    answer: Mapped[str] = mapped_column(String, nullable=False)
    # The rated reply's ConversationMessage.message_type: "instant", "learned" or "text".
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    helpful: Mapped[bool] = mapped_column(Boolean, nullable=False)
    correction: Mapped[str | None] = mapped_column(String, nullable=True)
    learned_answer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
