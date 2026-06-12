"""Streaks, XP, weak topics, profile building, progress/roadmap reports."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Lesson, Phase, Quiz, QuizAttempt, Topic, User, UserState

XP = {"lesson": 10, "quiz": 5, "quiz_bonus": 5, "revision": 5, "exercise": 15, "project_step": 20}


def tick_activity(state: UserState, xp_gain: int = 0) -> None:
    """Update streak for today's activity and award XP. Caller commits."""
    today = date.today()
    if state.last_active_date != today:
        if state.last_active_date == today - timedelta(days=1):
            state.streak_count += 1
        else:
            state.streak_count = 1
        state.last_active_date = today
        state.longest_streak = max(state.longest_streak, state.streak_count)
    state.xp += xp_gain


async def recent_scores(session: AsyncSession, user: User, limit: int = 5) -> list[float]:
    rows = await session.execute(
        select(QuizAttempt.score_pct)
        .where(QuizAttempt.user_id == user.id, QuizAttempt.score_pct.is_not(None))
        .order_by(QuizAttempt.finished_at.desc())
        .limit(limit)
    )
    return [r for (r,) in rows.all()]


async def weak_topics(session: AsyncSession, user: User, limit: int = 5) -> list[str]:
    """Titles of topics whose most recent lesson-quiz attempt scored < 80%."""
    rows = await session.execute(
        select(Topic.title, QuizAttempt.score_pct, QuizAttempt.finished_at)
        .join(Quiz, QuizAttempt.quiz_id == Quiz.id)
        .join(Topic, Quiz.topic_id == Topic.id)
        .where(
            QuizAttempt.user_id == user.id,
            Quiz.kind == "lesson",
            QuizAttempt.score_pct.is_not(None),
        )
        .order_by(QuizAttempt.finished_at.desc())
    )
    latest: dict[str, float] = {}
    for title, score, _at in rows.all():
        latest.setdefault(title, score)  # first seen = most recent
    return [t for t, s in latest.items() if s < 80][:limit]


async def build_profile(session: AsyncSession, user: User, state: UserState) -> dict:
    return {
        "name": user.first_name or "friend",
        "difficulty": state.difficulty,
        "weak_topics": await weak_topics(session, user),
    }


async def report(session: AsyncSession, user: User, state: UserState) -> dict:
    completed = (
        await session.scalar(
            select(Lesson.id)
            .where(Lesson.user_id == user.id, Lesson.status == "completed")
            .order_by(Lesson.id)
            .limit(1)
        )
        is not None
    )
    lessons_done = len(
        (
            await session.execute(
                select(Lesson.topic_id)
                .where(Lesson.user_id == user.id, Lesson.status == "completed")
                .distinct()
            )
        ).all()
    )
    scores = await recent_scores(session, user)
    pair_topic = (
        await session.get(Topic, state.current_topic_id) if state.current_topic_id else None
    )
    pair_phase = await session.get(Phase, pair_topic.phase_id) if pair_topic else None
    return {
        "has_history": completed,
        "lessons_done": lessons_done,
        "avg_recent_score": round(sum(scores) / len(scores), 1) if scores else None,
        "weak_topics": await weak_topics(session, user),
        "streak": state.streak_count,
        "longest_streak": state.longest_streak,
        "xp": state.xp,
        "current_phase": pair_phase.title if pair_phase else "—",
        "current_topic": pair_topic.title if pair_topic else "Roadmap complete 🎉",
    }


async def roadmap_view(session: AsyncSession, user: User, state: UserState) -> list[dict]:
    phases = list(
        (await session.execute(select(Phase).order_by(Phase.sort_order))).scalars()
    )
    topics = list((await session.execute(select(Topic))).scalars())
    done_topic_ids = {
        tid
        for (tid,) in (
            await session.execute(
                select(Lesson.topic_id)
                .where(Lesson.user_id == user.id, Lesson.status == "completed")
                .distinct()
            )
        ).all()
    }
    view = []
    for phase in phases:
        ph_topics = sorted(
            (t for t in topics if t.phase_id == phase.id), key=lambda t: t.sort_order
        )
        done = sum(1 for t in ph_topics if t.id in done_topic_ids)
        is_current = state.current_topic_id in {t.id for t in ph_topics}
        view.append(
            {
                "title": phase.title,
                "done": done,
                "total": len(ph_topics),
                "current": is_current,
            }
        )
    return view
