"""/project — propose a phase project, coach it step by step, review the finished build."""

from telegram import Message, Update
from telegram.ext import ContextTypes

from app.agents.llm_router import LLMBudgetExceeded, LLMUnavailable
from app.bot.formatting import esc, md_to_html, send_html
from app.bot.keyboards import project_start_kb, project_step_kb, project_submit_kb
from app.bot.users import ensure_user
from app.db.models import ProjectProgress, User, UserState
from app.db.session import SessionLocal
from app.engines import project_coach

MSG_NONE = "🧱 No project for your current phase yet — keep learning with /learn!"
MSG_PLANNING = "🧭 Designing your project plan… (~20s)"
MSG_BUDGET = "🛑 Daily AI budget reached — try /project again tomorrow."
MSG_DOWN = "😵 Can't reach my AI brain right now. Try again in a minute."
PROJECT_SUBMIT_KEY = "project_submit"


async def project_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        user, state, _ = await ensure_user(session, update.effective_user)
        pp = await project_coach.get_in_progress(session, user, state)
        if pp is not None:
            if pp.status == "active":
                await deliver_step(update.effective_message, pp)
            else:
                await show_overview(update.effective_message, pp)
            return
        await update.effective_message.reply_html(MSG_PLANNING)
        try:
            result = await project_coach.propose_next(session, user, state)
        except LLMBudgetExceeded:
            await update.effective_message.reply_html(MSG_BUDGET)
            return
        except LLMUnavailable:
            await update.effective_message.reply_html(MSG_DOWN)
            return
        if result is None:
            await update.effective_message.reply_html(MSG_NONE)
            return
        pp, _project = result
        await show_overview(update.effective_message, pp)


async def show_overview(message: Message, pp: ProjectProgress) -> None:
    plan = project_coach.plan_of(pp)
    await send_html(
        message,
        f"🚀 <b>Project: {esc(plan.title)}</b>\n\n{md_to_html(plan.overview)}\n\n"
        f"📋 <b>{pp.total_steps} steps</b>. Ready?",
        kb=project_start_kb(pp.id),
    )


async def deliver_step(message: Message, pp: ProjectProgress) -> None:
    step = project_coach.current_step(pp)
    if step is None:
        await prompt_final(message, pp)
        return
    await send_html(
        message,
        f"🔨 <b>Step {pp.current_step + 1}/{pp.total_steps}: {esc(step.title)}</b>\n\n"
        f"🎯 {esc(step.goal)}\n\n{md_to_html(step.details_md)}\n\n"
        f"✅ <b>Done when:</b> {esc(step.done_when)}",
        kb=project_step_kb(pp.id),
    )


async def prompt_final(message: Message, pp: ProjectProgress) -> None:
    plan = project_coach.plan_of(pp)
    await send_html(
        message,
        f"🎉 <b>All {pp.total_steps} steps of «{esc(plan.title)}» done!</b>\n\n"
        "Tap below, then send a short description or a GitHub link to your finished project "
        "and I'll review it like a mentor.",
        kb=project_submit_kb(pp.id),
    )


async def on_start(message: Message, session, pp_id: int) -> None:
    pp = await session.get(ProjectProgress, pp_id)
    if pp is None or pp.status == "done":
        return
    await project_coach.start(session, pp)
    await deliver_step(message, pp)


async def on_next(message: Message, session, user: User, state: UserState, pp_id: int) -> None:
    pp = await session.get(ProjectProgress, pp_id)
    if pp is None or pp.status != "active":
        return
    res = await project_coach.advance(session, user, state, pp)
    if res["completed_all"]:
        await prompt_final(message, pp)
    else:
        await deliver_step(message, pp)


async def on_guide(message: Message, session, user: User, state: UserState, pp_id: int) -> None:
    pp = await session.get(ProjectProgress, pp_id)
    if pp is None or pp.status != "active":
        return
    try:
        hint = await project_coach.guidance(session, user, state, pp)
    except (LLMBudgetExceeded, LLMUnavailable):
        await send_html(message, MSG_DOWN)
        return
    await send_html(message, f"💡 {md_to_html(hint)}")


async def on_submit(
    message: Message, context: ContextTypes.DEFAULT_TYPE, session, pp_id: int
) -> None:
    pp = await session.get(ProjectProgress, pp_id)
    if pp is None or pp.status == "done":
        return
    context.user_data[PROJECT_SUBMIT_KEY] = pp_id
    await send_html(
        message, "📤 Send your project description or GitHub link now and I'll review it."
    )


async def deliver_review(message: Message, plan_title: str, result) -> None:
    head = "🎓 <b>Project complete!</b>" if result.passed else "🛠 <b>Almost there</b>"
    lines = [f"{head}  (score {result.score}/100)", ""]
    if result.strengths:
        lines.append("<b>Strengths</b>")
        lines += [f"• {esc(s)}" for s in result.strengths]
    if result.issues:
        lines.append("\n<b>To improve</b>")
        lines += [f"• {esc(i)}" for i in result.issues]
    lines.append(f"\n🧭 {md_to_html(result.suggestion)}")
    if result.passed:
        lines.append(f"\n🏆 <b>«{esc(plan_title)}»</b> added to your portfolio. Onward!")
    await send_html(message, "\n".join(lines))
