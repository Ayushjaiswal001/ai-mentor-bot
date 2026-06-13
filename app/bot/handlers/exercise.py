"""/exercise — issue a coding exercise; grade the user's next message against a rubric."""

from telegram import Message, Update
from telegram.ext import ContextTypes

from app.agents.llm_router import LLMBudgetExceeded, LLMUnavailable
from app.bot.formatting import esc, md_to_html, send_html
from app.bot.keyboards import exercise_kb, next_lesson_kb
from app.bot.users import ensure_user
from app.db.models import Exercise
from app.db.session import SessionLocal
from app.engines import exercises

MSG_NO_TOPIC = "🎓 No active topic to practise. Finish a lesson first with /learn!"
MSG_GENERATING = "🛠 Designing a coding exercise for you… (~15s)"
MSG_BUDGET = "🛑 Daily AI budget reached — exercises resume tomorrow."
MSG_DOWN = "😵 Can't reach my AI brain right now. Try again in a minute."


async def exercise_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        user, state, _ = await ensure_user(session, update.effective_user)
        if state.current_topic_id is None:
            await update.effective_message.reply_html(MSG_NO_TOPIC)
            return
        pending = await exercises.get_pending(session, user, state)
        if pending is not None:
            await _deliver(update.effective_message, pending)
            return
        await update.effective_message.reply_html(MSG_GENERATING)
        try:
            result = await exercises.issue(session, user, state)
        except LLMBudgetExceeded:
            await update.effective_message.reply_html(MSG_BUDGET)
            return
        except LLMUnavailable:
            await update.effective_message.reply_html(MSG_DOWN)
            return
        if result is None:
            await update.effective_message.reply_html(MSG_NO_TOPIC)
            return
        ex, _schema = result
        await _deliver(update.effective_message, ex)


async def _deliver(message: Message, ex: Exercise) -> None:
    spec = ex.feedback_json or {}
    title = spec.get("title", "Coding exercise")
    body = f"💪 <b>{esc(title)}</b>\n\n{md_to_html(ex.prompt_md)}"
    starter = spec.get("starter")
    if starter:
        body += f"\n\n<b>Starter:</b>\n<pre>{esc(starter)}</pre>"
    body += "\n\n✍️ <i>Reply with your solution as a message and I'll grade it.</i>"
    await send_html(message, body, kb=exercise_kb(ex.id))


async def on_hint(
    message: Message, context: ContextTypes.DEFAULT_TYPE, session, ex_id: int
) -> None:
    ex = await session.get(Exercise, ex_id)
    if ex is None or ex.status != "issued":
        return
    hints = exercises.hints_of(ex)
    key = f"exhint:{ex_id}"
    idx = context.user_data.get(key, 0)
    if idx >= len(hints):
        await send_html(message, "💡 That's all the hints — give it your best shot and submit!")
        return
    await send_html(message, f"💡 <b>Hint {idx + 1}/{len(hints)}</b>\n{md_to_html(hints[idx])}")
    context.user_data[key] = idx + 1


async def on_skip(message: Message, session, ex_id: int) -> None:
    ex = await session.get(Exercise, ex_id)
    if ex is not None and ex.status == "issued":
        await exercises.skip(session, ex)
    await send_html(
        message, "⏭ Skipped. No worries — send /learn to continue or /exercise for another."
    )


async def deliver_grade(message: Message, ex: Exercise, result) -> None:
    head = "✅ <b>Passed!</b>" if result.passed else "🔁 <b>Not quite yet</b>"
    lines = [f"{head}  (score {result.score}/100)", ""]
    if result.strengths:
        lines.append("<b>What you did well</b>")
        lines += [f"• {esc(s)}" for s in result.strengths]
    if result.issues:
        lines.append("\n<b>To fix</b>")
        lines += [f"• {esc(i)}" for i in result.issues]
    lines.append(f"\n🧭 {md_to_html(result.suggestion)}")
    kb = None if result.passed else next_lesson_kb("📘 Review the lesson")
    await send_html(message, "\n".join(lines), kb=kb)
