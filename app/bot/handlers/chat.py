"""Free-text router: a pending exercise → grade it; otherwise → Socratic mentor chat."""

from telegram import Update
from telegram.ext import ContextTypes

from app.agents.llm_router import LLMBudgetExceeded, LLMUnavailable
from app.bot.formatting import md_to_html, send_html
from app.bot.handlers.exercise import deliver_grade
from app.bot.handlers.project import PROJECT_SUBMIT_KEY, deliver_review
from app.bot.users import ensure_user
from app.db.models import ProjectProgress
from app.db.session import SessionLocal
from app.engines import exercises, mentor, project_coach

MSG_CAP = (
    "💬 You've used all your free-chat questions for today — that keeps the bot free to run. "
    "Try /learn, /quiz or /revision, and chat resumes tomorrow!"
)
MSG_DOWN = "😵 Can't reach my AI brain right now. Try again in a minute."
MSG_GRADING = "🔍 Reading your solution…"
MSG_THINKING = "🤔 Thinking…"


async def free_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    text = (message.text or "").strip()
    if not text:
        return
    async with SessionLocal() as session:
        user, state, _ = await ensure_user(session, update.effective_user)

        # 1) Finished-project submission (user tapped "Submit project")
        pp_id = context.user_data.pop(PROJECT_SUBMIT_KEY, None)
        if pp_id is not None:
            pp = await session.get(ProjectProgress, pp_id)
            if pp is not None and pp.status != "done":
                await message.reply_html("🔍 Reviewing your project…")
                try:
                    result = await project_coach.review_final(session, user, state, pp, text)
                except LLMBudgetExceeded:
                    await message.reply_html("🛑 Daily AI budget reached — I'll review tomorrow.")
                    return
                except LLMUnavailable:
                    await message.reply_html(MSG_DOWN)
                    return
                await deliver_review(message, project_coach.plan_of(pp).title, result)
                return

        # 2) Pending exercise submission
        pending = await exercises.get_pending(session, user, state)
        if pending is not None:
            await message.reply_html(MSG_GRADING)
            try:
                result = await exercises.submit(session, user, state, pending, text)
            except LLMBudgetExceeded:
                await message.reply_html("🛑 Daily AI budget reached — I'll grade this tomorrow.")
                return
            except LLMUnavailable:
                await message.reply_html(MSG_DOWN)
                return
            await deliver_grade(message, pending, result)
            return

        # No pending exercise → Socratic mentor chat
        await message.chat.send_action("typing")
        try:
            answer = await mentor.chat(session, user, state, text)
        except mentor.FreeTextCapReached:
            await message.reply_html(MSG_CAP)
            return
        except LLMBudgetExceeded:
            await message.reply_html(MSG_CAP)
            return
        except LLMUnavailable:
            await message.reply_html(MSG_DOWN)
            return
        await send_html(message, md_to_html(answer))
