from fastapi.testclient import TestClient

from pathwayai_backend.config import Settings
from pathwayai_backend.main import create_app


def test_internal_trigger_rejects_missing_secret() -> None:
    app = create_app(
        Settings(
            app_env="development",
            INTERNAL_TRIGGER_SECRET="test-secret",
            DATABASE_URL=None,
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/internal/triggers/morning-checkin",
            json={"request_id": "request-123"},
        )

    assert response.status_code == 401


def test_internal_trigger_requires_database_after_authentication() -> None:
    app = create_app(
        Settings(
            app_env="development",
            INTERNAL_TRIGGER_SECRET="test-secret",
            DATABASE_URL=None,
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/internal/triggers/morning-checkin",
            headers={"X-PathwayAI-Secret": "test-secret"},
            json={"request_id": "request-123"},
        )

    assert response.status_code == 503


def test_weekly_digest_rejects_missing_secret() -> None:
    app = create_app(
        Settings(
            app_env="development",
            INTERNAL_TRIGGER_SECRET="test-secret",
            DATABASE_URL=None,
        )
    )

    with TestClient(app) as client:
        response = client.post("/admin/weekly-digest")

    assert response.status_code == 401
