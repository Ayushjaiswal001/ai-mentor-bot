from datetime import UTC, datetime, timedelta

import httpx
from pydantic import BaseModel, ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from pathwayai_backend.config import Settings
from pathwayai_backend.integrations.base import IntegrationError


class GitHubCommit(BaseModel):
    sha: str
    message: str
    repo: str
    occurred_at: datetime
    url: str | None = None


class GitHubRepo(BaseModel):
    full_name: str
    pushed_at: datetime | None = None
    archived: bool = False


class GitHubClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True,
    )
    async def fetch_recent_commits(self) -> list[GitHubCommit]:
        if not self.settings.github_username:
            raise IntegrationError("GITHUB_USERNAME is not configured")

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "PathwayAI",
        }
        authenticated = self.settings.github_token is not None
        if self.settings.github_token:
            headers["Authorization"] = (
                f"Bearer {self.settings.github_token.get_secret_value()}"
            )

        since = datetime.now(UTC) - timedelta(days=8)
        async with httpx.AsyncClient(timeout=20, headers=headers) as client:
            repos = await self._fetch_repositories(client, authenticated)
            recent_repos = [
                repo
                for repo in repos
                if not repo.archived
                and repo.pushed_at is not None
                and repo.pushed_at.astimezone(UTC) >= since
            ][:25]
            commits: list[GitHubCommit] = []
            for repo in recent_repos:
                commits.extend(await self._fetch_repo_commits(client, repo, since))
        return commits

    async def _fetch_repositories(
        self, client: httpx.AsyncClient, authenticated: bool
    ) -> list[GitHubRepo]:
        if authenticated:
            url = f"{self.settings.github_api_base}/user/repos"
            params = {
                "affiliation": "owner",
                "sort": "pushed",
                "direction": "desc",
                "per_page": 100,
            }
        else:
            url = (
                f"{self.settings.github_api_base}/users/"
                f"{self.settings.github_username}/repos"
            )
            params = {"sort": "pushed", "direction": "desc", "per_page": 100}
        response = await client.get(url, params=params)
        self._raise_for_status(response)
        try:
            return [GitHubRepo.model_validate(item) for item in response.json()]
        except (ValidationError, ValueError) as exc:
            raise IntegrationError("GitHub returned invalid repository data") from exc

    async def _fetch_repo_commits(
        self,
        client: httpx.AsyncClient,
        repo: GitHubRepo,
        since: datetime,
    ) -> list[GitHubCommit]:
        url = f"{self.settings.github_api_base}/repos/{repo.full_name}/commits"
        response = await client.get(
            url,
            params={
                "author": self.settings.github_username,
                "since": since.isoformat(),
                "per_page": 100,
            },
        )
        if response.status_code == 409:
            return []
        self._raise_for_status(response)
        commits: list[GitHubCommit] = []
        try:
            for item in response.json():
                author_data = (item.get("commit") or {}).get("author") or {}
                occurred_at = datetime.fromisoformat(
                    str(author_data["date"]).replace("Z", "+00:00")
                )
                commits.append(
                    GitHubCommit(
                        sha=str(item["sha"]),
                        message=str((item.get("commit") or {}).get("message", "")),
                        repo=repo.full_name,
                        occurred_at=occurred_at,
                        url=item.get("html_url"),
                    )
                )
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise IntegrationError("GitHub returned invalid commit data") from exc
        return commits

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code >= 400:
            raise IntegrationError(
                f"GitHub API returned {response.status_code}: {response.text[:200]}"
            )
