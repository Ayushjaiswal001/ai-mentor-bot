"""SQLAlchemy 2.0 models. Schema reference: docs/02_ENGINEERING_DESIGN.md §7."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    first_name: Mapped[str | None] = mapped_column(String(128))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    reminder_hour: Mapped[int | None] = mapped_column(default=20)  # None = reminders off
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserState(Base):
    __tablename__ = "user_state"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    current_phase_id: Mapped[int | None] = mapped_column(ForeignKey("phases.id"))
    current_topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id"))
    active_lesson_id: Mapped[int | None] = mapped_column(ForeignKey("lessons.id"))
    difficulty: Mapped[str] = mapped_column(String(16), default="normal")  # simpler|normal|harder
    streak_count: Mapped[int] = mapped_column(default=0)
    longest_streak: Mapped[int] = mapped_column(default=0)
    last_active_date: Mapped[date | None] = mapped_column(Date)
    xp: Mapped[int] = mapped_column(default=0)


class Phase(Base):
    __tablename__ = "phases"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(String(128))
    sort_order: Mapped[int] = mapped_column(default=0)


class Topic(Base):
    __tablename__ = "topics"
    __table_args__ = (UniqueConstraint("phase_id", "slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    phase_id: Mapped[int] = mapped_column(ForeignKey("phases.id"))
    slug: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(128))
    sort_order: Mapped[int] = mapped_column(default=0)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("phase_id", "slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    phase_id: Mapped[int] = mapped_column(ForeignKey("phases.id"))
    slug: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(128))
    brief_md: Mapped[str | None] = mapped_column(Text)


class Lesson(Base):
    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"))
    # standard | simplified | advanced — the (topic, variant) pair is the lesson cache key
    variant: Mapped[str] = mapped_column(String(16), default="standard")
    content_json: Mapped[dict] = mapped_column(JSON)
    model_used: Mapped[str | None] = mapped_column(String(64))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    progress_idx: Mapped[int] = mapped_column(default=0)  # last delivered section (resume)
    status: Mapped[str] = mapped_column(String(16), default="generated")  # |in_progress|completed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id"))
    kind: Mapped[str] = mapped_column(String(16), default="lesson")  # lesson|revision|weekly
    questions_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    __table_args__ = (Index("ix_quiz_attempts_user_finished", "user_id", "finished_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    answers_json: Mapped[dict] = mapped_column(JSON, default=dict)
    score_pct: Mapped[float | None] = mapped_column()
    weak_tags_json: Mapped[dict | None] = mapped_column(JSON)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QuestionBank(Base):
    __tablename__ = "question_bank"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    question_json: Mapped[dict] = mapped_column(JSON)
    times_used: Mapped[int] = mapped_column(default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReviewItem(Base):
    __tablename__ = "review_items"
    __table_args__ = (
        UniqueConstraint("user_id", "topic_id"),
        Index("ix_review_items_user_due", "user_id", "due_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"))
    ladder_index: Mapped[int] = mapped_column(default=0)  # 0..4 → [1,3,7,14,30] days; 5 = retired
    due_date: Mapped[date] = mapped_column(Date)
    lapses: Mapped[int] = mapped_column(default=0)
    last_result: Mapped[str | None] = mapped_column(String(8))  # pass | fail
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"))
    prompt_md: Mapped[str] = mapped_column(Text)
    submission_md: Mapped[str | None] = mapped_column(Text)
    feedback_json: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="issued")  # issued|submitted|reviewed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProjectProgress(Base):
    __tablename__ = "project_progress"
    __table_args__ = (UniqueConstraint("user_id", "project_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    plan_json: Mapped[dict | None] = mapped_column(JSON)
    current_step: Mapped[int] = mapped_column(default=0)
    total_steps: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(16), default="proposed")  # proposed|active|done
    notes_md: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    week_start: Mapped[date] = mapped_column(Date)
    report_json: Mapped[dict] = mapped_column(JSON)
    score_pct: Mapped[float | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_user_type_created", "user_id", "type", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    type: Mapped[str] = mapped_column(String(48))  # llm_usage | error | action | job_marker
    payload_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
