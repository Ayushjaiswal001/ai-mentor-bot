"""LangGraph multi-agent lesson pipeline: Writer → Critic → (revise | accept).

This is the M5 multi-agent upgrade. The engine interface is unchanged: callers get a
validated LessonSchema; internally a writer agent drafts and a critic agent reviews, looping
once for a revision if the draft falls short. Same pattern extends to quizzes/exercises later.
"""

from typing import TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.nodes import critic as critic_node
from app.agents.nodes import lesson_writer
from app.agents.schemas import LessonSchema

MAX_DRAFTS = 2  # 1 initial + at most 1 revision — caps token spend on the critic loop


class LessonState(TypedDict, total=False):
    # inputs (set once)
    profile: dict
    topic_title: str
    topic_slug: str
    phase_title: str
    variant: str
    recap: str | None
    user_id: int | None
    # working memory
    draft: dict
    critique: dict
    drafts: int
    # output
    lesson: dict


def _build(session: AsyncSession):
    async def writer(state: LessonState) -> dict:
        notes = None
        if state.get("drafts"):  # this is a revision — feed the critic's notes back in
            notes = (state.get("critique") or {}).get("notes") or None
        schema = await lesson_writer.generate_lesson(
            session,
            profile=state["profile"],
            topic_title=state["topic_title"],
            topic_slug=state["topic_slug"],
            phase_title=state["phase_title"],
            variant=state.get("variant", "standard"),
            recap=state.get("recap"),
            critique_notes=notes,
            user_id=state.get("user_id"),
        )
        return {"draft": schema.model_dump(), "drafts": state.get("drafts", 0) + 1}

    async def critic(state: LessonState) -> dict:
        verdict = await critic_node.review_lesson(
            session,
            profile=state["profile"],
            topic_title=state["topic_title"],
            variant=state.get("variant", "standard"),
            draft=state["draft"],
            user_id=state.get("user_id"),
        )
        return {"critique": verdict.model_dump()}

    def route(state: LessonState) -> str:
        approved = (state.get("critique") or {}).get("ok", False)
        if approved or state.get("drafts", 0) >= MAX_DRAFTS:
            return "accept"
        return "revise"

    def accept(state: LessonState) -> dict:
        return {"lesson": state["draft"]}

    g = StateGraph(LessonState)
    g.add_node("writer", writer)
    g.add_node("critic", critic)
    g.add_node("accept", accept)
    g.set_entry_point("writer")
    g.add_edge("writer", "critic")
    g.add_conditional_edges("critic", route, {"revise": "writer", "accept": "accept"})
    g.add_edge("accept", END)
    return g.compile()


async def run_lesson_graph(
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
    graph = _build(session)
    final = await graph.ainvoke(
        {
            "profile": profile,
            "topic_title": topic_title,
            "topic_slug": topic_slug,
            "phase_title": phase_title,
            "variant": variant,
            "recap": recap,
            "user_id": user_id,
            "drafts": 0,
        }
    )
    return LessonSchema.model_validate(final["lesson"])
