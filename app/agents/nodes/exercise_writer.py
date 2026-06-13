"""Exercise Writer node — tier t1."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import llm_router
from app.agents.nodes.base import render_system, render_task
from app.agents.schemas import ExerciseSchema


async def generate_exercise(
    session: AsyncSession,
    *,
    profile: dict,
    topic_title: str,
    topic_slug: str,
    phase_title: str,
    user_id: int | None = None,
) -> ExerciseSchema:
    system = render_system(profile)
    task = render_task(
        "exercise_writer.md",
        ExerciseSchema,
        topic_title=topic_title,
        topic_slug=topic_slug,
        phase_title=phase_title,
        difficulty=profile.get("difficulty", "normal"),
    )
    return await llm_router.generate_json(session, "t1", system, task, ExerciseSchema, user_id)
