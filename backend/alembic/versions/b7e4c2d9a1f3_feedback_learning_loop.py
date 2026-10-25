"""feedback learning loop: learned answers, answer feedback, chunk reward

Revision ID: b7e4c2d9a1f3
Revises: f3b8c1a9d2e7
Create Date: 2026-10-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = 'b7e4c2d9a1f3'
down_revision: Union[str, None] = 'f3b8c1a9d2e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tenant_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} "
        "USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)"
    )


def upgrade() -> None:
    op.add_column(
        'knowledge_chunks',
        sa.Column('feedback_score', sa.Float(), nullable=False, server_default='0'),
    )

    op.create_table('learned_answers',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.UUID(), nullable=False),
    sa.Column('question', sa.String(), nullable=False),
    sa.Column('question_norm', sa.String(), nullable=False),
    sa.Column('question_embedding', Vector(768), nullable=True),
    sa.Column('answer', sa.String(), nullable=True),
    sa.Column('citations', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('origin', sa.String(length=20), nullable=False),
    sa.Column('positive', sa.Integer(), nullable=False),
    sa.Column('negative', sa.Integer(), nullable=False),
    sa.Column('uses', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('agent_id', 'question_norm', name='uq_learned_answers_agent_question'),
    )

    op.create_table('answer_feedback',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.UUID(), nullable=False),
    sa.Column('message_id', sa.UUID(), nullable=True),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('question', sa.String(), nullable=False),
    sa.Column('answer', sa.String(), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('helpful', sa.Boolean(), nullable=False),
    sa.Column('correction', sa.String(), nullable=True),
    sa.Column('learned_answer_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_answer_feedback_agent_created', 'answer_feedback', ['agent_id', 'created_at'])

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON learned_answers TO app_user")
    # Append-only, same as conversation_messages: the reward log is evidence.
    op.execute("GRANT SELECT, INSERT ON answer_feedback TO app_user")
    _tenant_rls('learned_answers')
    _tenant_rls('answer_feedback')


def downgrade() -> None:
    op.drop_index('ix_answer_feedback_agent_created', table_name='answer_feedback')
    op.drop_table('answer_feedback')
    op.drop_table('learned_answers')
    op.drop_column('knowledge_chunks', 'feedback_score')
