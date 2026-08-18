"""open-source AI stack: embedding dim 1536->768, Piper voice names

Revision ID: a1f2b3c4d5e6
Revises: 509824895eeb
Create Date: 2026-08-07 00:00:00.000000

Swaps Azure OpenAI/Speech for self-hosted open-source models (Ollama LLM +
nomic-embed-text, faster-whisper STT, Piper TTS). Two consequences that
need a migration rather than just a code change:

1. nomic-embed-text produces 768-dim vectors, not Azure's 1536 — the
   pgvector column type is dimension-locked, so existing knowledge_chunks
   (embedded with the old model) can't be reinterpreted at the new
   dimension. They're deleted here; documents must be re-uploaded so
   Agent Studio re-parses and re-embeds them with the new model.
2. agents.voice stored Azure neural voice names (e.g. "en-IN-NeerjaNeural")
   — remapped to the closest available open-source Piper voice.
"""
from typing import Sequence, Union

from alembic import op
import pgvector.sqlalchemy


revision: str = 'a1f2b3c4d5e6'
down_revision: Union[str, None] = '509824895eeb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_VOICE_MAP = {
    'en-IN-NeerjaNeural': 'en_US-amy-medium',
    'en-US-JennyNeural': 'en_US-amy-medium',
    'en-US-GuyNeural': 'en_US-ryan-medium',
    'hi-IN-SwaraNeural': 'hi_IN-rohan-medium',
}


def upgrade() -> None:
    # Old (Azure, 1536-dim) embeddings are incompatible with the new
    # (nomic-embed-text, 768-dim) model — nothing to migrate them to.
    op.execute("DELETE FROM knowledge_chunks")
    op.execute("DELETE FROM knowledge_documents")

    op.alter_column(
        'knowledge_chunks', 'embedding',
        type_=pgvector.sqlalchemy.vector.VECTOR(dim=768),
        existing_nullable=False,
    )

    op.alter_column('agents', 'voice', server_default='en_US-amy-medium')
    for old_voice, new_voice in _VOICE_MAP.items():
        op.execute(
            f"UPDATE agents SET voice = '{new_voice}' WHERE voice = '{old_voice}'"
        )


def downgrade() -> None:
    op.alter_column('agents', 'voice', server_default='en-IN-NeerjaNeural')
    for old_voice, new_voice in _VOICE_MAP.items():
        op.execute(
            f"UPDATE agents SET voice = '{old_voice}' WHERE voice = '{new_voice}'"
        )

    op.execute("DELETE FROM knowledge_chunks")
    op.alter_column(
        'knowledge_chunks', 'embedding',
        type_=pgvector.sqlalchemy.vector.VECTOR(dim=1536),
        existing_nullable=False,
    )
