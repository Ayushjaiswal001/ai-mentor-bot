"""Allowlist gatekeeper (group -1) and global error boundary."""

import logging

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

from app.config import settings
from app.db.models import Event
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


async def gatekeeper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    allowed = settings.allowed_ids
    if user is not None and (not allowed or user.id in allowed):
        return
    if update.effective_message:
        await update.effective_message.reply_text(
            "🙏 This is a private mentor bot. It only serves its owner."
        )
    raise ApplicationHandlerStop


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("handler error", exc_info=context.error)
    try:
        async with SessionLocal() as session:
            session.add(Event(type="error", payload_json={"error": str(context.error)[:500]}))
            await session.commit()
    except Exception:
        logger.exception("failed to persist error event")
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ Something went wrong on my side. Give it another try in a moment."
            )
        except Exception:
            pass
