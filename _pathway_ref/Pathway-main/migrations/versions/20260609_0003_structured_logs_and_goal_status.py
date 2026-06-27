"""Structured learning logs and goal completion status.

Revision ID: 20260609_0003
Revises: 20260607_0002
Create Date: 2026-06-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260609_0003"
down_revision: str | None = "20260607_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "learning_logs", sa.Column("built", sa.Text(), nullable=True)
    )
    op.add_column(
        "learning_logs", sa.Column("topic", sa.String(length=120), nullable=True)
    )
    op.add_column(
        "learning_logs",
        sa.Column("difficulty", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "learning_logs", sa.Column("tradeoff", sa.Text(), nullable=True)
    )
    op.add_column(
        "learning_logs", sa.Column("interview_story", sa.Text(), nullable=True)
    )
    op.add_column(
        "learning_logs",
        sa.Column(
            "extraction_status",
            sa.String(length=24),
            nullable=False,
            server_default="pending",
        ),
    )
    op.create_index(
        "ix_learning_logs_topic", "learning_logs", ["topic"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_learning_logs_topic", table_name="learning_logs")
    op.drop_column("learning_logs", "extraction_status")
    op.drop_column("learning_logs", "interview_story")
    op.drop_column("learning_logs", "tradeoff")
    op.drop_column("learning_logs", "difficulty")
    op.drop_column("learning_logs", "topic")
    op.drop_column("learning_logs", "built")
