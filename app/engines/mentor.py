"""Free-text Socratic mentor chat, with a per-day cap to protect the free LLM tier."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import llm_router
from app.agents.nodes import socratic
from app.config import settings
from app.db.models import Event, Phase, Topic, User, UserState
from app.engines import progress


class FreeTextCapReached(Exception):
    """The user hit today's free-text mentor message limit."""


async def chat(session: AsyncSession, user: User, state: UserState, question: str) -> str:
    used = await llm_router.count_events_today(session, user.id, "freetext")
    if used >= settings.freetext_daily_cap:
        raise FreeTextCapReached

    topic_title, phase_title = "your studies", "your roadmap"
    if state.current_topic_id is not None:
        topic = await session.get(Topic, state.current_topic_id)
        if topic is not None:
            topic_title = topic.title
            phase = await session.get(Phase, topic.phase_id)
            phase_title = phase.title if phase else phase_title

    profile = await progress.build_profile(session, user, state)
    answer = await socratic.answer_question(
        session,
        profile=profile,
        topic_title=topic_title,
        phase_title=phase_title,
        question=question,
        user_id=user.id,
    )
    session.add(Event(user_id=user.id, type="freetext", payload_json={}))
    progress.tick_activity(state, 0)  # engagement keeps the streak alive; no XP to avoid gaming
    await session.commit()
    return answer


async def remaining_freetext(session: AsyncSession, user: User) -> int:
    used = await llm_router.count_events_today(session, user.id, "freetext")
    return max(0, settings.freetext_daily_cap - used)
