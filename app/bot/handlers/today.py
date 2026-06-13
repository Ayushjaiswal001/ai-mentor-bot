"""/today — the daily plan. today_view() is shared with the reminder job."""

from datetime import date

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.bot.formatting import esc, send_html
from app.bot.keyboards import today_kb
from app.bot.users import ensure_user
from app.db.models import Topic, User, UserState
from app.db.session import SessionLocal
from app.engines import revision


async def today_view(
    session, user: User, state: UserState
) -> tuple[str, InlineKeyboardMarkup | None, bool]:
    """Returns (html_text, keyboard, has_todo). Used by /today and the daily reminder."""
    due_count = await revision.count_due(session, user)
    topic = await session.get(Topic, state.current_topic_id) if state.current_topic_id else None
    done_today = state.last_active_date == date.today()
    has_lesson = topic is not None
    has_todo = (not done_today) or due_count > 0

    lines = [f"🗓 <b>Today's plan, {esc(user.first_name or 'friend')}</b>", ""]
    lines.append(f"🔥 Streak: <b>{state.streak_count}</b> · ⭐ XP: <b>{state.xp}</b>")
    if topic is not None:
        tag = " ✅ (done today)" if done_today else ""
        lines.append(f"📘 Lesson: <b>{esc(topic.title)}</b>{tag}")
    else:
        lines.append("🎓 <b>Roadmap complete!</b> Revisions keep your skills sharp.")
    if due_count > 0:
        lines.append(f"🔁 Reviews due: <b>{due_count}</b>")
    else:
        lines.append("🔁 Reviews due: none")
    if not has_todo:
        lines.append("\n🌟 You're all caught up. Rest or get ahead — your call!")
    return "\n".join(lines), today_kb(has_lesson and not done_today, due_count), has_todo


async def today_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        user, state, _ = await ensure_user(session, update.effective_user)
        text, kb, _ = await today_view(session, user, state)
    await send_html(update.effective_message, text, kb=kb)
