"""Project Coach nodes — plan (t2) and final review (t2)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import llm_router
from app.agents.nodes.base import render_system, render_task
from app.agents.schemas import EvalSchema, ProjectPlan


async def generate_plan(
    session: AsyncSession,
    *,
    profile: dict,
    project_title: str,
    project_slug: str,
    phase_title: str,
    brief: str | None,
    user_id: int | None = None,
) -> ProjectPlan:
    system = render_system(profile)
    task = render_task(
        "project_planner.md",
        ProjectPlan,
        name=profile.get("name", "the student"),
        project_title=project_title,
        phase_title=phase_title,
        brief=brief,
        difficulty=profile.get("difficulty", "normal"),
    )
    plan = await llm_router.generate_json(session, "t2", system, task, ProjectPlan, user_id)
    plan.project_slug = project_slug  # trust our slug over the model's
    return plan


async def review_project(
    session: AsyncSession,
    *,
    profile: dict,
    project_title: str,
    overview: str,
    submission: str,
    user_id: int | None = None,
) -> EvalSchema:
    system = render_system(profile)
    task = render_task(
        "project_reviewer.md",
        EvalSchema,
        name=profile.get("name", "the student"),
        project_title=project_title,
        overview=overview,
        submission=submission[:5000],
    )
    return await llm_router.generate_json(session, "t2", system, task, EvalSchema, user_id)
