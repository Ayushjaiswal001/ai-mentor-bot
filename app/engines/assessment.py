"""Weekly assessment: pick recent + weak topics, build an 6–8 Q quiz (t2), score & report."""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.nodes import assessment as assessment_node
from app.db.models import Assessment, Lesson, Quiz, QuizAttempt, Topic, User, UserState
from app.engines import progress as progress_engine

MIN_TOPICS = 1


def week_start(today: date | None = None) -> date:
    today = today or date.today()
    return today - timedelta(days=today.weekday())  # Monday


async def scope_topics(session: AsyncSession, user: User, days: int = 7) -> list[Topic]:
    """Topics completed in the last `days`, topped up with weak topics, else any completed."""
    since = datetime.now(UTC) - timedelta(days=days)
    recent = list(
        (
            await session.execute(
                select(Topic)
                .join(Lesson, Lesson.topic_id == Topic.id)
                .where(
                    Lesson.user_id == user.id,
                    Lesson.status == "completed",
                    Lesson.completed_at >= since,
                )
                .distinct()
            )
        ).scalars()
    )
    chosen = {t.id: t for t in recent}

    if len(chosen) < 3:  # top up with any completed topics so the quiz has breadth
        extra = list(
            (
                await session.execute(
                    select(Topic)
                    .join(Lesson, Lesson.topic_id == Topic.id)
                    .where(Lesson.user_id == user.id, Lesson.status == "completed")
                    .distinct()
                )
            ).scalars()
        )
        for t in extra:
            chosen.setdefault(t.id, t)
    return list(chosen.values())


async def start(
    session: AsyncSession, user: User, state: UserState
) -> tuple[Quiz, QuizAttempt] | None:
    topics = await scope_topics(session, user)
    if len(topics) < MIN_TOPICS:
        return None
    profile = await progress_engine.build_profile(session, user, state)
    schema = await assessment_node.generate_assessment(
        session,
        profile=profile,
        topic_titles=[t.title for t in topics],
        user_id=user.id,
    )
    quiz = Quiz(
        user_id=user.id,
        topic_id=None,
        kind="weekly",
        questions_json={
            "topics": [t.title for t in topics],
            "questions": schema.model_dump()["questions"],
        },
    )
    session.add(quiz)
    await session.flush()
    attempt = QuizAttempt(quiz_id=quiz.id, user_id=user.id, answers_json={})
    session.add(attempt)
    await session.commit()
    return quiz, attempt


async def record(
    session: AsyncSession,
    user: User,
    score: float,
    n_correct: int,
    n_total: int,
    weak_tags: list[str],
) -> dict:
    """Store the Assessment row and build a report card (with trend vs last week)."""
    prev = await session.scalar(
        select(Assessment.score_pct)
        .where(Assessment.user_id == user.id)
        .order_by(Assessment.created_at.desc())
        .limit(1)
    )
    ws = week_start()
    session.add(
        Assessment(
            user_id=user.id,
            week_start=ws,
            report_json={
                "score": score,
                "n_correct": n_correct,
                "n_total": n_total,
                "weak_tags": weak_tags,
            },
            score_pct=score,
        )
    )
    trend = None if prev is None else round(score - prev, 1)
    return {"trend": trend, "prev": prev, "week_start": ws.isoformat()}
