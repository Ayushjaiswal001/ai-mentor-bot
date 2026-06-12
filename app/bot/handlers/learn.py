"""/learn — generate/resume a lesson and deliver it section by section with checkpoints."""

from telegram import Message, Update
from telegram.ext import ContextTypes

from app.agents.llm_router import LLMBudgetExceeded, LLMUnavailable
from app.agents.schemas import LessonSchema
from app.bot.formatting import esc, md_to_html, send_html
from app.bot.keyboards import continue_kb, options_kb, post_lesson_kb
from app.bot.users import ensure_user
from app.db.models import Lesson, User, UserState
from app.db.session import SessionLocal
from app.engines import learning

SECTION_EMOJI = {"concept": "📘", "example": "🌍", "diagram": "✏️", "code": "💻"}

MSG_GENERATING = "✍️ Crafting your lesson… (~20 seconds)"
MSG_BUDGET = (
    "🛑 Daily AI budget reached — that's the free tier protecting itself.\n"
    "Take a rest day or do some revision. Everything resets at midnight UTC."
)
MSG_LLM_DOWN = "😵 My AI brain is unreachable right now. Try again in a minute."
MSG_DONE = "🎓 You've completed the <b>entire roadmap</b>! Phenomenal work. 🎉"


def options_text(options: list[str]) -> str:
    return "\n".join(f"<b>{i + 1}.</b> {esc(opt)}" for i, opt in enumerate(options))


async def learn_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        user, state, _ = await ensure_user(session, update.effective_user)
        await start_flow(update.effective_message, session, user, state)


async def start_flow(message: Message, session, user: User, state: UserState) -> None:
    resuming = False
    if state.active_lesson_id:
        existing = await session.get(Lesson, state.active_lesson_id)
        resuming = existing is not None and existing.status != "completed"
    if not resuming:
        await message.reply_html(MSG_GENERATING)
    try:
        lesson = await learning.get_or_create_lesson(session, user, state)
    except LLMBudgetExceeded:
        await message.reply_html(MSG_BUDGET)
        return
    except LLMUnavailable:
        await message.reply_html(MSG_LLM_DOWN)
        return
    if lesson is None:
        await send_html(message, MSG_DONE)
        return
    await deliver(message, session, lesson, resumed=resuming)


async def deliver(message: Message, session, lesson: Lesson, resumed: bool = False) -> None:
    """Send sections from progress_idx onward; pause at checkpoints and pacing breaks."""
    content = LessonSchema.model_validate(lesson.content_json)
    secs = content.sections
    idx = lesson.progress_idx

    if lesson.status == "generated":
        await send_html(
            message, f"🎯 <b>{esc(content.title)}</b>\n\n<i>{esc(content.objective)}</i>"
        )
        lesson.status = "in_progress"
    elif resumed and idx < len(secs):
        await send_html(
            message, f"⏪ Resuming <b>{esc(content.title)}</b> — picking up where you stopped."
        )

    while idx < len(secs):
        sec = secs[idx]
        if sec.kind == "checkpoint":
            cp = sec.checkpoint
            await send_html(
                message,
                f"❓ <b>Quick check</b>\n\n{md_to_html(cp.question)}\n\n{options_text(cp.options)}",
                kb=options_kb("ck", lesson.id, idx, len(cp.options)),
            )
            lesson.progress_idx = idx
            await session.commit()
            return
        emoji = SECTION_EMOJI.get(sec.kind, "📘")
        await send_html(
            message, f"{emoji} <b>{esc(sec.title)}</b>\n\n{md_to_html(sec.body_md)}"
        )
        idx += 1
        lesson.progress_idx = idx
        if (
            sec.kind in ("concept", "example")
            and idx < len(secs)
            and secs[idx].kind != "checkpoint"
        ):
            await send_html(
                message, "Take a breath — continue when ready. 😌", kb=continue_kb(lesson.id)
            )
            await session.commit()
            return

    await send_html(
        message,
        "📌 <b>Summary</b>\n" + "\n".join(f"• {esc(s)}" for s in content.summary),
    )
    await send_html(
        message,
        f"📝 <b>Homework</b>\n{md_to_html(content.homework)}\n\n"
        "When you're ready, take the quiz — it decides what we do next!",
        kb=post_lesson_kb(lesson.topic_id),
    )
    await session.commit()


async def on_continue(message: Message, session, lesson_id: int) -> None:
    lesson = await session.get(Lesson, lesson_id)
    if lesson is None or lesson.status == "completed":
        await message.reply_html("That lesson is already wrapped up. Send /learn for the next one!")
        return
    await deliver(message, session, lesson)


async def on_checkpoint(
    message: Message,
    context: ContextTypes.DEFAULT_TYPE,
    session,
    lesson_id: int,
    sec_idx: int,
    choice: int,
) -> None:
    lesson = await session.get(Lesson, lesson_id)
    if lesson is None or lesson.status == "completed" or lesson.progress_idx > sec_idx:
        return  # stale tap on an old keyboard
    content = LessonSchema.model_validate(lesson.content_json)
    cp = content.sections[sec_idx].checkpoint
    attempts_key = f"ck:{lesson_id}:{sec_idx}"

    if choice == cp.correct_index:
        await send_html(message, f"✅ <b>Correct!</b> {md_to_html(cp.explanation)}")
    else:
        attempts = context.user_data.get(attempts_key, 0) + 1
        context.user_data[attempts_key] = attempts
        if attempts == 1:
            await send_html(
                message,
                f"🤔 Not quite. <b>Hint:</b> {md_to_html(cp.hint)}\n\nTap another option above!",
            )
            return  # keyboard stays live for a second try
        correct_opt = cp.options[cp.correct_index]
        await send_html(
            message,
            f"💡 The answer was <b>{esc(correct_opt)}</b>. {md_to_html(cp.explanation)}",
        )
    context.user_data.pop(attempts_key, None)
    lesson.progress_idx = sec_idx + 1
    await session.commit()
    await deliver(message, session, lesson)
