"""Typed application settings. All env vars are declared here — see .env.example."""

import re

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str = ""
    allowed_tg_user_ids: str = ""  # comma-separated numeric ids

    gemini_api_key: str = ""
    groq_api_key: str = ""
    openai_api_key: str = ""

    # "provider:model" strings — model rotation is a config change, not a code change
    llm_t0: str = "gemini:gemini-2.0-flash-lite"
    llm_t1: str = "gemini:gemini-2.5-flash"
    llm_t2: str = "gemini:gemini-2.5-pro"

    daily_t1_cap: int = 30
    daily_t2_cap: int = 6
    freetext_daily_cap: int = 15

    database_url: str = "sqlite+aiosqlite:///./data/mentor.db"
    mode: str = "polling"  # polling | webhook
    admin_token: str = ""
    webhook_secret: str = ""

    @field_validator("database_url")
    @classmethod
    def normalize_db_url(cls, v: str) -> str:
        """Accept a raw Neon/Heroku-style Postgres URL and adapt it for SQLAlchemy+asyncpg."""
        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://") :]
        if v.startswith("postgresql://"):
            v = "postgresql+asyncpg://" + v[len("postgresql://") :]
        if v.startswith("postgresql+asyncpg://"):
            v = v.replace("sslmode=", "ssl=")
            v = re.sub(r"channel_binding=[^&]*&?", "", v)
            v = v.replace("?&", "?").rstrip("?&")
        return v

    @property
    def allowed_ids(self) -> set[int]:
        return {int(x) for x in self.allowed_tg_user_ids.split(",") if x.strip()}


settings = Settings()
