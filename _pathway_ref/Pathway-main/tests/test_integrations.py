from datetime import UTC, datetime

import httpx
import pytest
import respx

from pathwayai_backend.config import Settings
from pathwayai_backend.integrations.github import GitHubClient
from pathwayai_backend.integrations.leetcode import LeetCodeClient


@pytest.mark.asyncio
@respx.mock
async def test_github_client_normalizes_commits() -> None:
    settings = Settings(
        GITHUB_USERNAME="ayush",
        GITHUB_TOKEN="token",
        github_api_base="https://api.github.test",
    )
    respx.get("https://api.github.test/user/repos").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "full_name": "ayush/pathwayai",
                    "pushed_at": datetime.now(UTC).isoformat(),
                    "archived": False,
                }
            ],
        )
    )
    respx.get("https://api.github.test/repos/ayush/pathwayai/commits").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "sha": "abc123",
                    "html_url": "https://github.test/commit/abc123",
                    "commit": {
                        "message": "Build mentor",
                        "author": {"date": "2026-06-06T10:00:00Z"},
                    },
                }
            ],
        )
    )

    commits = await GitHubClient(settings).fetch_recent_commits()

    assert len(commits) == 1
    assert commits[0].repo == "ayush/pathwayai"
    assert commits[0].message == "Build mentor"


@pytest.mark.asyncio
@respx.mock
async def test_leetcode_client_normalizes_snapshot() -> None:
    settings = Settings(
        LEETCODE_USERNAME="ayush",
        leetcode_graphql_url="https://leetcode.test/graphql",
    )
    respx.post("https://leetcode.test/graphql").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "recentAcSubmissionList": [
                        {
                            "id": "1",
                            "title": "Two Sum",
                            "titleSlug": "two-sum",
                            "timestamp": "1780740000",
                        }
                    ],
                    "matchedUser": {
                        "submitStatsGlobal": {
                            "acSubmissionNum": [
                                {"difficulty": "Easy", "count": 10}
                            ]
                        },
                        "tagProblemCounts": {
                            "advanced": [],
                            "intermediate": [
                                {"tagName": "Graph", "problemsSolved": 2}
                            ],
                            "fundamental": [],
                        },
                    },
                }
            },
        )
    )

    snapshot = await LeetCodeClient(settings).fetch_snapshot()

    assert snapshot.difficulty_counts == {"easy": 10}
    assert snapshot.topic_counts == {"Graph": 2}
    assert snapshot.submissions[0].title == "Two Sum"


class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.started_tls = False
        self.login_args = None
        self.message = None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, username, password):
        self.login_args = (username, password)

    def send_message(self, message):
        self.message = message


@pytest.mark.asyncio
async def test_email_client_requires_configuration() -> None:
    from pathwayai_backend.integrations.base import IntegrationError
    from pathwayai_backend.integrations.email import EmailClient

    settings = Settings(SMTP_HOST="", DIGEST_EMAIL_TO="")

    with pytest.raises(IntegrationError):
        await EmailClient(settings).send(subject="Digest", body="Hello")


@pytest.mark.asyncio
async def test_email_client_sends_via_starttls_with_login(monkeypatch) -> None:
    import pathwayai_backend.integrations.email as email_module
    from pathwayai_backend.integrations.email import EmailClient

    FakeSMTP.instances.clear()
    monkeypatch.setattr(email_module.smtplib, "SMTP", FakeSMTP)
    settings = Settings(
        SMTP_HOST="smtp.test",
        SMTP_PORT=587,
        SMTP_USERNAME="bot@test.dev",
        SMTP_PASSWORD="secret",
        DIGEST_EMAIL_TO="me@test.dev",
    )

    await EmailClient(settings).send(
        subject="PathwayAI weekly digest", body="# Export\nWeek in review."
    )

    assert len(FakeSMTP.instances) == 1
    smtp = FakeSMTP.instances[0]
    assert (smtp.host, smtp.port) == ("smtp.test", 587)
    assert smtp.started_tls is True
    assert smtp.login_args == ("bot@test.dev", "secret")
    assert smtp.message["Subject"] == "PathwayAI weekly digest"
    # Sender falls back to SMTP_USERNAME when DIGEST_EMAIL_FROM is unset.
    assert smtp.message["From"] == "bot@test.dev"
    assert smtp.message["To"] == "me@test.dev"
    assert "Week in review." in smtp.message.get_content()
