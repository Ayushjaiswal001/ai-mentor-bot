"""Socratic Mentor node — tier t1, free-form text."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import llm_router
from app.agents.nodes.base import render_system, render_task


async def answer_question(
    session: AsyncSession,
    *,
    profile: dict,
    topic_title: str,
    phase_title: str,
    question: str,
    user_id: int | None = None,
) -> str:
    system = render_system(profile)
    task = render_task(
        "socratic_mentor.md",
        None,
        name=profile.get("name", "the student"),
        topic_title=topic_title,
        phase_title=phase_title,
        question=question[:1500],
    )
    return await llm_router.generate_text(session, "t1", system, task, user_id)
