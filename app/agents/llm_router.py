"""Tiered LLM access: provider fallback chain, JSON-schema validation w/ retry, budget guard.

Tiers (docs/02_ENGINEERING_DESIGN.md §5): t0 = routing/validation, t1 = content, t2 = heavy.
Providers are plain REST via httpx — no SDK lock-in; models rotate via .env.
"""

import json
import re
import time
from datetime import UTC, datetime

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Event

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
TIMEOUT = 60.0


class LLMUnavailable(Exception):
    """All providers in the tier's chain failed."""


class LLMBudgetExceeded(Exception):
    """Daily call cap for this tier reached (free-tier protection)."""


def _chains() -> dict[str, list[str]]:
    chains = {
        "t0": [settings.llm_t0],
        "t1": [settings.llm_t1],
        "t2": [settings.llm_t2, settings.llm_t1],
    }
    if settings.groq_api_key:
        chains["t0"].append("groq:llama-3.1-8b-instant")
        chains["t1"].append("groq:llama-3.3-70b-versatile")
        chains["t2"].append("groq:llama-3.3-70b-versatile")
    return chains


def _cap(tier: str) -> int | None:
    return {"t1": settings.daily_t1_cap, "t2": settings.daily_t2_cap}.get(tier)


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", raw, flags=re.S)
    return match.group(1) if match else raw


async def _calls_today(session: AsyncSession, tier: str) -> int:
    day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        await session.scalar(
            select(func.count(Event.id)).where(
                Event.type == "llm_usage",
                Event.created_at >= day_start,
                Event.payload_json["tier"].as_string() == tier,
            )
        )
    ) or 0


async def _call_gemini(model: str, system: str, user_text: str, json_mode: bool = True) -> str:
    if not settings.gemini_api_key:
        raise LLMUnavailable("GEMINI_API_KEY not set")
    gen_config: dict = {"temperature": 0.7}
    if json_mode:
        gen_config["response_mime_type"] = "application/json"
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "generationConfig": gen_config,
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(
            GEMINI_URL.format(model=model),
            params={"key": settings.gemini_api_key},
            json=body,
        )
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]


async def _call_groq(model: str, system: str, user_text: str, json_mode: bool = True) -> str:
    if not settings.groq_api_key:
        raise LLMUnavailable("GROQ_API_KEY not set")
    body: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.7,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            json=body,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


_PROVIDERS = {"gemini": _call_gemini, "groq": _call_groq}


async def generate_json[T: BaseModel](
    session: AsyncSession,
    tier: str,
    system: str,
    user_text: str,
    schema_cls: type[T],
    user_id: int | None = None,
) -> T:
    """Call the tier's provider chain until one returns valid JSON for schema_cls.

    Validation failures retry once on the same provider (with the error fed back);
    transport/provider failures move to the next provider in the chain.
    """
    cap = _cap(tier)
    if cap is not None and await _calls_today(session, tier) >= cap:
        raise LLMBudgetExceeded(f"daily cap for {tier} reached ({cap} calls)")

    last_err: Exception | None = None
    for spec in _chains()[tier]:
        provider, model = spec.split(":", 1)
        call = _PROVIDERS[provider]
        prompt = user_text
        for _attempt in (1, 2):
            started = time.monotonic()
            try:
                raw = await call(model, system, prompt)
                obj = schema_cls.model_validate_json(_strip_fences(raw))
            except (ValidationError, json.JSONDecodeError) as e:
                last_err = e
                prompt = (
                    f"{user_text}\n\nYour previous reply was rejected: {e}\n"
                    "Return ONLY valid JSON matching the schema. No prose, no code fences."
                )
                continue
            except Exception as e:  # transport, auth, rate limit, malformed response
                last_err = e
                break
            session.add(
                Event(
                    user_id=user_id,
                    type="llm_usage",
                    payload_json={
                        "tier": tier,
                        "model": spec,
                        "ok": True,
                        "ms": int((time.monotonic() - started) * 1000),
                    },
                )
            )
            await session.flush()
            return obj

    session.add(
        Event(
            user_id=user_id,
            type="llm_usage",
            payload_json={"tier": tier, "ok": False, "error": str(last_err)[:300]},
        )
    )
    await session.flush()
    raise LLMUnavailable(f"all providers failed for {tier}: {last_err}")


async def generate_text(
    session: AsyncSession,
    tier: str,
    system: str,
    user_text: str,
    user_id: int | None = None,
) -> str:
    """Free-form text generation (no schema) across the tier's provider chain."""
    cap = _cap(tier)
    if cap is not None and await _calls_today(session, tier) >= cap:
        raise LLMBudgetExceeded(f"daily cap for {tier} reached ({cap} calls)")

    last_err: Exception | None = None
    for spec in _chains()[tier]:
        provider, model = spec.split(":", 1)
        try:
            raw = await _PROVIDERS[provider](model, system, user_text, False)
        except Exception as e:
            last_err = e
            continue
        session.add(
            Event(
                user_id=user_id,
                type="llm_usage",
                payload_json={"tier": tier, "model": spec, "ok": True, "mode": "text"},
            )
        )
        await session.flush()
        return raw.strip()

    raise LLMUnavailable(f"all providers failed for {tier}: {last_err}")


async def count_events_today(session: AsyncSession, user_id: int, event_type: str) -> int:
    """Count today's events of a given type for a user (e.g. free-text mentor turns)."""
    day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        await session.scalar(
            select(func.count(Event.id)).where(
                Event.user_id == user_id,
                Event.type == event_type,
                Event.created_at >= day_start,
            )
        )
    ) or 0
