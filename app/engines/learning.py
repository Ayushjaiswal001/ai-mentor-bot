"""Lesson lifecycle: cache-or-generate, resume pointer, topic advancement, variant pick."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.nodes import lesson_writer
from app.agents.nodes.base import PROMPT_VERSION
from app.config import settings
from app.db.models import Lesson, Phase, Quiz, QuizAttempt, Topic, User, UserState
from app.engines import progress as progress_engine


async def ordered_topics(session: AsyncSession) -> list[Topic]:
    """All topics in global roadmap order (phase order, then topic order)."""
    rows = await session.execute(
        select(Topic)
        .join(Phase, Topic.phase_id == Phase.id)
        .order_by(Phase.sort_order, Topic.sort_order)
    )
    return list(rows.scalars())


async def current_topic_and_phase(
    session: AsyncSession, state: UserState
) -> tuple[Topic, Phase] | None:
    if state.current_topic_id is None:
        return None
    topic = await session.get(Topic, state.current_topic_id)
    if topic is None:
        return None
    phase = await session.get(Phase, topic.phase_id)
    return topic, phase


async def next_topic(session: AsyncSession, state: UserState) -> Topic | None:
    topics = await ordered_topics(session)
    ids = [t.id for t in topics]
    if state.current_topic_id not in ids:
        return topics[0] if topics else None
    idx = ids.index(state.current_topic_id)
    return topics[idx + 1] if idx + 1 < len(topics) else None


async def pick_variant(
    session: AsyncSession, user: User, topic_id: int, difficulty: str = "normal"
) -> str:
    """Choose lesson depth: a failed retake forces simplified; otherwise the user's
    difficulty setting steers simplified / standard / advanced."""
    last_score = await session.scalar(
        select(QuizAttempt.score_pct)
        .join(Quiz, QuizAttempt.quiz_id == Quiz.id)
        .where(
            QuizAttempt.user_id == user.id,
            Quiz.topic_id == topic_id,
            Quiz.kind == "lesson",
            QuizAttempt.score_pct.is_not(None),
        )
        .order_by(QuizAttempt.finished_at.desc())
        .limit(1)
    )
    if last_score is not None and last_score < 50:
        return "simplified"
    if difficulty == "harder":
        return "advanced"
    if difficulty == "simpler":
        return "simplified"
    return "standard"


async def get_or_create_lesson(
    session: AsyncSession, user: User, state: UserState
) -> Lesson | None:
    """Resume the active lesson, reuse a cached one, or generate a new one. None = roadmap done."""
    if state.active_lesson_id:
        lesson = await session.get(Lesson, state.active_lesson_id)
        if lesson and lesson.status != "completed":
            return lesson

    pair = await current_topic_and_phase(session, state)
    if pair is None:
        return None
    topic, phase = pair
    variant = await pick_variant(session, user, topic.id, state.difficulty)

    lesson = await session.scalar(
        select(Lesson).where(
            Lesson.user_id == user.id,
            Lesson.topic_id == topic.id,
            Lesson.variant == variant,
            Lesson.status != "completed",
        )
    )
    if lesson is None:
        profile = await progress_engine.build_profile(session, user, state)
        schema = await lesson_writer.generate_lesson(
            session,
            profile=profile,
            topic_title=topic.title,
            topic_slug=topic.slug,
            phase_title=phase.title,
            variant=variant,
            user_id=user.id,
        )
        lesson = Lesson(
            user_id=user.id,
            topic_id=topic.id,
            variant=variant,
            content_json=schema.model_dump(),
            model_used=settings.llm_t1,
            prompt_version=PROMPT_VERSION,
        )
        session.add(lesson)
        await session.flush()

    state.active_lesson_id = lesson.id
    await session.commit()
    return lesson


async def complete_lesson(session: AsyncSession, state: UserState, lesson: Lesson) -> None:
    lesson.status = "completed"
    lesson.completed_at = datetime.now(UTC)
    if state.active_lesson_id == lesson.id:
        state.active_lesson_id = None
