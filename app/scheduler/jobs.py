"""Heartbeat job: per-user daily reminder + evening streak nudge.

Runs every 30 min via PTB's JobQueue. Stateless across restarts — schedules are
code-defined and re-registered on boot; the only persistent state is in Postgres.
Idempotent: each send writes a per-user, per-day 'job_marker' event that guards repeats.
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.bot.handlers.today import today_view
from app.db.models import Event, User, UserState
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

NUDGE_HOUR = 21  # local time for the "don't break your streak" nudge
DEFAULT_TZ = "Asia/Kolkata"

NUDGE_TEXT = (
    "🌙 <b>Don't break your streak!</b>\n"
    "A quick lesson or a review keeps 🔥 <b>{streak}</b> alive. Send /today to see what's up."
)


def _tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo(DEFAULT_TZ)


async def _marked(session, user_id: int, job: str, day: str) -> bool:
    return (
        await session.scalar(
            select(Event.id)
            .where(
                Event.user_id == user_id,
                Event.type == "job_marker",
                Event.payload_json["job"].as_string() == job,
                Event.payload_json["day"].as_string() == day,
            )
            .limit(1)
        )
    ) is not None


def _mark(session, user_id: int, job: str, day: str) -> None:
    session.add(
        Event(user_id=user_id, type="job_marker", payload_json={"job": job, "day": day})
    )


async def heartbeat(context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        users = list((await session.execute(select(User))).scalars())
        for user in users:
            state = await session.get(UserState, user.id)
            if state is None:
                continue
            now = datetime.now(_tz(user.timezone))
            day = now.date().isoformat()

            # Daily reminder at the user's chosen hour
            if user.reminder_hour is not None and now.hour == user.reminder_hour:
                if not await _marked(session, user.id, "reminder", day):
                    text, kb, has_todo = await today_view(session, user, state)
                    if has_todo:
                        await _safe_send(context, user.tg_user_id, text, kb)
                    _mark(session, user.id, "reminder", day)

            # Evening streak nudge if nothing done today (and reminder didn't already cover it)
            if now.hour == NUDGE_HOUR and state.last_active_date != now.date():
                already = await _marked(session, user.id, "reminder", day) or await _marked(
                    session, user.id, "nudge", day
                )
                if not already:
                    await _safe_send(
                        context,
                        user.tg_user_id,
                        NUDGE_TEXT.format(streak=state.streak_count),
                        None,
                    )
                    _mark(session, user.id, "nudge", day)
        await session.commit()


async def _safe_send(context, chat_id: int, text: str, kb) -> None:
    try:
        await context.bot.send_message(
            chat_id=chat_id, text=text, reply_markup=kb, parse_mode=ParseMode.HTML
        )
    except Exception:
        logger.warning("reminder send failed for chat %s", chat_id, exc_info=True)
