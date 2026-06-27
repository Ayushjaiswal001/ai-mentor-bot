import asyncio

from telegram import Bot, BotCommand, MenuButtonCommands, ReplyKeyboardRemove

from pathwayai_backend.config import get_settings


async def _set_webhook() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
    if not settings.telegram_webhook_secret:
        raise RuntimeError("TELEGRAM_WEBHOOK_SECRET is required")
    webhook_url = f"{settings.app_base_url.rstrip('/')}/telegram/webhook"
    bot = Bot(settings.telegram_bot_token.get_secret_value())
    async with bot:
        await bot.set_my_commands(
            [
                # Daily-use actions first so the menu picker stays fast.
                BotCommand("goals", "View or set today's goals"),
                BotCommand("log", "Log what you built or learned"),
                BotCommand("ask", "Ask a technical question"),
                BotCommand("status", "Streak, goal stats, and readiness"),
                # Recall and review.
                BotCommand("logs", "Show recent learning logs"),
                BotCommand("stories", "Interview stories grouped by topic"),
                BotCommand("mastery", "Topic mastery and due re-quizzes"),
                BotCommand("review", "Re-quiz the next due topic"),
                BotCommand("search", "Semantic search across logs and memory"),
                # Deeper sessions.
                BotCommand("mock", "Start a mock interview on a topic"),
                BotCommand("codereview", "Structured review of a code snippet"),
                BotCommand("activity", "GitHub and LeetCode activity"),
                BotCommand("next", "Show the latest weekly plan"),
                BotCommand("export", "Markdown export of this week / month"),
                # Meta / setup.
                BotCommand("help", "How to use the bot"),
                BotCommand("start", "Run the 3-question intake"),
                BotCommand("forgetme", "Wipe stored memory (requires confirm)"),
                BotCommand("version", "Show the running build version"),
            ]
        )
        # Pin the chat menu button to the commands list so the ≡ icon opens
        # the slash-command picker instead of the default "Menu" label.
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        await bot.set_webhook(
            url=webhook_url,
            secret_token=settings.telegram_webhook_secret.get_secret_value(),
            allowed_updates=["message", "edited_message", "callback_query"],
            drop_pending_updates=False,
        )
    print(f"Telegram webhook configured: {webhook_url}")


def set_telegram_webhook() -> None:
    asyncio.run(_set_webhook())


async def _backfill_embeddings() -> None:
    from pathwayai_backend.db.repositories import Repository
    from pathwayai_backend.db.session import Database
    from pathwayai_backend.llm.embeddings import EmbeddingGateway

    settings = get_settings()
    embeddings = EmbeddingGateway(settings)
    if not embeddings.enabled:
        raise RuntimeError(
            "HUGGINGFACE_API_TOKEN is required to compute embeddings"
        )
    database = Database(settings)
    if not database.configured:
        raise RuntimeError("DATABASE_URL is required")
    embedded = skipped = 0
    try:
        async for session in database.session():
            repository = Repository(session)
            while True:
                logs = await repository.logs_missing_embedding(limit=50)
                memories = await repository.memories_missing_embedding(limit=50)
                if not logs and not memories:
                    break
                progressed = 0
                for row in (*logs, *memories):
                    vector = await embeddings.embed(row.content)
                    if vector is None:
                        skipped += 1
                        continue
                    row.embedding = vector
                    progressed += 1
                await session.commit()
                embedded += progressed
                if progressed == 0:
                    # Provider is failing on every remaining row; stop
                    # instead of refetching the same batch forever.
                    break
            break
    finally:
        await database.close()
    print(f"Embedded {embedded} rows, skipped {skipped}.")


def backfill_embeddings() -> None:
    asyncio.run(_backfill_embeddings())


async def _clear_reply_keyboard() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
    if not settings.telegram_chat_id:
        raise RuntimeError("TELEGRAM_CHAT_ID is required")
    bot = Bot(settings.telegram_bot_token.get_secret_value())
    async with bot:
        await bot.send_message(
            chat_id=settings.telegram_chat_id,
            text="Menu cleared. Use the ≡ button for commands.",
            reply_markup=ReplyKeyboardRemove(),
        )
    print(f"Reply keyboard cleared for chat {settings.telegram_chat_id}.")


def clear_reply_keyboard() -> None:
    asyncio.run(_clear_reply_keyboard())
