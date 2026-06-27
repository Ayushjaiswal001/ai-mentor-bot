import hmac

from fastapi import Header, HTTPException, Request, status

from pathwayai_backend.config import Settings


def verify_secret(provided: str | None, expected: str) -> bool:
    return bool(provided) and hmac.compare_digest(provided, expected)


async def require_internal_secret(
    request: Request,
    x_pathwayai_secret: str | None = Header(default=None),
) -> None:
    settings: Settings = request.app.state.settings
    if not verify_secret(
        x_pathwayai_secret, settings.internal_trigger_secret.get_secret_value()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal trigger credentials",
        )


def verify_telegram_secret(provided: str | None, settings: Settings) -> bool:
    if settings.telegram_webhook_secret is None:
        return not settings.is_production
    return verify_secret(
        provided, settings.telegram_webhook_secret.get_secret_value()
    )
