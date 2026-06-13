"""Tests for the LangGraph Writer→Critic lesson pipeline (M5 multi-agent upgrade)."""

from app.agents import graph as agent_graph
from app.agents import llm_router
from app.agents.schemas import Critique, LessonSchema
from tests.factories import fake_lesson

GRAPH_KW = dict(
    profile={"name": "Ayush", "difficulty": "normal", "weak_topics": []},
    topic_title="Variables",
    topic_slug="variables",
    phase_title="Python Fundamentals",
)


def dispatcher(monkeypatch, critic_results: list[bool], counters: dict):
    """Critic returns the given verdicts in order; writer always returns a lesson."""

    async def fake(session, tier, system, user_text, schema_cls, user_id=None):
        if schema_cls is Critique:
            ok = critic_results[min(counters["critic"], len(critic_results) - 1)]
            counters["critic"] += 1
            return Critique(ok=ok, notes="" if ok else "code section: off-by-one")
        counters["writer"] += 1
        return fake_lesson()

    monkeypatch.setattr(llm_router, "generate_json", fake)


async def test_good_draft_accepted_first_pass(session, monkeypatch):
    counters = {"writer": 0, "critic": 0}
    dispatcher(monkeypatch, [True], counters)

    lesson = await agent_graph.run_lesson_graph(session, **GRAPH_KW)

    assert isinstance(lesson, LessonSchema)
    assert counters["writer"] == 1  # no revision needed
    assert counters["critic"] == 1


async def test_bad_draft_triggers_one_revision_then_accepts(session, monkeypatch):
    counters = {"writer": 0, "critic": 0}
    dispatcher(monkeypatch, [False, True], counters)  # reject, then approve

    lesson = await agent_graph.run_lesson_graph(session, **GRAPH_KW)

    assert isinstance(lesson, LessonSchema)
    assert counters["writer"] == 2  # initial + one revision
    assert counters["critic"] == 2


async def test_revision_cap_stops_the_loop(session, monkeypatch):
    counters = {"writer": 0, "critic": 0}
    dispatcher(monkeypatch, [False, False, False], counters)  # never satisfied

    lesson = await agent_graph.run_lesson_graph(session, **GRAPH_KW)

    assert isinstance(lesson, LessonSchema)  # still returns the last draft
    assert counters["writer"] == agent_graph.MAX_DRAFTS  # capped, doesn't loop forever


async def test_writer_receives_critique_notes_on_revision(session, monkeypatch):
    seen_notes = []

    async def fake(session, tier, system, user_text, schema_cls, user_id=None):
        if schema_cls is Critique:
            return Critique(ok=False, notes="FIXME-marker")
        seen_notes.append("FIXME-marker" in user_text)
        return fake_lesson()

    monkeypatch.setattr(llm_router, "generate_json", fake)
    await agent_graph.run_lesson_graph(session, **GRAPH_KW)

    # first draft has no notes; the revision draft must include the critic's notes
    assert seen_notes[0] is False
    assert seen_notes[1] is True
