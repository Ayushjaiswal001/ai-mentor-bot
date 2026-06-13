"""/assessment — the weekly checkpoint: an 6–8 question quiz across recent topics."""

from telegram import Message, Update
from telegram.ext import ContextTypes

from app.agents.llm_router import LLMBudgetExceeded, LLMUnavailable
from app.bot.formatting import esc, send_html
from app.bot.handlers import quiz as quiz_handler
from app.bot.users import ensure_user
from app.db.models import User, UserState
from app.db.session import SessionLocal
from app.engines import assessment as assessment_engine

MSG_NONE = (
    "📊 No weekly assessment yet — finish at least one lesson with /learn first, "
    "then I can test you across what you've learned!"
)
MSG_PREP = "📝 Building your weekly assessment across recent topics… (~20s)"


async def assessment_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        user, state, _ = await ensure_user(session, update.effective_user)
        await begin(update.effective_message, session, user, state)


async def begin(message: Message, session, user: User, state: UserState) -> None:
    await message.reply_html(MSG_PREP)
    try:
        result = await assessment_engine.start(session, user, state)
    except LLMBudgetExceeded:
        await send_html(message, "🛑 Daily AI budget reached — assessment tomorrow!")
        return
    except LLMUnavailable:
        await send_html(message, "😵 Can't reach my AI brain right now. Try again in a minute.")
        return
    if result is None:
        await send_html(message, MSG_NONE)
        return
    quiz, attempt = result
    topics = quiz.questions_json.get("topics", [])
    await send_html(
        message,
        f"📊 <b>Weekly Assessment</b>\nCovering: {esc(', '.join(topics))}\n"
        f"{len(quiz_handler.quiz_engine.questions_of(quiz))} questions — let's go!",
    )
    await quiz_handler.send_question(message, quiz, attempt, 0)


def render_weekly_report(r: dict) -> str:
    bar = "🟩" * r["n_correct"] + "🟥" * (r["n_total"] - r["n_correct"])
    lines = [
        f"📊 <b>Weekly Assessment: {r['n_correct']}/{r['n_total']} ({r['score']:.0f}%)</b>",
        bar,
    ]
    if r["trend"] is not None:
        arrow = "▲" if r["trend"] > 0 else ("▼" if r["trend"] < 0 else "→")
        lines.append(f"{arrow} {abs(r['trend']):.0f} pts vs last week")
    if r["weak_tags"]:
        lines.append(f"\n🎯 <b>Focus next week:</b> {esc(', '.join(r['weak_tags']))}")
    else:
        lines.append("\n🌟 Clean sweep — no weak areas flagged!")
    lines.append(f"\n🔥 Streak: <b>{r['streak']}</b> · ⭐ XP: <b>{r['xp_total']}</b>")
    return "\n".join(lines)
