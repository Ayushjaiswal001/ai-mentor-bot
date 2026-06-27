"""Create the initial PathwayAI schema.

Revision ID: 20260606_0001
Revises:
Create Date: 2026-06-06
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260606_0001"
down_revision: str | None = None
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
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("telegram_chat_id", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("target_role", sa.String(length=160), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint(
            "telegram_chat_id", name="uq_users_telegram_chat_id"
        ),
    )
    op.create_table(
        "workflow_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("workflow_type", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column(
            "result", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_runs"),
    )
    op.create_index(
        "ix_workflow_runs_request_id", "workflow_runs", ["request_id"], unique=True
    )
    op.create_index(
        "ix_workflow_runs_workflow_type",
        "workflow_runs",
        ["workflow_type"],
        unique=False,
    )
    op.create_table(
        "sync_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("records_processed", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_sync_runs"),
    )
    op.create_index("ix_sync_runs_source", "sync_runs", ["source"], unique=False)
    op.create_table(
        "activity_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("external_ref", sa.String(length=255), nullable=False),
        sa.Column(
            "payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_activity_events_user_id_users"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_activity_events"),
        sa.UniqueConstraint(
            "source", "external_ref", name="uq_activity_source_ref"
        ),
    )
    op.create_index(
        "ix_activity_events_event_type",
        "activity_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        "ix_activity_events_source", "activity_events", ["source"], unique=False
    )
    op.create_index(
        "ix_activity_events_user_id", "activity_events", ["user_id"], unique=False
    )
    op.create_index(
        "ix_activity_events_occurred_at",
        "activity_events",
        ["occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_activity_user_occurred",
        "activity_events",
        ["user_id", "occurred_at"],
        unique=False,
    )
    op.create_table(
        "learning_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "topics", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_learning_logs_user_id_users"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_learning_logs"),
    )
    op.create_index(
        "ix_learning_logs_user_id", "learning_logs", ["user_id"], unique=False
    )
    op.create_index(
        "ix_learning_logs_user_created",
        "learning_logs",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "daily_goals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("goal_date", sa.Date(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_daily_goals_user_id_users"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_daily_goals"),
        sa.UniqueConstraint(
            "user_id", "goal_date", name="uq_daily_goal_user_date"
        ),
    )
    op.create_index(
        "ix_daily_goals_goal_date", "daily_goals", ["goal_date"], unique=False
    )
    op.create_index(
        "ix_daily_goals_user_id", "daily_goals", ["user_id"], unique=False
    )
    op.create_table(
        "conversation_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("external_message_id", sa.String(length=128), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("message_type", sa.String(length=40), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_conversation_messages_user_id_users",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_conversation_messages"),
        sa.UniqueConstraint(
            "source",
            "external_message_id",
            name="uq_message_source_external",
        ),
    )
    op.create_index(
        "ix_conversation_messages_user_id",
        "conversation_messages",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_message_user_created",
        "conversation_messages",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "memory_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("memory_type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "evidence_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_memory_summaries_user_id_users"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_memory_summaries"),
    )
    op.create_index(
        "ix_memory_summaries_memory_type",
        "memory_summaries",
        ["memory_type"],
        unique=False,
    )
    op.create_index(
        "ix_memory_summaries_user_id",
        "memory_summaries",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_memory_user_type_created",
        "memory_summaries",
        ["user_id", "memory_type", "created_at"],
        unique=False,
    )
    op.create_table(
        "readiness_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_role", sa.String(length=160), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("score_version", sa.String(length=32), nullable=False),
        sa.Column(
            "subscores", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "gap_analysis", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_readiness_scores_user_id_users"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_readiness_scores"),
    )
    op.create_index(
        "ix_readiness_scores_user_id",
        "readiness_scores",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "weekly_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "priorities", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_weekly_plans_user_id_users"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_weekly_plans"),
    )
    op.create_index(
        "ix_weekly_plans_user_id", "weekly_plans", ["user_id"], unique=False
    )
    op.create_index(
        "ix_weekly_plans_week_start",
        "weekly_plans",
        ["week_start"],
        unique=False,
    )
    op.create_table(
        "outbound_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("message_type", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("provider_message_id", sa.String(length=128), nullable=True),
        sa.Column(
            "workflow_run_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("delivered", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_outbound_messages_user_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
            name="fk_outbound_messages_workflow_run_id_workflow_runs",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_outbound_messages"),
    )
    op.create_index(
        "ix_outbound_messages_message_type",
        "outbound_messages",
        ["message_type"],
        unique=False,
    )
    op.create_index(
        "ix_outbound_messages_user_id",
        "outbound_messages",
        ["user_id"],
        unique=False,
    )
    op.execute(
        """
        CREATE INDEX ix_learning_logs_content_fts
        ON learning_logs USING GIN (to_tsvector('english', content))
        """
    )
    op.execute(
        """
        CREATE INDEX ix_memory_summaries_content_fts
        ON memory_summaries USING GIN (to_tsvector('english', content))
        """
    )


def downgrade() -> None:
    op.drop_table("outbound_messages")
    op.drop_table("weekly_plans")
    op.drop_table("readiness_scores")
    op.drop_table("memory_summaries")
    op.drop_table("conversation_messages")
    op.drop_table("daily_goals")
    op.drop_table("learning_logs")
    op.drop_table("activity_events")
    op.drop_table("sync_runs")
    op.drop_table("workflow_runs")
    op.drop_table("users")
