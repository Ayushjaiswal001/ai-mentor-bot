"""Topic mastery for spaced-repetition re-quizzes.

Revision ID: 20260609_0004
Revises: 20260609_0003
Create Date: 2026-06-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260609_0004"
down_revision: str | None = "20260609_0003"
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
        "topic_mastery",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("topic", sa.String(length=120), nullable=False),
        sa.Column(
            "level", sa.String(length=32), nullable=False, server_default="exposure"
        ),
        sa.Column("last_quizzed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quiz_count", sa.Integer(), nullable=False, server_default="0"),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_topic_mastery_user_id_users"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_topic_mastery"),
        sa.UniqueConstraint("user_id", "topic", name="uq_topic_mastery_user_topic"),
    )
    op.create_index(
        "ix_topic_mastery_user_id", "topic_mastery", ["user_id"], unique=False
    )
    op.create_index(
        "ix_topic_mastery_user_due",
        "topic_mastery",
        ["user_id", "next_due_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_topic_mastery_user_due", table_name="topic_mastery")
    op.drop_index("ix_topic_mastery_user_id", table_name="topic_mastery")
    op.drop_table("topic_mastery")
