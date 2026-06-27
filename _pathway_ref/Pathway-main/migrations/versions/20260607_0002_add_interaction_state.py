"""Add per-user interaction state for Telegram flows.

Revision ID: 20260607_0002
Revises: 20260606_0001
Create Date: 2026-06-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260607_0002"
down_revision: str | None = "20260606_0001"
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
        "user_interaction_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state_type", sa.String(length=64), nullable=False),
        sa.Column(
            "state_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_user_interaction_states_user_id_users"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_interaction_states"),
        sa.UniqueConstraint("user_id", name="uq_user_interaction_states_user_id"),
    )
    op.create_index(
        "ix_user_interaction_states_user_id",
        "user_interaction_states",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_user_interaction_states_state_type",
        "user_interaction_states",
        ["state_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_interaction_states_state_type", table_name="user_interaction_states"
    )
    op.drop_index(
        "ix_user_interaction_states_user_id", table_name="user_interaction_states"
    )
    op.drop_table("user_interaction_states")
