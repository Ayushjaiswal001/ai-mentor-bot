"""Allow multiple goals per day.

The original schema enforced one goal per (user_id, goal_date) via
uq_daily_goal_user_date. In practice users wanted to track 2-3 parallel
threads on the same day (ship X + study Y), and the upsert silently
overwrote earlier goals — confusing and lossy. Dropping the constraint
makes goals append-only per day; status is tracked per row.

Revision ID: 20260610_0007
Revises: 20260610_0006
Create Date: 2026-06-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260610_0007"
down_revision: str | None = "20260610_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_daily_goal_user_date", "daily_goals", type_="unique"
    )
    op.create_index(
        "ix_daily_goals_user_date", "daily_goals", ["user_id", "goal_date"]
    )


def downgrade() -> None:
    op.drop_index("ix_daily_goals_user_date", table_name="daily_goals")
    op.create_unique_constraint(
        "uq_daily_goal_user_date", "daily_goals", ["user_id", "goal_date"]
    )
