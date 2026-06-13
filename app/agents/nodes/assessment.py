"""Weekly Assessment node — tier t2 (quality matters; it's the weekly checkpoint)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import llm_router
from app.agents.nodes.base import render_system, render_task
from app.agents.schemas import AssessmentSchema


async def generate_assessment(
    session: AsyncSession,
    *,
    profile: dict,
    topic_titles: list[str],
    user_id: int | None = None,
) -> AssessmentSchema:
    system = render_system(profile)
    task = render_task(
        "weekly_assessment.md",
        AssessmentSchema,
        name=profile.get("name", "the student"),
        topics=", ".join(topic_titles),
        difficulty=profile.get("difficulty", "normal"),
    )
    return await llm_router.generate_json(
        session, "t2", system, task, AssessmentSchema, user_id
    )
