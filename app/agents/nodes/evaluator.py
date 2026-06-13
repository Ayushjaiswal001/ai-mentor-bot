"""Code Evaluator node — tier t2 (the heaviest, most careful tier)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import llm_router
from app.agents.nodes.base import render_system, render_task
from app.agents.schemas import EvalSchema


async def evaluate_submission(
    session: AsyncSession,
    *,
    profile: dict,
    topic_title: str,
    prompt_md: str,
    rubric: list[str],
    submission: str,
    user_id: int | None = None,
) -> EvalSchema:
    system = render_system(profile)
    task = render_task(
        "code_evaluator.md",
        EvalSchema,
        name=profile.get("name", "the student"),
        topic_title=topic_title,
        prompt_md=prompt_md,
        rubric=rubric,
        submission=submission[:4000],  # guard against pasted megabytes
    )
    return await llm_router.generate_json(session, "t2", system, task, EvalSchema, user_id)
