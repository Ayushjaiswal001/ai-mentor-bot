from datetime import UTC, datetime

import httpx
from pydantic import BaseModel, Field, ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from pathwayai_backend.config import Settings
from pathwayai_backend.integrations.base import IntegrationError

LEETCODE_QUERY = """
query pathwayAIProfile($username: String!, $limit: Int!) {
  recentAcSubmissionList(username: $username, limit: $limit) {
    id
    title
    titleSlug
    timestamp
  }
  matchedUser(username: $username) {
    submitStatsGlobal {
      acSubmissionNum {
        difficulty
        count
      }
    }
    tagProblemCounts {
      advanced { tagName problemsSolved }
      intermediate { tagName problemsSolved }
      fundamental { tagName problemsSolved }
    }
  }
}
"""


class LeetCodeSubmission(BaseModel):
    id: str
    title: str
    titleSlug: str
    timestamp: str


class LeetCodeSnapshot(BaseModel):
    submissions: list[LeetCodeSubmission] = Field(default_factory=list)
    difficulty_counts: dict[str, int] = Field(default_factory=dict)
    topic_counts: dict[str, int] = Field(default_factory=dict)
    fetched_at: datetime


class LeetCodeClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True,
    )
    async def fetch_snapshot(self) -> LeetCodeSnapshot:
        if not self.settings.leetcode_username:
            raise IntegrationError("LEETCODE_USERNAME is not configured")

        headers = {
            "Content-Type": "application/json",
            "Referer": f"https://leetcode.com/u/{self.settings.leetcode_username}/",
            "User-Agent": "PathwayAI",
        }
        cookies = {}
        if self.settings.leetcode_session:
            cookies["LEETCODE_SESSION"] = (
                self.settings.leetcode_session.get_secret_value()
            )
        if self.settings.leetcode_csrf_token:
            token = self.settings.leetcode_csrf_token.get_secret_value()
            cookies["csrftoken"] = token
            headers["X-CSRFToken"] = token

        payload = {
            "query": LEETCODE_QUERY,
            "variables": {"username": self.settings.leetcode_username, "limit": 50},
        }
        async with httpx.AsyncClient(timeout=20, cookies=cookies) as client:
            response = await client.post(
                self.settings.leetcode_graphql_url,
                headers=headers,
                json=payload,
            )
        if response.status_code >= 400:
            raise IntegrationError(
                f"LeetCode returned {response.status_code}: {response.text[:200]}"
            )
        body = response.json()
        if body.get("errors"):
            raise IntegrationError(f"LeetCode GraphQL error: {body['errors'][0]}")

        try:
            data = body["data"]
            submissions = [
                LeetCodeSubmission.model_validate(item)
                for item in data.get("recentAcSubmissionList") or []
            ]
            stats = (
                ((data.get("matchedUser") or {}).get("submitStatsGlobal") or {}).get(
                    "acSubmissionNum"
                )
                or []
            )
            difficulty_counts = {
                str(item["difficulty"]).lower(): int(item["count"]) for item in stats
            }
            tag_groups = (
                (data.get("matchedUser") or {}).get("tagProblemCounts") or {}
            )
            topic_counts = {
                str(item["tagName"]): int(item["problemsSolved"])
                for group in tag_groups.values()
                for item in (group or [])
            }
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise IntegrationError("LeetCode returned an unexpected payload") from exc

        return LeetCodeSnapshot(
            submissions=submissions,
            difficulty_counts=difficulty_counts,
            topic_counts=topic_counts,
            fetched_at=datetime.now(UTC),
        )
