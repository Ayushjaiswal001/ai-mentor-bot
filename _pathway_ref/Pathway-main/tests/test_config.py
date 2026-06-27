from pathwayai_backend.config import Settings


def test_neon_url_is_normalized_for_asyncpg() -> None:
    settings = Settings(
        DATABASE_URL=(
            "postgresql://user:pass@example-pooler.neon.tech/neondb"
            "?sslmode=require&channel_binding=require"
        )
    )

    assert settings.async_database_url() == (
        "postgresql+asyncpg://user:pass@example-pooler.neon.tech/neondb"
        "?ssl=require"
    )


def test_production_configuration_rejects_default_secret() -> None:
    settings = Settings(
        app_env="production",
        DATABASE_URL=None,
        INTERNAL_TRIGGER_SECRET="change-me-in-production",
    )

    errors = settings.validate_runtime_secrets()

    assert "DATABASE_URL is required in production" in errors
    assert "INTERNAL_TRIGGER_SECRET must be changed in production" in errors
