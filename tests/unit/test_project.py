from app.agents import llm_router
from app.agents.schemas import EvalSchema, ProjectPlan, ProjectStep
from app.db.models import Project
from app.engines import project_coach


def fake_plan() -> ProjectPlan:
    return ProjectPlan(
        project_slug="calculator",
        title="Calculator",
        overview="Build a command-line calculator.",
        steps=[
            ProjectStep(title=f"Step {i}", goal="do it", details_md="details", done_when="works")
            for i in range(4)
        ],
    )


async def _seed_project(env):
    proj = Project(phase_id=env.phase.id, slug="calculator", title="Calculator")
    env.session.add(proj)
    await env.session.commit()
    return proj


async def test_propose_start_and_advance_to_completion(env, monkeypatch):
    await _seed_project(env)

    async def gen(session, tier, system, user_text, schema_cls, user_id=None):
        assert tier == "t2"
        return fake_plan()

    monkeypatch.setattr(llm_router, "generate_json", gen)

    result = await project_coach.propose_next(env.session, env.user, env.state)
    assert result is not None
    pp, project = result
    assert pp.status == "proposed"
    assert pp.total_steps == 4

    in_prog = await project_coach.get_in_progress(env.session, env.user, env.state)
    assert in_prog.id == pp.id

    await project_coach.start(env.session, pp)
    assert pp.status == "active"
    assert project_coach.current_step(pp).title == "Step 0"

    for _ in range(3):
        res = await project_coach.advance(env.session, env.user, env.state, pp)
        assert res["completed_all"] is False
    res = await project_coach.advance(env.session, env.user, env.state, pp)
    assert res["completed_all"] is True
    assert env.state.xp >= 80  # 4 steps * 20 XP


async def test_review_final_marks_done(env, monkeypatch):
    await _seed_project(env)

    async def gen_plan(session, tier, system, user_text, schema_cls, user_id=None):
        return fake_plan()

    monkeypatch.setattr(llm_router, "generate_json", gen_plan)
    pp, _ = await project_coach.propose_next(env.session, env.user, env.state)
    await project_coach.start(env.session, pp)

    async def gen_eval(session, tier, system, user_text, schema_cls, user_id=None):
        return EvalSchema(
            passed=True, score=85, strengths=["clean"], issues=[], suggestion="add tests"
        )

    monkeypatch.setattr(llm_router, "generate_json", gen_eval)
    result = await project_coach.review_final(
        env.session, env.user, env.state, pp, "github.com/me/calc"
    )
    assert result.passed is True
    assert pp.status == "done"
    assert await project_coach.get_in_progress(env.session, env.user, env.state) is None
