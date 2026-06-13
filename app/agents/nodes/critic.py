"""Lesson Critic node — tier t0 (cheap). Reviews a draft for quality beyond schema validity."""

import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import llm_router
from app.agents.nodes.base import render_system, render_task
from app.agents.schemas import Critique


async def review_lesson(
    session: AsyncSession,
    *,
    profile: dict,
    topic_title: str,
    variant: str,
    draft: dict,
    user_id: int | None = None,
) -> Critique:
    system = render_system(profile)
    task = render_task(
        "lesson_critic.md",
        Critique,
        name=profile.get("name", "the student"),
        topic_title=topic_title,
        variant=variant,
        draft_json=json.dumps(draft, separators=(",", ":"))[:6000],
    )
    return await llm_router.generate_json(session, "t0", system, task, Critique, user_id)
