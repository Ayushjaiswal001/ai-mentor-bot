"""/settings — adjust lesson difficulty and the daily reminder hour."""

from telegram import CallbackQuery, Update
from telegram.ext import ContextTypes

from app.bot.formatting import send_html
from app.bot.keyboards import settings_kb
from app.bot.users import ensure_user
from app.db.models import User, UserState
from app.db.session import SessionLocal

DIFF_LABEL = {"simpler": "🐣 Simpler", "normal": "⚖️ Normal", "harder": "🔥 Harder"}


def _summary(state: UserState, user: User) -> str:
    rem = f"{user.reminder_hour}:00 IST" if user.reminder_hour is not None else "off"
    return (
        "⚙️ <b>Settings</b>\n\n"
        f"Difficulty: <b>{DIFF_LABEL.get(state.difficulty, state.difficulty)}</b>\n"
        f"Daily reminder: <b>{rem}</b>\n\n"
        "Difficulty changes the depth of your next lessons. Pick below:"
    )


async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        user, state, _ = await ensure_user(session, update.effective_user)
        await send_html(update.effective_message, _summary(state, user), kb=settings_kb())


async def on_difficulty(
    query: CallbackQuery, session, user: User, state: UserState, value: str
) -> None:
    state.difficulty = value
    await session.commit()
    await send_html(query.message, _summary(state, user), kb=settings_kb())


async def on_reminder(
    query: CallbackQuery, session, user: User, state: UserState, arg: str
) -> None:
    user.reminder_hour = None if arg == "off" else int(arg)
    await session.commit()
    await send_html(query.message, _summary(state, user), kb=settings_kb())
