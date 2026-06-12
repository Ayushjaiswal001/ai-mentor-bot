"""Telegram Application wiring: handlers, gatekeeper, error boundary, command menu."""

from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    TypeHandler,
    filters,
)

from app.bot import callbacks, middlewares
from app.bot.handlers import info, learn, quiz, start
from app.config import settings

COMMANDS = [
    ("start", "Set up / restart your mentor"),
    ("learn", "Start or resume a lesson"),
    ("quiz", "Quiz on the current topic"),
    ("progress", "Streak, XP, scores"),
    ("roadmap", "The full journey map"),
    ("help", "How this works"),
]


async def _post_init(app: Application) -> None:
    from app.db.session import init_db

    await init_db()
    await app.bot.set_my_commands([BotCommand(c, d) for c, d in COMMANDS])


def build_application() -> Application:
    app = (
        ApplicationBuilder().token(settings.telegram_bot_token).post_init(_post_init).build()
    )
    app.add_handler(TypeHandler(Update, middlewares.gatekeeper), group=-1)
    app.add_handler(CommandHandler("start", start.start_cmd))
    app.add_handler(CommandHandler("learn", learn.learn_cmd))
    app.add_handler(CommandHandler("quiz", quiz.quiz_cmd))
    app.add_handler(CommandHandler("progress", info.progress_cmd))
    app.add_handler(CommandHandler("roadmap", info.roadmap_cmd))
    app.add_handler(CommandHandler("help", info.help_cmd))
    app.add_handler(CallbackQueryHandler(callbacks.on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, info.free_text))
    app.add_error_handler(middlewares.on_error)
    return app
