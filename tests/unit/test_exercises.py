from app.agents import llm_router
from app.agents.schemas import EvalSchema, ExerciseSchema
from app.db.models import Exercise
from app.engines import exercises, learning


def fake_exercise() -> ExerciseSchema:
    return ExerciseSchema(
        topic_slug="variables",
        title="Swap two variables",
        prompt_md="Swap `a` and `b` without a temp variable.",
        starter_code="a, b = 1, 2",
        hints=["Python can assign two names at once.", "Try `a, b = b, a`."],
        rubric=["swaps correctly", "no temp variable"],
    )


def fake_eval(passed: bool) -> EvalSchema:
    return EvalSchema(
        passed=passed,
        score=90 if passed else 40,
        strengths=["clear code"],
        issues=[] if passed else ["used a temp variable"],
        suggestion="What if you assigned both at once?",
    )


async def test_issue_stores_spec_and_is_pending(env, monkeypatch):
    async def gen(session, tier, system, user_text, schema_cls, user_id=None):
        return fake_exercise()

    monkeypatch.setattr(llm_router, "generate_json", gen)

    ex, schema = await exercises.issue(env.session, env.user, env.state)
    assert ex.status == "issued"
    assert ex.feedback_json["rubric"] == ["swaps correctly", "no temp variable"]
    assert exercises.hints_of(ex) == schema.hints

    pending = await exercises.get_pending(env.session, env.user, env.state)
    assert pending is not None and pending.id == ex.id


async def test_submit_grades_and_clears_pending(env, monkeypatch):
    async def gen_ex(session, tier, system, user_text, schema_cls, user_id=None):
        return fake_exercise()

    monkeypatch.setattr(llm_router, "generate_json", gen_ex)
    ex, _ = await exercises.issue(env.session, env.user, env.state)

    async def gen_eval(session, tier, system, user_text, schema_cls, user_id=None):
        assert tier == "t2"  # grading uses the heavy tier
        return fake_eval(passed=True)

    monkeypatch.setattr(llm_router, "generate_json", gen_eval)
    result = await exercises.submit(env.session, env.user, env.state, ex, "a, b = b, a")

    assert result.passed is True
    refreshed = await env.session.get(Exercise, ex.id)
    assert refreshed.status == "reviewed"
    assert refreshed.submission_md == "a, b = b, a"
    assert refreshed.feedback_json["result"]["score"] == 90
    assert env.state.xp >= 15  # exercise XP awarded
    assert await exercises.get_pending(env.session, env.user, env.state) is None


async def test_skip_marks_reviewed(env, monkeypatch):
    async def gen(session, tier, system, user_text, schema_cls, user_id=None):
        return fake_exercise()

    monkeypatch.setattr(llm_router, "generate_json", gen)
    ex, _ = await exercises.issue(env.session, env.user, env.state)
    await exercises.skip(env.session, ex)
    assert ex.status == "reviewed"
    assert ex.feedback_json["skipped"] is True
    assert await exercises.get_pending(env.session, env.user, env.state) is None


async def test_pick_variant_respects_difficulty(env):
    assert await learning.pick_variant(env.session, env.user, env.t1.id, "harder") == "advanced"
    assert await learning.pick_variant(env.session, env.user, env.t1.id, "simpler") == "simplified"
    assert await learning.pick_variant(env.session, env.user, env.t1.id, "normal") == "standard"
