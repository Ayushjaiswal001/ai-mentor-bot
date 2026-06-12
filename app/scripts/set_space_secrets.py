"""Push runtime secrets from local .env to a Hugging Face Space.

Usage: python -m app.scripts.set_space_secrets <user/space> <hf_write_token>
Values are read locally and sent only to the HF API; they are never printed.
"""

import re
import sys
from pathlib import Path

import httpx

KEYS = [
    "TELEGRAM_BOT_TOKEN",
    "ALLOWED_TG_USER_IDS",
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "OPENAI_API_KEY",
    "DATABASE_URL",
]


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = re.split(r"\s+#", value)[0].strip()
        values[key.strip()] = value
    return values


def main() -> None:
    space_id, token = sys.argv[1], sys.argv[2]
    values = parse_env(Path(".env"))
    for key in KEYS:
        value = values.get(key, "")
        if not value:
            print(f"  skip {key} (empty)")
            continue
        r = httpx.post(
            f"https://huggingface.co/api/spaces/{space_id}/secrets",
            headers={"Authorization": f"Bearer {token}"},
            json={"key": key, "value": value},
            timeout=30,
        )
        print(f"  set {key}: HTTP {r.status_code}")


if __name__ == "__main__":
    main()
