from datetime import date, timedelta

from app.agents import llm_router
from app.db.models import QuestionBank, ReviewItem
from app.engines import quiz as quiz_engine
from app.engines import revision
from tests.factories import fake_quiz

TODAY = date(2026, 6, 12)


def make_item(index: int) -> ReviewItem:
    return ReviewItem(user_id=1, topic_id=1, ladder_index=index, due_date=TODAY, lapses=0)


def due_now(uid: int, tid: int) -> ReviewItem:
    return ReviewItem(user_id=uid, topic_id=tid, ladder_index=0, due_date=date.today())


def test_ladder_promotes_and_schedules_further_out():
    item = make_item(0)
    revision.apply_ladder(item, passed=True, today=TODAY)
    assert item.ladder_index == 1
    assert item.due_date == TODAY + timedelta(days=3)  # LADDER[1]
    assert item.last_result == "pass"


def test_ladder_demotes_and_counts_lapse():
    item = make_item(3)
    revision.apply_ladder(item, passed=False, today=TODAY)
    assert item.ladder_index == 2
    assert item.lapses == 1
    assert item.due_date == TODAY + timedelta(days=LADDER_AT(2))
    assert item.last_result == "fail"


def test_ladder_floor_at_zero():
    item = make_item(0)
    revision.apply_ladder(item, passed=False, today=TODAY)
    assert item.ladder_index == 0
    assert item.due_date == TODAY + timedelta(days=1)  # LADDER[0]


def test_ladder_retires_after_final_rung():
    item = make_item(4)
    revision.apply_ladder(item, passed=True, today=TODAY)
    assert item.ladder_index == revision.RETIRED
    assert item.due_date > TODAY + timedelta(days=300)


def test_is_pass_two_of_three():
    assert revision.is_pass(2, 3) is True
    assert revision.is_pass(1, 3) is False
    assert revision.is_pass(3, 3) is True


def LADDER_AT(i: int) -> int:
    return revision.LADDER[i]


async def test_due_lists_only_past_due_active_items(env):
    s = env.session
    s.add(due_now(env.user.id, env.t1.id))
    s.add(
        ReviewItem(
            user_id=env.user.id,
            topic_id=env.t2.id,
            ladder_index=0,
            due_date=date.today() + timedelta(days=5),  # not due yet
        )
    )
    await s.commit()

    due = await revision.due(s, env.user)
    assert len(due) == 1
    assert due[0][1].id == env.t1.id
    assert await revision.count_due(s, env.user) == 1


async def test_revision_quiz_uses_question_bank_when_full(env, monkeypatch):
    s = env.session
    for i in range(5):
        s.add(
            QuestionBank(
                topic_id=env.t1.id,
                question_json={
                    "question": f"Q{i}",
                    "options": ["a", "b", "c", "d"],
                    "correct_index": 0,
                    "explanation": "because",
                    "concept_tag": "tag",
                },
            )
        )
    item = due_now(env.user.id, env.t1.id)
    s.add(item)
    await s.commit()

    def boom(*a, **k):
        raise AssertionError("must not call the LLM when the bank has enough questions")

    monkeypatch.setattr(llm_router, "generate_json", boom)

    quiz, attempt, topic = await revision.start_revision(s, env.user, env.state, item)
    assert len(quiz_engine.questions_of(quiz)) == revision.REVIEW_QUESTIONS
    assert topic.id == env.t1.id


async def test_revision_finalize_passes_and_promotes(env, monkeypatch):
    s = env.session

    async def fake_gen(session, tier, system, user_text, schema_cls, user_id=None):
        return fake_quiz(correct_index=0)

    monkeypatch.setattr(llm_router, "generate_json", fake_gen)

    item = due_now(env.user.id, env.t1.id)
    s.add(item)
    await s.commit()

    quiz, attempt, _ = await revision.start_revision(s, env.user, env.state, item)
    for i in range(revision.REVIEW_QUESTIONS):
        quiz_engine.record_answer(attempt, quiz, i, 0)  # all correct
    report = await quiz_engine.finalize(s, env.user, env.state, quiz, attempt)

    assert report["kind"] == "revision"
    assert report["passed"] is True
    refreshed = await s.get(ReviewItem, item.id)
    assert refreshed.ladder_index == 1
    assert report["remaining_due"] == 0
