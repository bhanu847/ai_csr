"""password reset tokens

Revision ID: f3b8c1a9d2e7
Revises: a1f2b3c4d5e6
Create Date: 2026-08-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f3b8c1a9d2e7'
down_revision: Union[str, None] = 'a1f2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Only the SHA-256 hash of the reset token is stored, never the token
    # itself — same reason passwords are hashed, not stored plain: a DB
    # leak shouldn't hand out usable credentials.
    op.add_column('users', sa.Column('password_reset_token_hash', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('password_reset_expires_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'password_reset_expires_at')
    op.drop_column('users', 'password_reset_token_hash')
