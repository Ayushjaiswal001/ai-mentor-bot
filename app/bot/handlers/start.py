"""/start — onboarding (new user) or welcome-back summary (returning user)."""

from telegram import CallbackQuery, Update
from telegram.ext import ContextTypes

from app.bot.formatting import esc, send_html
from app.bot.keyboards import hour_kb
from app.bot.users import ensure_user
from app.db.models import User
from app.db.session import SessionLocal

WELCOME_NEW = (
    "👋 Hey <b>{name}</b>! I'm your personal AI mentor.\n\n"
    "Together we'll go from Python basics all the way to building multi-agent AI systems "
    "— with daily lessons, quizzes, spaced revision, and real projects.\n\n"
    "📚 Lessons are <b>on-demand</b>: hit /learn whenever you're ready, stop any time, "
    "and resume right where you left off.\n\n"
    "Want a daily reminder nudge? Pick a time (IST):"
)

WELCOME_BACK = (
    "👋 Welcome back, <b>{name}</b>!\n\n"
    "🔥 Streak: <b>{streak}</b> · ⭐ XP: <b>{xp}</b>\n"
    "▶️ Current topic: <b>{topic}</b>\n\n"
    "/learn — start or resume your lesson\n"
    "/quiz — test yourself · /progress — your stats"
)

TOUR = (
    "✅ Done! Here's your toolkit:\n\n"
    "/learn — start or resume a lesson (10–20 min)\n"
    "/quiz — 5 quick questions on the current topic\n"
    "/progress — streak, XP, weak topics\n"
    "/roadmap — the full journey map\n"
    "/help — how my teaching works\n\n"
    "Ready? Send /learn to begin <b>Phase 1: Python Fundamentals</b> 🚀"
)


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    async with SessionLocal() as session:
        user, state, created = await ensure_user(session, update.effective_user)
        if created:
            await send_html(
                message, WELCOME_NEW.format(name=esc(user.first_name or "there")), kb=hour_kb()
            )
            return
        from app.db.models import Topic

        topic = (
            await session.get(Topic, state.current_topic_id) if state.current_topic_id else None
        )
        await send_html(
            message,
            WELCOME_BACK.format(
                name=esc(user.first_name or "there"),
                streak=state.streak_count,
                xp=state.xp,
                topic=esc(topic.title) if topic else "Roadmap complete 🎉",
            ),
        )


async def on_hour_choice(query: CallbackQuery, session, user: User, arg: str) -> None:
    user.reminder_hour = None if arg == "off" else int(arg)
    await session.commit()
    label = "🔕 No reminders — you're in full control." if arg == "off" else (
        f"⏰ Reminder set for {arg}:00 IST (starts working once scheduling ships)."
    )
    await send_html(query.message, f"{label}\n\n{TOUR}")
