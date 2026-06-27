from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class TriggerType(StrEnum):
    MORNING_CHECKIN = "morning-checkin"
    GITHUB_SYNC = "github-sync"
    LEETCODE_SYNC = "leetcode-sync"
    EVENING_REFLECTION = "evening-reflection"
    WEEKLY_REVIEW = "weekly-review"
    MEMORY_COMPACTION = "memory-compaction"


class HealthResponse(BaseModel):
    status: str
    app_name: str
    environment: str
    database_configured: bool
    telegram_enabled: bool
    model_providers: list[str]
    version: str | None = None
    last_model_call_at: str | None = None
    last_model_call_success: bool | None = None


class ReadinessResponse(BaseModel):
    ready: bool
    checks: dict[str, bool]
    errors: list[str] = Field(default_factory=list)


class TriggerRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TriggerResponse(BaseModel):
    request_id: str
    workflow_type: str
    status: str
    duplicate: bool = False
    result: dict[str, Any] = Field(default_factory=dict)


class TutorRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=500)
    objective: str | None = Field(default=None, max_length=1000)
    send_to_telegram: bool = False


class TutorResponse(BaseModel):
    topic: str
    objective: str
    message: str
    provider: str
    delivered_to_telegram: bool


class TelegramMessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4096)


class TelegramMessageResponse(BaseModel):
    delivered: bool
    chat_id: str | None = None
    provider_message_id: str | None = None
    preview: str


class TelegramWebhookResponse(BaseModel):
    accepted: bool
    action: str


class OperationalStatusResponse(BaseModel):
    database_configured: bool
    telegram_enabled: bool
    model_providers: list[str]
    details: dict[str, Any] = Field(default_factory=dict)
