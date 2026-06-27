from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from pathwayai_backend.config import Settings
from pathwayai_backend.core.tracing import TraceRecorder
from pathwayai_backend.db.repositories import Repository
from pathwayai_backend.integrations.github import GitHubClient
from pathwayai_backend.integrations.leetcode import LeetCodeClient
from pathwayai_backend.integrations.telegram import TelegramClient
from pathwayai_backend.llm.gateway import ModelGateway
from pathwayai_backend.schemas import TriggerType
from pathwayai_backend.workflows.mentor import MentorWorkflowEngine

logger = structlog.get_logger(__name__)


class WorkflowCoordinator:
    def __init__(self, settings: Settings, session: AsyncSession) -> None:
        self.settings = settings
        self.session = session
        self.repository = Repository(session)
        self.traces = TraceRecorder(settings)
        self.github = GitHubClient(settings)
        self.leetcode = LeetCodeClient(settings)
        self.telegram = TelegramClient(settings)
        self.models = ModelGateway(settings)
        self.mentor = MentorWorkflowEngine(
            settings=settings,
            repository=self.repository,
            model_gateway=self.models,
            telegram=self.telegram,
        )

    async def execute(
        self, trigger_type: TriggerType, request_id: str
    ) -> tuple[dict[str, Any], bool]:
        run, created = await self.repository.start_workflow(
            request_id, trigger_type.value
        )
        if not created:
            return {
                "status": run.status,
                "result": run.result,
                "workflow_run_id": str(run.id),
            }, True
        await self.session.commit()
        self.traces.record(
            "workflow_started",
            request_id=request_id,
            workflow_type=trigger_type.value,
            workflow_run_id=str(run.id),
        )

        try:
            user = await self.repository.get_or_create_user(
                telegram_chat_id=self.settings.telegram_chat_id or "unconfigured",
                display_name=self.settings.default_user_name,
                target_role=self.settings.target_role,
                timezone=self.settings.user_timezone,
            )
            result = await self._dispatch(trigger_type, user.id, run.id)
            await self.repository.finish_workflow(run, result=result)
            await self.session.commit()
            self.traces.record(
                "workflow_succeeded",
                request_id=request_id,
                workflow_type=trigger_type.value,
                workflow_run_id=str(run.id),
            )
            return {
                "status": run.status,
                "result": result,
                "workflow_run_id": str(run.id),
            }, False
        except Exception as exc:
            await self.session.rollback()
            run = await self.session.merge(run)
            if trigger_type in {
                TriggerType.GITHUB_SYNC,
                TriggerType.LEETCODE_SYNC,
            }:
                await self.repository.add_sync_run(
                    trigger_type.value.removesuffix("-sync"),
                    "failed",
                    0,
                    datetime.now(UTC),
                    error=f"{type(exc).__name__}: {exc}",
                )
            await self.repository.finish_workflow(
                run, error=f"{type(exc).__name__}: {exc}"
            )
            await self.session.commit()
            self.traces.record(
                "workflow_failed",
                request_id=request_id,
                workflow_type=trigger_type.value,
                workflow_run_id=str(run.id),
                error_type=type(exc).__name__,
            )
            logger.error(
                "workflow_failed",
                workflow_type=trigger_type.value,
                request_id=request_id,
                exc_info=True,
            )
            return {
                "status": run.status,
                "result": {},
                "error": str(exc),
                "workflow_run_id": str(run.id),
            }, False

    async def _dispatch(
        self, trigger_type: TriggerType, user_id, workflow_run_id
    ) -> dict[str, Any]:
        if trigger_type == TriggerType.MORNING_CHECKIN:
            return await self.mentor.run_morning(user_id, workflow_run_id)
        if trigger_type == TriggerType.EVENING_REFLECTION:
            return await self.mentor.run_evening(user_id, workflow_run_id)
        if trigger_type == TriggerType.WEEKLY_REVIEW:
            return await self.mentor.run_weekly(user_id, workflow_run_id)
        if trigger_type == TriggerType.GITHUB_SYNC:
            return await self._sync_github(user_id)
        if trigger_type == TriggerType.LEETCODE_SYNC:
            return await self._sync_leetcode(user_id)
        if trigger_type == TriggerType.MEMORY_COMPACTION:
            return await self.repository.prune_raw_records(
                event_retention_days=self.settings.raw_event_retention_days,
                message_retention_days=self.settings.raw_message_retention_days,
            )
        raise ValueError(f"Unsupported trigger type: {trigger_type}")

    async def _sync_github(self, user_id) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        commits = await self.github.fetch_recent_commits()
        events = [
            {
                "user_id": user_id,
                "event_type": "github_commit",
                "source": "github",
                "external_ref": commit.sha,
                "payload": {
                    "repo": commit.repo,
                    "message": commit.message,
                    "url": commit.url,
                },
                "occurred_at": commit.occurred_at,
            }
            for commit in commits
        ]
        inserted = await self.repository.add_activity_events(events)
        await self.repository.add_sync_run(
            "github", "succeeded", inserted, started_at
        )
        return {"fetched": len(commits), "inserted": inserted}

    async def _sync_leetcode(self, user_id) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        snapshot = await self.leetcode.fetch_snapshot()
        # Only real submissions are written as activity events; snapshot
        # totals are all-time and would falsely show up as "today's work."
        events = [
            {
                "user_id": user_id,
                "event_type": "leetcode_solve",
                "source": "leetcode",
                "external_ref": submission.id,
                "payload": {
                    "title": submission.title,
                    "title_slug": submission.titleSlug,
                },
                "occurred_at": datetime.fromtimestamp(
                    int(submission.timestamp), tz=UTC
                ),
            }
            for submission in snapshot.submissions
        ]
        inserted = await self.repository.add_activity_events(events)
        await self.repository.add_sync_run(
            "leetcode", "succeeded", inserted, started_at
        )
        return {"fetched": len(events), "inserted": inserted}
