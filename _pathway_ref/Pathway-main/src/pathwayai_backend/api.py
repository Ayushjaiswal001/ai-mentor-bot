from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pathwayai_backend.config import Settings
from pathwayai_backend.core.security import (
    require_internal_secret,
    verify_telegram_secret,
)
from pathwayai_backend.db.repositories import Repository
from pathwayai_backend.integrations.telegram import TelegramClient
from pathwayai_backend.schemas import (
    HealthResponse,
    OperationalStatusResponse,
    ReadinessResponse,
    TelegramMessageRequest,
    TelegramMessageResponse,
    TelegramWebhookResponse,
    TriggerRequest,
    TriggerResponse,
    TriggerType,
    TutorRequest,
    TutorResponse,
)
from pathwayai_backend.services.coordinator import WorkflowCoordinator
from pathwayai_backend.services.telegram_updates import TelegramUpdateService
from pathwayai_backend.services.tutor import TutorService

router = APIRouter()


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    database = request.app.state.database
    if not database.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured",
        )
    async for session in database.session():
        yield session


@router.get("/health", response_model=HealthResponse)
async def health(
    request: Request,
    settings: Settings = Depends(get_app_settings),
) -> HealthResponse:
    from pathwayai_backend.core.version import app_version

    last_at: str | None = None
    last_ok: bool | None = None
    database = request.app.state.database
    if database.configured:
        try:
            async for session in database.session():
                from pathwayai_backend.db.repositories import Repository

                repository = Repository(session)
                latest = await repository.latest_model_call()
                if latest is not None:
                    last_at = latest.created_at.isoformat()
                    last_ok = latest.success
                break
        except Exception:
            pass

    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        environment=settings.app_env,
        database_configured=settings.database_enabled,
        telegram_enabled=settings.telegram_enabled,
        model_providers=list(settings.model_provider_order),
        version=app_version(),
        last_model_call_at=last_at,
        last_model_call_success=last_ok,
    )


@router.get("/ready", response_model=ReadinessResponse)
async def readiness(request: Request) -> ReadinessResponse:
    settings: Settings = request.app.state.settings
    checks = {
        "configuration": not settings.validate_runtime_secrets(),
        "database": False,
        "telegram": settings.telegram_enabled,
        "model_provider": bool(settings.model_provider_order),
    }
    errors = settings.validate_runtime_secrets()
    database = request.app.state.database
    if database.configured:
        try:
            async for session in database.session():
                await session.execute(text("SELECT 1"))
                checks["database"] = True
                break
        except Exception:
            errors.append("Database connectivity check failed")
    else:
        errors.append("Database is not configured")
    return ReadinessResponse(
        ready=all(checks.values()),
        checks=checks,
        errors=errors,
    )


@router.post("/telegram/send", response_model=TelegramMessageResponse)
async def send_telegram_message(
    payload: TelegramMessageRequest,
    settings: Settings = Depends(get_app_settings),
) -> TelegramMessageResponse:
    delivery = await TelegramClient(settings).send_message(payload.text)
    return TelegramMessageResponse(
        delivered=delivery.delivered,
        chat_id=settings.telegram_chat_id,
        provider_message_id=delivery.message_id,
        preview=payload.text,
    )


@router.get(
    "/admin/model-usage",
    dependencies=[Depends(require_internal_secret)],
)
async def admin_model_usage(
    request: Request,
    days: int = 1,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    import structlog

    from pathwayai_backend.db.repositories import Repository

    structlog.get_logger("admin_audit").info(
        "admin_call",
        endpoint="model_usage",
        client=request.client.host if request.client else None,
        days=days,
    )
    repository = Repository(session)
    summary = await repository.model_call_summary(days=days)
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        from fastapi.responses import HTMLResponse

        series = await repository.model_call_daily_series(days=max(days, 7))
        errors = await repository.model_call_error_summary(days=days, limit=5)
        provider_days: dict[str, list[int]] = {}
        for row in series:
            provider_days.setdefault(row["provider"], []).append(int(row["total"]))
        spark_chars = " ▁▂▃▄▅▆▇█"

        def spark(values: list[int]) -> str:
            if not values:
                return ""
            top = max(values) or 1
            return "".join(
                spark_chars[min(len(spark_chars) - 1, round(v * 8 / top))]
                for v in values
            )

        rows = "".join(
            f"<tr><td>{row['provider']}</td>"
            f"<td>{row['success_count']}/{row['total']}"
            f" ({(int(row['success_count']) / int(row['total']) * 100):.0f}%)</td>"
            f"<td>{row['prompt_tokens']}</td>"
            f"<td>{row['completion_tokens']}</td>"
            f"<td>{int(row['avg_latency_ms'])} ms</td>"
            f"<td class='spark'>{spark(provider_days.get(row['provider'], []))}</td></tr>"
            for row in summary
        )
        error_rows = "".join(
            f"<tr><td>{row['provider']}</td><td>{row['count']}</td>"
            f"<td><code>{row['error']}</code></td></tr>"
            for row in errors
        )
        html = f"""<!doctype html><html><head><title>Model Usage</title>
<style>body{{font-family:system-ui;margin:2rem;max-width:900px;}}
table{{border-collapse:collapse;margin-bottom:2rem;width:100%;}}
td,th{{border:1px solid #ccc;padding:.5rem 1rem;text-align:left;}}
th{{background:#f4f4f4;}}
.spark{{font-family:ui-monospace,monospace;font-size:1.4rem;letter-spacing:1px;}}
code{{font-size:.85rem;}}
h2{{margin-top:2.5rem;}}</style></head><body>
<h1>Model usage (last {days}d)</h1>
<table><thead><tr><th>Provider</th><th>Success</th><th>Prompt tokens</th>
<th>Completion tokens</th><th>Avg latency</th><th>Calls/day (last 7d)</th></tr></thead>
<tbody>{rows or '<tr><td colspan=6>No data.</td></tr>'}</tbody></table>
<h2>Recent errors</h2>
<table><thead><tr><th>Provider</th><th>Count</th><th>Error</th></tr></thead>
<tbody>{error_rows or '<tr><td colspan=3>No failures recorded.</td></tr>'}</tbody></table>
</body></html>"""
        return HTMLResponse(content=html)
    return {"days": days, "summary": summary}


@router.post(
    "/admin/daily-nudge",
    dependencies=[Depends(require_internal_secret)],
)
async def admin_daily_nudge(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    import structlog

    structlog.get_logger("admin_audit").info(
        "admin_call",
        endpoint="daily_nudge",
        client=request.client.host if request.client else None,
    )
    from datetime import UTC, datetime
    from zoneinfo import ZoneInfo

    from pathwayai_backend.config import get_settings
    from pathwayai_backend.db.repositories import Repository
    from pathwayai_backend.integrations.telegram import TelegramClient

    settings = get_settings()
    repository = Repository(session)
    telegram = TelegramClient(settings)
    tz = ZoneInfo(settings.user_timezone)
    local_now = datetime.now(tz)
    day_start_utc = local_now.replace(
        hour=0, minute=0, second=0, microsecond=0
    ).astimezone(UTC)
    nudged: list[str] = []
    for user in await repository.active_users():
        if await repository.logged_today(user.id, day_start_utc):
            continue
        try:
            await telegram.send_message(
                "You haven't logged today — even one line locks the day's work in.\n"
                "Use /log to capture what you built, learned, or got stuck on.",
                chat_id=user.telegram_chat_id,
            )
            nudged.append(user.telegram_chat_id)
        except Exception:
            continue
    return {"nudged": nudged, "count": len(nudged)}


@router.post(
    "/admin/prune",
    dependencies=[Depends(require_internal_secret)],
)
async def admin_prune(
    request: Request,
    days: int = 90,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    import structlog

    from pathwayai_backend.db.repositories import Repository

    structlog.get_logger("admin_audit").info(
        "admin_call",
        endpoint="prune",
        client=request.client.host if request.client else None,
        days=days,
    )
    repository = Repository(session)
    summary = await repository.prune_old_rows(days=days)
    await session.commit()
    return {"days": days, "deleted": summary}


@router.post(
    "/admin/weekly-digest",
    dependencies=[Depends(require_internal_secret)],
)
async def admin_weekly_digest(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    import structlog

    from pathwayai_backend.db.repositories import Repository
    from pathwayai_backend.integrations.email import EmailClient

    settings: Settings = request.app.state.settings
    structlog.get_logger("admin_audit").info(
        "admin_call",
        endpoint="weekly_digest",
        client=request.client.host if request.client else None,
    )
    if not settings.digest_email_enabled:
        return {"sent": [], "skipped": "digest email is not configured"}
    repository = Repository(session)
    service = TelegramUpdateService(settings, session)
    email = EmailClient(settings)
    sent: list[str] = []
    failed: list[str] = []
    for user in await repository.active_users():
        filename, markdown = await service.build_export_markdown(
            user.id, scope="week"
        )
        try:
            await email.send(
                subject=f"PathwayAI weekly digest — {user.display_name or 'your week'}",
                body=markdown,
            )
            sent.append(filename)
        except Exception:
            structlog.get_logger("admin_audit").warning(
                "weekly_digest_send_failed", user_id=str(user.id)
            )
            failed.append(filename)
    return {"sent": sent, "failed": failed}


@router.post("/telegram/webhook", response_model=TelegramWebhookResponse)
async def telegram_webhook(
    payload: dict[str, Any],
    request: Request,
    session: AsyncSession = Depends(get_session),
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> TelegramWebhookResponse:
    settings: Settings = request.app.state.settings
    if not verify_telegram_secret(x_telegram_bot_api_secret_token, settings):
        raise HTTPException(status_code=401, detail="Invalid Telegram webhook secret")
    action = await TelegramUpdateService(settings, session).handle(payload)
    return TelegramWebhookResponse(accepted=True, action=action)


@router.post("/tutor/message", response_model=TutorResponse)
async def generate_tutor_message(
    payload: TutorRequest,
    settings: Settings = Depends(get_app_settings),
) -> TutorResponse:
    objective = payload.objective or settings.tutor_default_goal
    result = await TutorService(settings).generate_message(
        topic=payload.topic,
        objective=objective,
    )
    delivered = False
    if payload.send_to_telegram:
        delivered = (
            await TelegramClient(settings).send_message(result.content)
        ).delivered
    return TutorResponse(
        topic=payload.topic,
        objective=objective,
        message=result.content,
        provider=result.provider,
        delivered_to_telegram=delivered,
    )


@router.post(
    "/internal/triggers/{trigger_type}",
    response_model=TriggerResponse,
    dependencies=[Depends(require_internal_secret)],
)
async def run_trigger(
    trigger_type: TriggerType,
    payload: TriggerRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> TriggerResponse:
    settings: Settings = request.app.state.settings
    result, duplicate = await WorkflowCoordinator(settings, session).execute(
        trigger_type, payload.request_id
    )
    if result["status"] == "failed":
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "request_id": payload.request_id,
                "workflow_type": trigger_type.value,
                **result,
            },
        )
    return TriggerResponse(
        request_id=payload.request_id,
        workflow_type=trigger_type.value,
        status=result["status"],
        duplicate=duplicate,
        result=result.get("result", {}),
    )


@router.get(
    "/internal/status",
    response_model=OperationalStatusResponse,
    dependencies=[Depends(require_internal_secret)],
)
async def operational_status(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> OperationalStatusResponse:
    settings: Settings = request.app.state.settings
    details = await Repository(session).operational_status()
    return OperationalStatusResponse(
        database_configured=settings.database_enabled,
        telegram_enabled=settings.telegram_enabled,
        model_providers=list(settings.model_provider_order),
        details=details,
    )
