"""/quiz — 5 MCQs with inline buttons, per-question feedback, adaptive final report."""

from telegram import Message, Update
from telegram.ext import ContextTypes

from app.agents.llm_router import LLMBudgetExceeded, LLMUnavailable
from app.bot.formatting import esc, md_to_html, send_html
from app.bot.handlers.learn import options_text
from app.bot.keyboards import next_lesson_kb, options_kb, revise_kb
from app.bot.users import ensure_user
from app.db.models import Quiz, QuizAttempt, Topic, User, UserState
from app.db.session import SessionLocal
from app.engines import quiz as quiz_engine

MSG_PREPARING = "🧠 Preparing 5 questions… (~15 seconds)"
MSG_NO_TOPIC = "🎓 Roadmap complete — nothing left to quiz! Try /revision once it ships."


async def quiz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        user, state, _ = await ensure_user(session, update.effective_user)
        if state.current_topic_id is None:
            await update.effective_message.reply_html(MSG_NO_TOPIC)
            return
        await begin(update.effective_message, session, user, state, state.current_topic_id)


async def begin(
    message: Message, session, user: User, state: UserState, topic_id: int
) -> None:
    topic = await session.get(Topic, topic_id)
    if topic is None:
        await message.reply_html("Hmm, I can't find that topic any more. Send /learn!")
        return
    await message.reply_html(MSG_PREPARING)
    try:
        quiz, attempt = await quiz_engine.start_for_topic(session, user, state, topic)
    except LLMBudgetExceeded:
        await message.reply_html("🛑 Daily AI budget reached — quiz tomorrow, promise!")
        return
    except LLMUnavailable:
        await message.reply_html("😵 Can't reach my AI brain right now. Try again in a minute.")
        return
    await send_question(message, quiz, attempt, 0)


async def send_question(message: Message, quiz: Quiz, attempt: QuizAttempt, q_idx: int) -> None:
    qs = quiz_engine.questions_of(quiz)
    q = qs[q_idx]
    await send_html(
        message,
        f"🎯 <b>Question {q_idx + 1}/{len(qs)}</b>\n\n{md_to_html(q.question)}\n\n"
        + options_text(q.options),
        kb=options_kb("q", attempt.id, q_idx, len(q.options)),
    )


async def on_answer(
    message: Message,
    session,
    user: User,
    state: UserState,
    attempt_id: int,
    q_idx: int,
    choice: int,
) -> None:
    attempt = await session.get(QuizAttempt, attempt_id)
    if attempt is None or attempt.finished_at is not None:
        return  # stale tap
    quiz = await session.get(Quiz, attempt.quiz_id)
    fb = quiz_engine.record_answer(attempt, quiz, q_idx, choice)
    if fb is None:
        return  # double tap on the same question
    await session.commit()

    if fb["correct"]:
        await send_html(message, f"✅ <b>Correct!</b> {md_to_html(fb['explanation'])}")
    else:
        await send_html(
            message,
            f"❌ Correct answer: <b>{esc(fb['correct_option'])}</b>\n"
            f"{md_to_html(fb['explanation'])}",
        )

    if fb["answered"] < fb["total"]:
        await send_question(message, quiz, attempt, q_idx + 1)
        return

    report = await quiz_engine.finalize(session, user, state, quiz, attempt)
    if report["kind"] == "revision":
        await send_html(message, render_revision_report(report), kb=revision_followup_kb(report))
    elif report["kind"] == "weekly":
        from app.bot.handlers.assessment import render_weekly_report

        await send_html(message, render_weekly_report(report))
    else:
        await send_html(message, render_report(report), kb=report_kb(report))


def render_revision_report(r: dict) -> str:
    head = "✅ <b>Review passed!</b>" if r["passed"] else "🔁 <b>Needs another pass</b>"
    lines = [f"{head}  ({r['n_correct']}/{r['n_total']})", ""]
    if r["retired"]:
        lines.append("🏆 You've mastered this topic — it graduates from revision!")
    elif r["passed"]:
        lines.append(f"📈 Great — I'll bring it back in <b>{r['next_interval_days']} days</b>.")
    else:
        lines.append(
            f"No worries — I'll resurface it sooner (in <b>{r['next_interval_days']} day(s)</b>) "
            "so it sticks."
        )
    if r["remaining_due"] > 0:
        lines.append(f"\n📚 <b>{r['remaining_due']}</b> more review(s) due today.")
    else:
        lines.append("\n🎉 That's all your reviews for today. Nicely done!")
    lines.append(f"🔥 Streak: <b>{r['streak']}</b> · ⭐ +{r['xp_gain']} XP (total {r['xp_total']})")
    return "\n".join(lines)


def revision_followup_kb(r: dict):
    if r["remaining_due"] > 0:
        return revise_kb(r["remaining_due"])
    return None


def render_report(r: dict) -> str:
    bar = "🟩" * r["n_correct"] + "🟥" * (r["n_total"] - r["n_correct"])
    lines = [f"🏁 <b>Quiz done: {r['n_correct']}/{r['n_total']} ({r['score']:.0f}%)</b>", bar, ""]
    if r["outcome"] == "advance":
        if r["next_topic_title"]:
            lines.append(f"🚀 Excellent! Next up: <b>{esc(r['next_topic_title'])}</b>.")
        else:
            lines.append("🚀 Excellent — and that was the FINAL topic! 🎉")
    elif r["outcome"] == "flagged":
        lines.append(
            "👍 Passed — but I'll keep an eye on this topic and we'll revisit it in revision."
        )
        if r["next_topic_title"]:
            lines.append(f"Next up: <b>{esc(r['next_topic_title'])}</b>.")
    else:
        lines.append(
            "💪 No stress — this one needs another pass. I've prepared a <b>simpler take</b>: "
            "hit /learn to redo it at a gentler pace."
        )
    if r["weak_tags"]:
        lines.append(f"\n🔍 Watch out for: {esc(', '.join(r['weak_tags']))}")
    lines.append(
        f"\n🔥 Streak: <b>{r['streak']}</b> · ⭐ +{r['xp_gain']} XP (total {r['xp_total']})"
    )
    return "\n".join(lines)


def report_kb(r: dict):
    if r["outcome"] == "repeat":
        return next_lesson_kb("📘 Relearn this topic")
    if r["next_topic_title"]:
        return next_lesson_kb()
    return None
