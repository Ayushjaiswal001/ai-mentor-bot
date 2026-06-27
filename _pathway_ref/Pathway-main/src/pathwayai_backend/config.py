from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "PathwayAI Tutor"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_base_url: str = "http://127.0.0.1:8000"
    log_level: str = "INFO"
    user_timezone: str = "Asia/Kolkata"
    default_user_name: str = "there"
    target_role: str = "Software Engineer"
    job_search_horizon_months: int = 6

    database_url: SecretStr | None = Field(default=None, alias="DATABASE_URL")
    migration_database_url: SecretStr | None = Field(
        default=None, alias="MIGRATION_DATABASE_URL"
    )
    internal_trigger_secret: SecretStr = Field(
        default=SecretStr("change-me-in-production"),
        alias="INTERNAL_TRIGGER_SECRET",
    )

    telegram_bot_token: SecretStr | None = Field(
        default=None, alias="TELEGRAM_BOT_TOKEN"
    )
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")
    telegram_allowed_chat_ids: str = Field(
        default="", alias="TELEGRAM_ALLOWED_CHAT_IDS"
    )
    telegram_webhook_secret: SecretStr | None = Field(
        default=None, alias="TELEGRAM_WEBHOOK_SECRET"
    )
    telegram_api_base: str = "https://api.telegram.org"

    github_token: SecretStr | None = Field(default=None, alias="GITHUB_TOKEN")
    github_username: str = Field(default="", alias="GITHUB_USERNAME")
    github_api_base: str = "https://api.github.com"

    leetcode_username: str = Field(default="", alias="LEETCODE_USERNAME")
    leetcode_session: SecretStr | None = Field(
        default=None, alias="LEETCODE_SESSION"
    )
    leetcode_csrf_token: SecretStr | None = Field(
        default=None, alias="LEETCODE_CSRF_TOKEN"
    )
    leetcode_graphql_url: str = "https://leetcode.com/graphql"

    groq_api_key: SecretStr | None = Field(default=None, alias="GROQ_API_KEY")
    groq_model: str = "openai/gpt-oss-20b"
    huggingface_api_token: SecretStr | None = Field(
        default=None, alias="HUGGINGFACE_API_TOKEN"
    )
    huggingface_model: str = "Qwen/Qwen2.5-7B-Instruct"
    huggingface_provider: str = "auto"
    model_temperature: float = 0.2
    model_max_tokens: int = 1200
    model_timeout_seconds: float = 45
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimensions: int = 384

    langsmith_tracing: bool = False
    langsmith_api_key: SecretStr | None = Field(
        default=None, alias="LANGSMITH_API_KEY"
    )
    langsmith_project: str = "pathwayai"
    local_trace_path: str = "var/traces.jsonl"
    raw_event_retention_days: int = 365
    raw_message_retention_days: int = 180

    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str = Field(default="", alias="SMTP_USERNAME")
    smtp_password: SecretStr | None = Field(default=None, alias="SMTP_PASSWORD")
    digest_email_from: str = Field(default="", alias="DIGEST_EMAIL_FROM")
    digest_email_to: str = Field(default="", alias="DIGEST_EMAIL_TO")

    tutor_name: str = "PathwayAI"
    tutor_default_goal: str = (
        "Become interview-ready for a backend or AI engineering role within six months."
    )
    max_interview_followups: int = 3
    chat_rate_limit_per_hour: int = 60

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    @field_validator(
        "job_search_horizon_months",
        "max_interview_followups",
        "chat_rate_limit_per_hour",
    )
    @classmethod
    def positive_integer(cls, value: int) -> int:
        if value < 1:
            raise ValueError("must be at least 1")
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def telegram_chat_allowlist(self) -> set[str]:
        raw = self.telegram_allowed_chat_ids or self.telegram_chat_id
        if not raw:
            return set()
        return {chunk.strip() for chunk in raw.split(",") if chunk.strip()}

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def database_enabled(self) -> bool:
        return self.database_url is not None

    @property
    def digest_email_enabled(self) -> bool:
        return bool(self.smtp_host and self.digest_email_to)

    @property
    def digest_email_sender(self) -> str:
        return self.digest_email_from or self.smtp_username

    @property
    def model_provider_order(self) -> tuple[str, ...]:
        providers: list[str] = []
        if self.groq_api_key:
            providers.append("groq")
        if self.huggingface_api_token:
            providers.append("huggingface")
        return tuple(providers)

    def async_database_url(self, *, migrations: bool = False) -> str | None:
        secret = (
            self.migration_database_url
            if migrations and self.migration_database_url
            else self.database_url
        )
        if secret is None:
            return None
        raw_url = secret.get_secret_value()
        split = urlsplit(raw_url)
        scheme = split.scheme
        if scheme in {"postgres", "postgresql"}:
            scheme = "postgresql+asyncpg"

        query = dict(parse_qsl(split.query, keep_blank_values=True))
        query.pop("channel_binding", None)
        if "sslmode" in query:
            query["ssl"] = query.pop("sslmode")
        return urlunsplit(
            (scheme, split.netloc, split.path, urlencode(query), split.fragment)
        )

    def validate_runtime_secrets(self) -> list[str]:
        errors: list[str] = []
        if self.is_production:
            if not self.database_enabled:
                errors.append("DATABASE_URL is required in production")
            if (
                self.internal_trigger_secret.get_secret_value()
                == "change-me-in-production"
            ):
                errors.append("INTERNAL_TRIGGER_SECRET must be changed in production")
        return errors


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
