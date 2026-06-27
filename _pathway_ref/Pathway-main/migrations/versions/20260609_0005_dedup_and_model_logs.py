"""Webhook deduplication and model call logging.

Revision ID: 20260609_0005
Revises: 20260609_0004
Create Date: 2026-06-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260609_0005"
down_revision: str | None = "20260609_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "processed_updates",
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "source", "external_id", name="pk_processed_updates"
        ),
    )
    op.create_index(
        "ix_processed_updates_processed_at",
        "processed_updates",
        ["processed_at"],
        unique=False,
    )

    op.create_table(
        "model_call_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column(
            "success", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "latency_ms", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_model_call_logs"),
    )
    op.create_index(
        "ix_model_call_logs_created",
        "model_call_logs",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_model_call_logs_provider",
        "model_call_logs",
        ["provider"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_model_call_logs_provider", table_name="model_call_logs")
    op.drop_index("ix_model_call_logs_created", table_name="model_call_logs")
    op.drop_table("model_call_logs")
    op.drop_index(
        "ix_processed_updates_processed_at", table_name="processed_updates"
    )
    op.drop_table("processed_updates")
