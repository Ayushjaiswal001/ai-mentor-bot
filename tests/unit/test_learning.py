from sqlalchemy import select

from app.agents import llm_router
from app.db.models import Lesson
from app.engines import learning
from tests.factories import fake_lesson


def patch_lesson_llm(monkeypatch, counter: dict):
    async def fake_generate_json(session, tier, system, user_text, schema_cls, user_id=None):
        counter["n"] += 1
        return fake_lesson()

    monkeypatch.setattr(llm_router, "generate_json", fake_generate_json)


async def test_lesson_generated_once_then_cached_and_resumed(env, monkeypatch):
    counter = {"n": 0}
    patch_lesson_llm(monkeypatch, counter)

    lesson1 = await learning.get_or_create_lesson(env.session, env.user, env.state)
    lesson2 = await learning.get_or_create_lesson(env.session, env.user, env.state)

    assert counter["n"] == 1, "second call must hit the cache/resume path"
    assert lesson1.id == lesson2.id
    assert env.state.active_lesson_id == lesson1.id
    assert lesson1.variant == "standard"


async def test_resume_pointer_survives(env, monkeypatch):
    counter = {"n": 0}
    patch_lesson_llm(monkeypatch, counter)

    lesson = await learning.get_or_create_lesson(env.session, env.user, env.state)
    lesson.progress_idx = 3
    lesson.status = "in_progress"
    await env.session.commit()

    again = await learning.get_or_create_lesson(env.session, env.user, env.state)
    assert again.id == lesson.id
    assert again.progress_idx == 3


async def test_complete_lesson_clears_active_pointer(env, monkeypatch):
    patch_lesson_llm(monkeypatch, {"n": 0})
    lesson = await learning.get_or_create_lesson(env.session, env.user, env.state)
    await learning.complete_lesson(env.session, env.state, lesson)
    await env.session.commit()

    row = await env.session.scalar(select(Lesson).where(Lesson.id == lesson.id))
    assert row.status == "completed"
    assert env.state.active_lesson_id is None
