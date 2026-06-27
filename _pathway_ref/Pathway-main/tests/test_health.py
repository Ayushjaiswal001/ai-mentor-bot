from fastapi.testclient import TestClient

from pathwayai_backend.main import app


def test_health_endpoint_returns_ok() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "version" in payload
    assert isinstance(payload["model_providers"], list)


def test_app_version_helper_resolves_or_falls_back() -> None:
    from pathwayai_backend.core.version import app_version

    app_version.cache_clear()
    value = app_version()

    assert isinstance(value, str)
    assert value  # never empty
    assert " " not in value  # no shell error spilled in
    # Either a SHA, an env override, or "unknown"; all are non-empty single
    # tokens.
