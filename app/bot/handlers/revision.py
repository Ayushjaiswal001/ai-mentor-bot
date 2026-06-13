"""/revision — run the most-due spaced-repetition review (3 questions, ladder-graded)."""

from telegram import Message, Update
from telegram.ext import ContextTypes

from app.agents.llm_router import LLMBudgetExceeded, LLMUnavailable
from app.bot.formatting import send_html
from app.bot.handlers import quiz as quiz_handler
from app.bot.users import ensure_user
from app.db.models import User, UserState
from app.db.session import SessionLocal
from app.engines import revision as revision_engine

MSG_NONE = (
    "🎉 <b>No reviews due right now!</b>\n"
    "Spaced repetition brings topics back at 1, 3, 7, 14 and 30 days. "
    "Keep learning with /learn and they'll show up here when it's time."
)
MSG_PREP = "🔁 Pulling up your review…"


async def revision_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        user, state, _ = await ensure_user(session, update.effective_user)
        await begin(update.effective_message, session, user, state)


async def begin(message: Message, session, user: User, state: UserState) -> None:
    due = await revision_engine.due(session, user)
    if not due:
        await send_html(message, MSG_NONE)
        return
    item, topic = due[0]
    await message.reply_html(f"{MSG_PREP}  (<b>{len(due)}</b> due)")
    try:
        quiz, attempt, topic = await revision_engine.start_revision(session, user, state, item)
    except LLMBudgetExceeded:
        await send_html(message, "🛑 Daily AI budget reached — reviews resume tomorrow!")
        return
    except LLMUnavailable:
        await send_html(message, "😵 Can't reach my AI brain right now. Try again in a minute.")
        return
    await send_html(message, f"🔁 <b>Review: {topic.title}</b>")
    await quiz_handler.send_question(message, quiz, attempt, 0)
