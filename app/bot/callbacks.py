"""Central callback-query router. Formats documented in keyboards.py."""

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.handlers import learn, quiz, revision, start
from app.bot.users import ensure_user
from app.db.session import SessionLocal


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    message = update.effective_message
    if message is None:
        return
    parts = (query.data or "").split(":")

    async with SessionLocal() as session:
        user, state, _ = await ensure_user(session, query.from_user)
        match parts:
            case ["ob", "hour", arg]:
                await start.on_hour_choice(query, session, user, arg)
            case ["nav", "cont", lesson_id]:
                await learn.on_continue(message, session, int(lesson_id))
            case ["nav", "learn"]:
                await learn.start_flow(message, session, user, state)
            case ["nav", "quiz", topic_id]:
                await quiz.begin(message, session, user, state, int(topic_id))
            case ["nav", "revise"]:
                await revision.begin(message, session, user, state)
            case ["nav", "later"]:
                await message.reply_html("👍 No rush — the quiz waits. Send /quiz when ready.")
            case ["ck", lesson_id, sec_idx, choice]:
                await learn.on_checkpoint(
                    message, context, session, int(lesson_id), int(sec_idx), int(choice)
                )
            case ["q", attempt_id, q_idx, choice]:
                await quiz.on_answer(
                    message, session, user, state, int(attempt_id), int(q_idx), int(choice)
                )
