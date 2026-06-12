"""Lesson Writer node — tier t1. Direct call in M1; becomes a LangGraph node in M5."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import llm_router
from app.agents.nodes.base import render_system, render_task
from app.agents.schemas import LessonSchema


async def generate_lesson(
    session: AsyncSession,
    *,
    profile: dict,
    topic_title: str,
    topic_slug: str,
    phase_title: str,
    variant: str = "standard",
    recap: str | None = None,
    user_id: int | None = None,
) -> LessonSchema:
    system = render_system(profile)
    task = render_task(
        "lesson_writer.md",
        LessonSchema,
        topic_title=topic_title,
        topic_slug=topic_slug,
        phase_title=phase_title,
        variant=variant,
        recap=recap,
    )
    return await llm_router.generate_json(session, "t1", system, task, LessonSchema, user_id)
