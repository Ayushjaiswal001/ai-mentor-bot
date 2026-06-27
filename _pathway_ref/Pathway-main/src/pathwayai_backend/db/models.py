from datetime import UTC, date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from pathwayai_backend.db.base import Base, TimestampMixin


class WorkflowStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    telegram_chat_id: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    target_role: Mapped[str] = mapped_column(String(160))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ActivityEvent(Base, TimestampMixin):
    __tablename__ = "activity_events"
    __table_args__ = (
        UniqueConstraint("source", "external_ref", name="uq_activity_source_ref"),
        Index("ix_activity_user_occurred", "user_id", "occurred_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    source: Mapped[str] = mapped_column(String(40), index=True)
    external_ref: Mapped[str] = mapped_column(String(255))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class LearningLog(Base, TimestampMixin):
    __tablename__ = "learning_logs"
    __table_args__ = (
        Index("ix_learning_logs_user_created", "user_id", "created_at"),
        Index("ix_learning_logs_topic", "topic"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    source: Mapped[str] = mapped_column(String(40), default="telegram")
    content: Mapped[str] = mapped_column(Text)
    topics: Mapped[list[str]] = mapped_column(JSONB, default=list)
    built: Mapped[str | None] = mapped_column(Text, nullable=True)
    topic: Mapped[str | None] = mapped_column(String(120), nullable=True)
    difficulty: Mapped[str | None] = mapped_column(String(40), nullable=True)
    tradeoff: Mapped[str | None] = mapped_column(Text, nullable=True)
    interview_story: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_status: Mapped[str] = mapped_column(
        String(24), default="pending"
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(384), nullable=True
    )


class DailyGoal(Base, TimestampMixin):
    __tablename__ = "daily_goals"
    __table_args__ = (
        Index("ix_daily_goals_user_date", "user_id", "goal_date"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    goal_date: Mapped[date] = mapped_column(Date, index=True)
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="planned")


class ConversationMessage(Base, TimestampMixin):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        UniqueConstraint(
            "source", "external_message_id", name="uq_message_source_external"
        ),
        Index("ix_message_user_created", "user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    source: Mapped[str] = mapped_column(String(40), default="telegram")
    external_message_id: Mapped[str] = mapped_column(String(128))
    direction: Mapped[str] = mapped_column(String(16))
    message_type: Mapped[str] = mapped_column(String(40), default="text")
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class UserInteractionState(Base, TimestampMixin):
    __tablename__ = "user_interaction_states"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_interaction_states_user_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    state_type: Mapped[str] = mapped_column(String(64), index=True)
    state_data: Mapped[dict] = mapped_column(JSONB, default=dict)


class MemorySummary(Base, TimestampMixin):
    __tablename__ = "memory_summaries"
    __table_args__ = (
        Index("ix_memory_user_type_created", "user_id", "memory_type", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    memory_type: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    evidence_refs: Mapped[list[str]] = mapped_column(JSONB, default=list)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(384), nullable=True
    )


class OutboundMessage(Base, TimestampMixin):
    __tablename__ = "outbound_messages"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    channel: Mapped[str] = mapped_column(String(32), default="telegram")
    message_type: Mapped[str] = mapped_column(String(50), index=True)
    content: Mapped[str] = mapped_column(Text)
    provider_message_id: Mapped[str | None] = mapped_column(String(128))
    workflow_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("workflow_runs.id")
    )
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)


class SyncRun(Base, TimestampMixin):
    __tablename__ = "sync_runs"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    source: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(32))
    records_processed: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReadinessScore(Base, TimestampMixin):
    __tablename__ = "readiness_scores"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    target_role: Mapped[str] = mapped_column(String(160))
    overall_score: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    score_version: Mapped[str] = mapped_column(String(32))
    subscores: Mapped[dict] = mapped_column(JSONB)
    gap_analysis: Mapped[dict] = mapped_column(JSONB)
    evidence: Mapped[dict] = mapped_column(JSONB)


class ProcessedUpdate(Base):
    __tablename__ = "processed_updates"

    source: Mapped[str] = mapped_column(String(32), primary_key=True)
    external_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class ModelCallLog(Base, TimestampMixin):
    __tablename__ = "model_call_logs"
    __table_args__ = (
        Index("ix_model_call_logs_created", "created_at"),
        Index("ix_model_call_logs_provider", "provider"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(120))
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class TopicMastery(Base, TimestampMixin):
    __tablename__ = "topic_mastery"
    __table_args__ = (
        UniqueConstraint("user_id", "topic", name="uq_topic_mastery_user_topic"),
        Index("ix_topic_mastery_user_due", "user_id", "next_due_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    topic: Mapped[str] = mapped_column(String(120))
    level: Mapped[str] = mapped_column(String(32), default="exposure")
    last_quizzed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    quiz_count: Mapped[int] = mapped_column(Integer, default=0)


class WeeklyPlan(Base, TimestampMixin):
    __tablename__ = "weekly_plans"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    week_start: Mapped[date] = mapped_column(Date, index=True)
    content: Mapped[str] = mapped_column(Text)
    priorities: Mapped[list[str]] = mapped_column(JSONB, default=list)


class WorkflowRun(Base, TimestampMixin):
    __tablename__ = "workflow_runs"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    request_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    workflow_type: Mapped[str] = mapped_column(String(60), index=True)
    status: Mapped[str] = mapped_column(
        String(24), default=WorkflowStatus.RUNNING.value
    )
    result: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
