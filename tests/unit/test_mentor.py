import pytest

from app.agents import llm_router
from app.config import settings
from app.engines import mentor


async def test_chat_answers_and_logs_freetext(env, monkeypatch):
    async def gen_text(session, tier, system, user_text, user_id=None):
        return "Great question! What do you think a variable points to?"

    monkeypatch.setattr(llm_router, "generate_text", gen_text)

    answer = await mentor.chat(env.session, env.user, env.state, "what is a variable?")
    assert "variable" in answer.lower()
    assert await llm_router.count_events_today(env.session, env.user.id, "freetext") == 1


async def test_chat_enforces_daily_cap(env, monkeypatch):
    async def gen_text(session, tier, system, user_text, user_id=None):
        return "answer"

    monkeypatch.setattr(llm_router, "generate_text", gen_text)
    monkeypatch.setattr(settings, "freetext_daily_cap", 2)

    await mentor.chat(env.session, env.user, env.state, "q1")
    await mentor.chat(env.session, env.user, env.state, "q2")
    assert await mentor.remaining_freetext(env.session, env.user) == 0
    with pytest.raises(mentor.FreeTextCapReached):
        await mentor.chat(env.session, env.user, env.state, "q3")
