from dataclasses import dataclass
from html import escape
import re

from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.error import TelegramError
from telegram.constants import ParseMode
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from pathwayai_backend.config import Settings
from pathwayai_backend.integrations.base import IntegrationError


@dataclass(frozen=True)
class TelegramDelivery:
    delivered: bool
    message_id: str | None = None


@dataclass(frozen=True)
class InlineAction:
    text: str
    callback_data: str


class TelegramClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        retry=retry_if_exception_type(TelegramError),
        reraise=True,
    )
    async def send_message(
        self,
        text: str,
        *,
        chat_id: str | None = None,
        inline_actions: list[InlineAction] | None = None,
        remove_keyboard: bool = False,
    ) -> TelegramDelivery:
        if not self.settings.telegram_bot_token:
            raise IntegrationError("TELEGRAM_BOT_TOKEN is not configured")
        destination = chat_id or self.settings.telegram_chat_id
        if not destination:
            raise IntegrationError("TELEGRAM_CHAT_ID is not configured")
        bot = Bot(token=self.settings.telegram_bot_token.get_secret_value())
        try:
            async with bot:
                message = await bot.send_message(
                    chat_id=destination,
                    text=self._format_html(text),
                    parse_mode=ParseMode.HTML,
                    reply_markup=self._message_markup(inline_actions, remove_keyboard),
                )
        except TelegramError as exc:
            raise IntegrationError(f"Telegram delivery failed: {exc}") from exc
        return TelegramDelivery(delivered=True, message_id=str(message.message_id))

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        retry=retry_if_exception_type(TelegramError),
        reraise=True,
    )
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        retry=retry_if_exception_type(TelegramError),
        reraise=True,
    )
    async def send_document(
        self,
        *,
        chat_id: str | None = None,
        filename: str,
        content: bytes,
        caption: str | None = None,
    ) -> TelegramDelivery:
        if not self.settings.telegram_bot_token:
            raise IntegrationError("TELEGRAM_BOT_TOKEN is not configured")
        destination = chat_id or self.settings.telegram_chat_id
        if not destination:
            raise IntegrationError("TELEGRAM_CHAT_ID is not configured")
        bot = Bot(token=self.settings.telegram_bot_token.get_secret_value())
        from io import BytesIO

        buffer = BytesIO(content)
        buffer.name = filename
        try:
            async with bot:
                message = await bot.send_document(
                    chat_id=destination,
                    document=buffer,
                    filename=filename,
                    caption=caption,
                )
        except TelegramError as exc:
            raise IntegrationError(f"Telegram document delivery failed: {exc}") from exc
        return TelegramDelivery(delivered=True, message_id=str(message.message_id))

    async def pin_message(
        self, *, chat_id: str, message_id: str
    ) -> bool:
        if not self.settings.telegram_bot_token:
            raise IntegrationError("TELEGRAM_BOT_TOKEN is not configured")
        bot = Bot(token=self.settings.telegram_bot_token.get_secret_value())
        try:
            async with bot:
                await bot.pin_chat_message(
                    chat_id=chat_id,
                    message_id=int(message_id),
                    disable_notification=True,
                )
        except TelegramError:
            return False
        return True

    async def edit_message(
        self,
        *,
        chat_id: str,
        message_id: str,
        text: str,
    ) -> bool:
        if not self.settings.telegram_bot_token:
            raise IntegrationError("TELEGRAM_BOT_TOKEN is not configured")
        bot = Bot(token=self.settings.telegram_bot_token.get_secret_value())
        try:
            async with bot:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=int(message_id),
                    text=self._format_html(text),
                    parse_mode=ParseMode.HTML,
                )
        except TelegramError as exc:
            raise IntegrationError(f"Telegram edit failed: {exc}") from exc
        return True

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        retry=retry_if_exception_type(TelegramError),
        reraise=True,
    )
    async def answer_callback(self, callback_query_id: str, text: str) -> None:
        if not self.settings.telegram_bot_token:
            raise IntegrationError("TELEGRAM_BOT_TOKEN is not configured")
        bot = Bot(token=self.settings.telegram_bot_token.get_secret_value())
        try:
            async with bot:
                await bot.answer_callback_query(
                    callback_query_id=callback_query_id,
                    text=text[:200],
                )
        except TelegramError as exc:
            raise IntegrationError(f"Telegram callback acknowledgement failed: {exc}") from exc

    @staticmethod
    def _format_html(text: str) -> str:
        escaped = escape(text)
        return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped, flags=re.DOTALL)

    @staticmethod
    def _message_markup(
        inline_actions: list[InlineAction] | None,
        remove_keyboard: bool,
    ) -> InlineKeyboardMarkup | ReplyKeyboardRemove | None:
        if inline_actions:
            rows: list[list[InlineKeyboardButton]] = []
            for index in range(0, len(inline_actions), 2):
                rows.append(
                    [
                        InlineKeyboardButton(
                            text=action.text, callback_data=action.callback_data
                        )
                        for action in inline_actions[index : index + 2]
                    ]
                )
            return InlineKeyboardMarkup(rows)
        if remove_keyboard:
            return ReplyKeyboardRemove()
        return None
