"""pgvector embeddings for semantic search across logs and memory.

Revision ID: 20260610_0006
Revises: 20260609_0005
Create Date: 2026-06-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "20260610_0006"
down_revision: str | None = "20260609_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIMENSIONS = 384


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column(
        "learning_logs",
        sa.Column("embedding", Vector(EMBEDDING_DIMENSIONS), nullable=True),
    )
    op.add_column(
        "memory_summaries",
        sa.Column("embedding", Vector(EMBEDDING_DIMENSIONS), nullable=True),
    )
    # ivfflat indexes are usable immediately; recall improves as rows
    # accumulate. lists=100 is the pgvector default guidance for small sets.
    op.execute(
        "CREATE INDEX ix_learning_logs_embedding ON learning_logs "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )
    op.execute(
        "CREATE INDEX ix_memory_summaries_embedding ON memory_summaries "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_memory_summaries_embedding")
    op.execute("DROP INDEX IF EXISTS ix_learning_logs_embedding")
    op.drop_column("memory_summaries", "embedding")
    op.drop_column("learning_logs", "embedding")
