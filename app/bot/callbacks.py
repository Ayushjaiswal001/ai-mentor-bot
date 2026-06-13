"""Central callback-query router. Formats documented in keyboards.py."""

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.handlers import exercise, learn, project, quiz, revision, start
from app.bot.handlers import settings as settings_h
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
            case ["ex", "hint", ex_id]:
                await exercise.on_hint(message, context, session, int(ex_id))
            case ["ex", "skip", ex_id]:
                await exercise.on_skip(message, session, int(ex_id))
            case ["pj", "start", pp_id]:
                await project.on_start(message, session, int(pp_id))
            case ["pj", "next", pp_id]:
                await project.on_next(message, session, user, state, int(pp_id))
            case ["pj", "guide", pp_id]:
                await project.on_guide(message, session, user, state, int(pp_id))
            case ["pj", "submit", pp_id]:
                await project.on_submit(message, context, session, int(pp_id))
            case ["set", "diff", value]:
                await settings_h.on_difficulty(query, session, user, state, value)
            case ["set", "hour", arg]:
                await settings_h.on_reminder(query, session, user, state, arg)
