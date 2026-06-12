from sqlalchemy import func, select

from app.agents import llm_router
from app.db.models import QuestionBank, ReviewItem
from app.engines import learning
from app.engines import quiz as quiz_engine
from tests.factories import fake_quiz


def patch_quiz_llm(monkeypatch, correct_index: int = 0):
    async def fake_generate_json(session, tier, system, user_text, schema_cls, user_id=None):
        return fake_quiz(correct_index=correct_index)

    monkeypatch.setattr(llm_router, "generate_json", fake_generate_json)


async def test_perfect_score_advances_topic(env, monkeypatch):
    patch_quiz_llm(monkeypatch)
    quiz, attempt = await quiz_engine.start_for_topic(env.session, env.user, env.state, env.t1)

    for i in range(5):
        fb = quiz_engine.record_answer(attempt, quiz, i, 0)
        assert fb["correct"]
    report = await quiz_engine.finalize(env.session, env.user, env.state, quiz, attempt)

    assert report["score"] == 100
    assert report["outcome"] == "advance"
    assert env.state.current_topic_id == env.t2.id
    assert report["next_topic_title"] == env.t2.title
    assert env.state.streak_count == 1
    assert env.state.xp >= 10

    review = await env.session.scalar(
        select(ReviewItem).where(ReviewItem.topic_id == env.t1.id)
    )
    assert review is not None and review.ladder_index == 0

    banked = await env.session.scalar(select(func.count(QuestionBank.id)))
    assert banked == 5


async def test_low_score_repeats_with_simplified_variant(env, monkeypatch):
    patch_quiz_llm(monkeypatch)
    quiz, attempt = await quiz_engine.start_for_topic(env.session, env.user, env.state, env.t1)

    quiz_engine.record_answer(attempt, quiz, 0, 0)  # 1 correct
    for i in range(1, 5):
        quiz_engine.record_answer(attempt, quiz, i, 1)  # 4 wrong
    report = await quiz_engine.finalize(env.session, env.user, env.state, quiz, attempt)

    assert report["score"] == 20
    assert report["outcome"] == "repeat"
    assert env.state.current_topic_id == env.t1.id, "must NOT advance"
    assert len(report["weak_tags"]) == 4

    variant = await learning.pick_variant(env.session, env.user, env.t1.id)
    assert variant == "simplified"


async def test_mid_score_advances_but_flags(env, monkeypatch):
    patch_quiz_llm(monkeypatch)
    quiz, attempt = await quiz_engine.start_for_topic(env.session, env.user, env.state, env.t1)

    for i in range(3):
        quiz_engine.record_answer(attempt, quiz, i, 0)  # 3 correct = 60%
    for i in range(3, 5):
        quiz_engine.record_answer(attempt, quiz, i, 2)
    report = await quiz_engine.finalize(env.session, env.user, env.state, quiz, attempt)

    assert report["outcome"] == "flagged"
    assert env.state.current_topic_id == env.t2.id, "50-79% still advances"


async def test_answers_are_idempotent(env, monkeypatch):
    patch_quiz_llm(monkeypatch)
    quiz, attempt = await quiz_engine.start_for_topic(env.session, env.user, env.state, env.t1)

    first = quiz_engine.record_answer(attempt, quiz, 0, 0)
    second = quiz_engine.record_answer(attempt, quiz, 0, 3)
    assert first is not None
    assert second is None, "double tap must not overwrite or double-count"
