"""Single choke point for outbound text: small-Markdown → Telegram HTML, chunking, sending.

Our prompts restrict LLM output to **bold**, `inline code` and ``` fences — this module
converts exactly that subset to Telegram HTML (far more forgiving than MarkdownV2).
"""

import html
import re

from telegram import InlineKeyboardMarkup, Message

CHUNK_LIMIT = 3500  # Telegram hard limit is 4096; leave headroom for tags


def esc(text: object) -> str:
    return html.escape(str(text), quote=False)


def md_to_html(text: str) -> str:
    parts = re.split(r"```[a-zA-Z0-9_+\-]*\n?(.*?)```", text, flags=re.S)
    out: list[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 1:  # inside a code fence
            out.append(f"<pre>{html.escape(part.strip(), quote=False)}</pre>")
        else:
            p = html.escape(part, quote=False)
            p = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", p, flags=re.S)
            p = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", p)
            out.append(p)
    return "".join(out)


def chunk(text: str, limit: int = CHUNK_LIMIT) -> list[str]:
    """Split on paragraph boundaries; hard-split only a single oversized paragraph."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    cur = ""
    for para in text.split("\n\n"):
        while len(para) > limit:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(para[:limit])
            para = para[limit:]
        candidate = f"{cur}\n\n{para}" if cur else para
        if len(candidate) > limit:
            chunks.append(cur)
            cur = para
        else:
            cur = candidate
    if cur:
        chunks.append(cur)
    return chunks


async def send_html(
    message: Message, text: str, kb: InlineKeyboardMarkup | None = None
) -> None:
    parts = chunk(text)
    for i, part in enumerate(parts):
        await message.reply_html(part, reply_markup=kb if i == len(parts) - 1 else None)
