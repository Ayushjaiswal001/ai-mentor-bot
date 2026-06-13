"""/progress, /roadmap, /help and the free-text fallback."""

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.formatting import esc, send_html
from app.bot.users import ensure_user
from app.db.session import SessionLocal
from app.engines import progress

HELP = (
    "🧭 <b>How your mentor works</b>\n\n"
    "/today — your daily plan at a glance\n"
    "/learn — start or resume a lesson (10–20 min, stop any time)\n"
    "/quiz — 5 questions on your current topic\n"
    "/revision — spaced-repetition reviews of past topics\n"
    "/exercise — a coding exercise I grade with feedback\n"
    "/project — build a real project, coached step by step\n"
    "/assessment — your weekly checkpoint across recent topics\n"
    "/progress — streak, XP, scores, weak spots\n"
    "/roadmap — the journey: Python → FastAPI → ML → Transformers → LLMs → LangGraph\n"
    "/settings — difficulty & reminder time\n\n"
    "💬 <b>Just type a question</b> anytime and I'll answer it Socratically.\n\n"
    "<b>The method:</b>\n"
    "• Active recall — I ask before I tell.\n"
    "• Adaptive difficulty — score ≥80% advances you; &lt;50% gets a simpler retake.\n"
    "• Spaced repetition — topics return at 1/3/7/14/30 days; pass to push them further out.\n"
    "• Project-based — every phase ends in a project for your portfolio.\n"
    "• Weekly checkpoint — every Sunday, /assessment scores how much stuck.\n\n"
    "Next up: the multi-agent upgrade 🤖"
)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_html(update.effective_message, HELP)


async def progress_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        user, state, _ = await ensure_user(session, update.effective_user)
        r = await progress.report(session, user, state)
    lines = [
        "📊 <b>Your progress</b>\n",
        f"📍 Phase: <b>{esc(r['current_phase'])}</b>",
        f"▶️ Topic: <b>{esc(r['current_topic'])}</b>",
        f"✅ Topics completed: <b>{r['lessons_done']}</b>",
        f"🔥 Streak: <b>{r['streak']}</b> (best {r['longest_streak']})",
        f"⭐ XP: <b>{r['xp']}</b>",
    ]
    if r["avg_recent_score"] is not None:
        lines.append(f"🎯 Avg of last 5 quizzes: <b>{r['avg_recent_score']}%</b>")
    if r["weak_topics"]:
        lines.append(f"🔍 Weak topics: {esc(', '.join(r['weak_topics']))}")
    if not r["has_history"]:
        lines.append("\nNo lessons finished yet — send /learn to start your journey! 🚀")
    await send_html(update.effective_message, "\n".join(lines))


async def roadmap_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        user, state, _ = await ensure_user(session, update.effective_user)
        view = await progress.roadmap_view(session, user, state)
    lines = ["🗺 <b>Your roadmap</b>\n"]
    for ph in view:
        if ph["current"]:
            icon = "▶️"
        elif ph["total"] > 0 and ph["done"] >= ph["total"]:
            icon = "✅"
        else:
            icon = "🔒"
        suffix = f" ({ph['done']}/{ph['total']})" if ph["total"] else ""
        lines.append(f"{icon} {esc(ph['title'])}{suffix}")
    await send_html(update.effective_message, "\n".join(lines))
