from datetime import UTC, datetime

from sqlalchemy import func, select

from app.agents import llm_router
from app.agents.schemas import MCQ, AssessmentSchema
from app.db.models import Assessment, Lesson
from app.engines import assessment as ae
from app.engines import quiz as quiz_engine


def fake_assessment() -> AssessmentSchema:
    return AssessmentSchema(
        questions=[
            MCQ(
                question=f"q{i}",
                options=["a", "b", "c", "d"],
                correct_index=0,
                explanation="because",
                concept_tag=f"tag{i}",
            )
            for i in range(6)
        ]
    )


async def _complete_lesson(env, topic_id):
    env.session.add(
        Lesson(
            user_id=env.user.id,
            topic_id=topic_id,
            variant="standard",
            content_json={},
            status="completed",
            completed_at=datetime.now(UTC),
        )
    )
    await env.session.commit()


async def test_scope_includes_completed_topics(env):
    await _complete_lesson(env, env.t1.id)
    topics = await ae.scope_topics(env.session, env.user)
    assert any(t.id == env.t1.id for t in topics)


async def test_weekly_flow_scores_and_records(env, monkeypatch):
    await _complete_lesson(env, env.t1.id)

    async def gen(session, tier, system, user_text, schema_cls, user_id=None):
        assert tier == "t2"
        return fake_assessment()

    monkeypatch.setattr(llm_router, "generate_json", gen)

    result = await ae.start(env.session, env.user, env.state)
    assert result is not None
    quiz, attempt = result
    assert quiz.kind == "weekly"
    qs = quiz_engine.questions_of(quiz)
    assert len(qs) == 6

    for i in range(6):
        quiz_engine.record_answer(attempt, quiz, i, 0)  # all correct
    report = await quiz_engine.finalize(env.session, env.user, env.state, quiz, attempt)

    assert report["kind"] == "weekly"
    assert report["score"] == 100
    assert report["trend"] is None  # first assessment, no prior
    assert (await env.session.scalar(select(func.count(Assessment.id)))) == 1


async def test_no_assessment_without_completed_lessons(env, monkeypatch):
    # no completed lessons → scope is empty → start returns None
    result = await ae.start(env.session, env.user, env.state)
    assert result is None
