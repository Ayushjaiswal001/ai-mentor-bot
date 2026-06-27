from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import Integer as sa_Integer, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pathwayai_backend.db.models import (
    ActivityEvent,
    ConversationMessage,
    DailyGoal,
    LearningLog,
    MemorySummary,
    ModelCallLog,
    OutboundMessage,
    ProcessedUpdate,
    ReadinessScore,
    SyncRun,
    TopicMastery,
    UserInteractionState,
    User,
    WeeklyPlan,
    WorkflowRun,
    WorkflowStatus,
)


class Repository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create_user(
        self,
        *,
        telegram_chat_id: str,
        display_name: str,
        target_role: str,
        timezone: str,
    ) -> User:
        result = await self.session.execute(
            select(User).where(User.telegram_chat_id == telegram_chat_id)
        )
        user = result.scalar_one_or_none()
        if user:
            return user
        user = User(
            telegram_chat_id=telegram_chat_id,
            display_name=display_name,
            target_role=target_role,
            timezone=timezone,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def add_goal(
        self, user_id: UUID, goal_date: date, content: str
    ) -> DailyGoal:
        goal = DailyGoal(
            user_id=user_id, goal_date=goal_date, content=content
        )
        self.session.add(goal)
        await self.session.flush()
        return goal

    async def goals_for_date(
        self, user_id: UUID, goal_date: date
    ) -> list[DailyGoal]:
        result = await self.session.execute(
            select(DailyGoal)
            .where(
                DailyGoal.user_id == user_id, DailyGoal.goal_date == goal_date
            )
            .order_by(DailyGoal.created_at)
        )
        return list(result.scalars())

    async def get_goal_by_id(self, goal_id: UUID) -> DailyGoal | None:
        result = await self.session.execute(
            select(DailyGoal).where(DailyGoal.id == goal_id)
        )
        return result.scalar_one_or_none()

    async def update_goal_status_by_id(
        self, goal_id: UUID, status: str
    ) -> int:
        result = await self.session.execute(
            update(DailyGoal)
            .where(DailyGoal.id == goal_id)
            .values(status=status, updated_at=func.now())
        )
        return result.rowcount or 0

    async def delete_goal_by_id(self, goal_id: UUID) -> int:
        result = await self.session.execute(
            delete(DailyGoal).where(DailyGoal.id == goal_id)
        )
        return result.rowcount or 0

    async def goals_in_range(
        self, user_id: UUID, start: date, end: date
    ) -> list[DailyGoal]:
        result = await self.session.execute(
            select(DailyGoal)
            .where(
                DailyGoal.user_id == user_id,
                DailyGoal.goal_date >= start,
                DailyGoal.goal_date <= end,
            )
            .order_by(DailyGoal.goal_date.desc())
        )
        return list(result.scalars())

    async def recent_goals(self, user_id: UUID, limit: int = 7) -> list[DailyGoal]:
        result = await self.session.execute(
            select(DailyGoal)
            .where(DailyGoal.user_id == user_id)
            .order_by(DailyGoal.goal_date.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def delete_goal(self, user_id: UUID, goal_date: date) -> int:
        result = await self.session.execute(
            delete(DailyGoal).where(
                DailyGoal.user_id == user_id, DailyGoal.goal_date == goal_date
            )
        )
        return result.rowcount or 0

    async def add_learning_log(
        self,
        user_id: UUID,
        content: str,
        topics: list[str] | None = None,
        embedding: list[float] | None = None,
    ) -> LearningLog:
        log = LearningLog(
            user_id=user_id,
            content=content,
            topics=topics or [],
            embedding=embedding,
        )
        self.session.add(log)
        await self.session.flush()
        return log

    async def active_users(self) -> list[User]:
        result = await self.session.execute(
            select(User).where(User.active.is_(True))
        )
        return list(result.scalars())

    async def logged_today(
        self, user_id: UUID, day_start_utc: datetime
    ) -> bool:
        result = await self.session.execute(
            select(func.count())
            .select_from(LearningLog)
            .where(
                LearningLog.user_id == user_id,
                LearningLog.created_at >= day_start_utc,
            )
        )
        return int(result.scalar_one() or 0) > 0

    async def claim_update(self, source: str, external_id: str) -> bool:
        """Returns True if this is the first time we have seen this update."""
        statement = (
            insert(ProcessedUpdate)
            .values(source=source, external_id=str(external_id))
            .on_conflict_do_nothing(constraint="pk_processed_updates")
            .returning(ProcessedUpdate.source)
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none() is not None

    async def latest_model_call(self) -> ModelCallLog | None:
        result = await self.session.execute(
            select(ModelCallLog)
            .order_by(ModelCallLog.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def model_call_daily_series(
        self, days: int = 7
    ) -> list[dict]:
        """Returns daily counts and tokens per provider for the last `days`."""
        since = datetime.now(UTC) - timedelta(days=days)
        result = await self.session.execute(
            select(
                ModelCallLog.provider,
                func.date_trunc("day", ModelCallLog.created_at).label("day"),
                func.count().label("total"),
                func.sum(func.cast(ModelCallLog.success, sa_Integer)).label("success_count"),
                func.coalesce(
                    func.sum(
                        ModelCallLog.prompt_tokens
                        + func.coalesce(ModelCallLog.completion_tokens, 0)
                    ),
                    0,
                ).label("tokens"),
            )
            .where(ModelCallLog.created_at >= since)
            .group_by(ModelCallLog.provider, "day")
            .order_by("day")
        )
        return [dict(row._mapping) for row in result.all()]

    async def model_call_error_summary(
        self, days: int = 1, limit: int = 5
    ) -> list[dict]:
        since = datetime.now(UTC) - timedelta(days=days)
        result = await self.session.execute(
            select(
                ModelCallLog.provider,
                ModelCallLog.error,
                func.count().label("count"),
            )
            .where(
                ModelCallLog.created_at >= since,
                ModelCallLog.success.is_(False),
                ModelCallLog.error.is_not(None),
            )
            .group_by(ModelCallLog.provider, ModelCallLog.error)
            .order_by(func.count().desc())
            .limit(limit)
        )
        return [dict(row._mapping) for row in result.all()]

    async def log_model_call(
        self,
        *,
        provider: str,
        model: str,
        success: bool,
        latency_ms: int,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        error: str | None = None,
    ) -> None:
        self.session.add(
            ModelCallLog(
                provider=provider,
                model=model,
                success=success,
                latency_ms=latency_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                error=error,
            )
        )
        await self.session.flush()

    async def model_call_summary(self, days: int = 1) -> list[dict]:
        since = datetime.now(UTC) - timedelta(days=days)
        result = await self.session.execute(
            select(
                ModelCallLog.provider,
                func.sum(func.cast(ModelCallLog.success, sa_Integer)).label("success_count"),
                func.count().label("total"),
                func.coalesce(func.sum(ModelCallLog.prompt_tokens), 0).label("prompt_tokens"),
                func.coalesce(func.sum(ModelCallLog.completion_tokens), 0).label("completion_tokens"),
                func.coalesce(func.avg(ModelCallLog.latency_ms), 0).label("avg_latency_ms"),
            )
            .where(ModelCallLog.created_at >= since)
            .group_by(ModelCallLog.provider)
        )
        return [dict(row._mapping) for row in result.all()]

    async def latest_log_for_topic(
        self, user_id: UUID, topic: str
    ) -> LearningLog | None:
        result = await self.session.execute(
            select(LearningLog)
            .where(
                LearningLog.user_id == user_id,
                func.lower(LearningLog.topic) == topic.lower(),
            )
            .order_by(LearningLog.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def delete_learning_log(self, user_id: UUID, log_id: UUID) -> int:
        result = await self.session.execute(
            delete(LearningLog).where(
                LearningLog.user_id == user_id, LearningLog.id == log_id
            )
        )
        return result.rowcount or 0

    async def upsert_topic_mastery(
        self,
        *,
        user_id: UUID,
        topic: str,
        level: str,
        next_due_at: datetime,
    ) -> TopicMastery:
        now = datetime.now(UTC)
        statement = (
            insert(TopicMastery)
            .values(
                user_id=user_id,
                topic=topic,
                level=level,
                last_quizzed_at=now,
                next_due_at=next_due_at,
                quiz_count=1,
            )
            .on_conflict_do_update(
                constraint="uq_topic_mastery_user_topic",
                set_={
                    "level": level,
                    "last_quizzed_at": now,
                    "next_due_at": next_due_at,
                    "quiz_count": TopicMastery.quiz_count + 1,
                    "updated_at": func.now(),
                },
            )
            .returning(TopicMastery)
        )
        result = await self.session.execute(statement)
        return result.scalar_one()

    async def due_topics(
        self, user_id: UUID, limit: int = 5
    ) -> list[TopicMastery]:
        now = datetime.now(UTC)
        result = await self.session.execute(
            select(TopicMastery)
            .where(
                TopicMastery.user_id == user_id,
                TopicMastery.next_due_at.is_not(None),
                TopicMastery.next_due_at <= now,
            )
            .order_by(TopicMastery.next_due_at.asc())
            .limit(limit)
        )
        return list(result.scalars())

    async def all_topic_mastery(
        self, user_id: UUID
    ) -> list[TopicMastery]:
        result = await self.session.execute(
            select(TopicMastery)
            .where(TopicMastery.user_id == user_id)
            .order_by(TopicMastery.last_quizzed_at.desc().nulls_last())
        )
        return list(result.scalars())

    async def update_log_fields(
        self, log_id: UUID, fields: dict
    ) -> None:
        if not fields:
            return
        await self.session.execute(
            update(LearningLog)
            .where(LearningLog.id == log_id)
            .values(**fields, updated_at=func.now())
        )

    async def set_log_embedding(
        self, log_id: UUID, embedding: list[float]
    ) -> None:
        await self.session.execute(
            update(LearningLog)
            .where(LearningLog.id == log_id)
            .values(embedding=embedding, updated_at=func.now())
        )

    async def set_memory_embedding(
        self, memory_id: UUID, embedding: list[float]
    ) -> None:
        await self.session.execute(
            update(MemorySummary)
            .where(MemorySummary.id == memory_id)
            .values(embedding=embedding, updated_at=func.now())
        )

    async def logs_with_stories(
        self, user_id: UUID, limit: int = 20
    ) -> list[LearningLog]:
        result = await self.session.execute(
            select(LearningLog)
            .where(
                LearningLog.user_id == user_id,
                LearningLog.interview_story.is_not(None),
                LearningLog.interview_story != "",
            )
            .order_by(LearningLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def log_dates(
        self, user_id: UUID, days: int = 60
    ) -> list[datetime]:
        since = datetime.now(UTC) - timedelta(days=days)
        result = await self.session.execute(
            select(LearningLog.created_at)
            .where(
                LearningLog.user_id == user_id,
                LearningLog.created_at >= since,
            )
        )
        return [row[0] for row in result.all()]

    async def recent_memories_by_type(
        self, user_id: UUID, memory_type: str, days: int = 7
    ) -> list[MemorySummary]:
        since = datetime.now(UTC) - timedelta(days=days)
        result = await self.session.execute(
            select(MemorySummary)
            .where(
                MemorySummary.user_id == user_id,
                MemorySummary.memory_type == memory_type,
                MemorySummary.created_at >= since,
            )
            .order_by(MemorySummary.created_at.desc())
        )
        return list(result.scalars())

    async def get_learning_log(self, user_id: UUID, log_id: UUID) -> LearningLog | None:
        result = await self.session.execute(
            select(LearningLog).where(
                LearningLog.user_id == user_id, LearningLog.id == log_id
            )
        )
        return result.scalar_one_or_none()

    async def recent_logs_limited(
        self, user_id: UUID, limit: int = 5
    ) -> list[LearningLog]:
        result = await self.session.execute(
            select(LearningLog)
            .where(LearningLog.user_id == user_id)
            .order_by(LearningLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def add_message(
        self,
        *,
        user_id: UUID,
        external_message_id: str,
        direction: str,
        content: str,
        message_type: str = "text",
        metadata: dict | None = None,
    ) -> None:
        statement = (
            insert(ConversationMessage)
            .values(
                user_id=user_id,
                source="telegram",
                external_message_id=external_message_id,
                direction=direction,
                message_type=message_type,
                content=content,
                metadata_json=metadata or {},
            )
            .on_conflict_do_nothing(constraint="uq_message_source_external")
        )
        await self.session.execute(statement)

    async def inbound_count_since(
        self, user_id: UUID, since: datetime
    ) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(ConversationMessage)
            .where(
                ConversationMessage.user_id == user_id,
                ConversationMessage.direction == "inbound",
                ConversationMessage.created_at >= since,
            )
        )
        return int(result.scalar_one() or 0)

    async def conversation_message_count(self, user_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(ConversationMessage)
            .where(ConversationMessage.user_id == user_id)
        )
        return int(result.scalar_one() or 0)

    async def oldest_conversation_messages(
        self, user_id: UUID, limit: int
    ) -> list[ConversationMessage]:
        result = await self.session.execute(
            select(ConversationMessage)
            .where(ConversationMessage.user_id == user_id)
            .order_by(ConversationMessage.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars())

    async def delete_conversation_messages(
        self, user_id: UUID, ids: list[UUID]
    ) -> int:
        if not ids:
            return 0
        result = await self.session.execute(
            delete(ConversationMessage).where(
                ConversationMessage.user_id == user_id,
                ConversationMessage.id.in_(ids),
            )
        )
        return result.rowcount or 0

    async def prune_old_rows(self, days: int = 90) -> dict[str, int]:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        outbound = await self.session.execute(
            delete(OutboundMessage).where(OutboundMessage.created_at < cutoff)
        )
        model_logs = await self.session.execute(
            delete(ModelCallLog).where(ModelCallLog.created_at < cutoff)
        )
        processed = await self.session.execute(
            delete(ProcessedUpdate).where(ProcessedUpdate.processed_at < cutoff)
        )
        return {
            "outbound_messages_deleted": outbound.rowcount or 0,
            "model_call_logs_deleted": model_logs.rowcount or 0,
            "processed_updates_deleted": processed.rowcount or 0,
        }

    async def recent_conversation_messages(
        self, user_id: UUID, limit: int = 12
    ) -> list[ConversationMessage]:
        result = await self.session.execute(
            select(ConversationMessage)
            .where(ConversationMessage.user_id == user_id)
            .order_by(ConversationMessage.created_at.desc())
            .limit(limit)
        )
        rows = list(result.scalars())
        rows.reverse()
        return rows

    async def add_activity_events(self, events: list[dict]) -> int:
        inserted = 0
        for event in events:
            statement = (
                insert(ActivityEvent)
                .values(**event)
                .on_conflict_do_nothing(constraint="uq_activity_source_ref")
                .returning(ActivityEvent.id)
            )
            result = await self.session.execute(statement)
            inserted += int(result.scalar_one_or_none() is not None)
        return inserted

    # Snapshot rows are sync-time metadata (all-time totals stamped at now()),
    # not real activity. Excluding them keeps the morning/evening/weekly LLM
    # prompts and /activity from claiming you did 253 problems "today."
    _SNAPSHOT_EVENT_TYPES = ("leetcode_snapshot",)

    async def recent_events(self, user_id: UUID, days: int = 7) -> list[ActivityEvent]:
        since = datetime.now(UTC) - timedelta(days=days)
        result = await self.session.execute(
            select(ActivityEvent)
            .where(
                ActivityEvent.user_id == user_id,
                ActivityEvent.occurred_at >= since,
                ActivityEvent.event_type.notin_(self._SNAPSHOT_EVENT_TYPES),
            )
            .order_by(ActivityEvent.occurred_at.desc())
        )
        return list(result.scalars())

    async def recent_logs(self, user_id: UUID, days: int = 7) -> list[LearningLog]:
        since = datetime.now(UTC) - timedelta(days=days)
        result = await self.session.execute(
            select(LearningLog)
            .where(LearningLog.user_id == user_id, LearningLog.created_at >= since)
            .order_by(LearningLog.created_at.desc())
        )
        return list(result.scalars())

    async def recent_memories(
        self, user_id: UUID, days: int = 30
    ) -> list[MemorySummary]:
        since = datetime.now(UTC) - timedelta(days=days)
        result = await self.session.execute(
            select(MemorySummary)
            .where(
                MemorySummary.user_id == user_id,
                MemorySummary.created_at >= since,
            )
            .order_by(MemorySummary.created_at.desc())
        )
        return list(result.scalars())

    async def search_memory(
        self, user_id: UUID, query: str, limit: int = 8
    ) -> list[MemorySummary | LearningLog]:
        ts_query = func.websearch_to_tsquery("english", query)
        memory_result = await self.session.execute(
            select(MemorySummary)
            .where(
                MemorySummary.user_id == user_id,
                func.to_tsvector("english", MemorySummary.content).op("@@")(ts_query),
            )
            .limit(limit)
        )
        log_result = await self.session.execute(
            select(LearningLog)
            .where(
                LearningLog.user_id == user_id,
                func.to_tsvector("english", LearningLog.content).op("@@")(ts_query),
            )
            .limit(limit)
        )
        return [*memory_result.scalars(), *log_result.scalars()][:limit]

    async def add_memory(
        self,
        user_id: UUID,
        memory_type: str,
        title: str,
        content: str,
        evidence_refs: list[str],
        embedding: list[float] | None = None,
    ) -> MemorySummary:
        memory = MemorySummary(
            user_id=user_id,
            memory_type=memory_type,
            title=title,
            content=content,
            evidence_refs=evidence_refs,
            embedding=embedding,
        )
        self.session.add(memory)
        await self.session.flush()
        return memory

    async def semantic_search(
        self, user_id: UUID, embedding: list[float], limit: int = 8
    ) -> list[tuple[LearningLog | MemorySummary, float]]:
        """Top rows across logs + memories by cosine distance (smaller = closer)."""
        log_distance = LearningLog.embedding.cosine_distance(embedding)
        log_result = await self.session.execute(
            select(LearningLog, log_distance.label("distance"))
            .where(
                LearningLog.user_id == user_id,
                LearningLog.embedding.is_not(None),
            )
            .order_by(log_distance)
            .limit(limit)
        )
        memory_distance = MemorySummary.embedding.cosine_distance(embedding)
        memory_result = await self.session.execute(
            select(MemorySummary, memory_distance.label("distance"))
            .where(
                MemorySummary.user_id == user_id,
                MemorySummary.embedding.is_not(None),
            )
            .order_by(memory_distance)
            .limit(limit)
        )
        combined = [(row[0], float(row[1])) for row in log_result.all()]
        combined.extend((row[0], float(row[1])) for row in memory_result.all())
        combined.sort(key=lambda pair: pair[1])
        return combined[:limit]

    async def logs_missing_embedding(self, limit: int = 100) -> list[LearningLog]:
        result = await self.session.execute(
            select(LearningLog)
            .where(LearningLog.embedding.is_(None))
            .order_by(LearningLog.created_at)
            .limit(limit)
        )
        return list(result.scalars())

    async def memories_missing_embedding(
        self, limit: int = 100
    ) -> list[MemorySummary]:
        result = await self.session.execute(
            select(MemorySummary)
            .where(MemorySummary.embedding.is_(None))
            .order_by(MemorySummary.created_at)
            .limit(limit)
        )
        return list(result.scalars())

    async def upsert_interaction_state(
        self, user_id: UUID, state_type: str, state_data: dict
    ) -> UserInteractionState:
        statement = (
            insert(UserInteractionState)
            .values(user_id=user_id, state_type=state_type, state_data=state_data)
            .on_conflict_do_update(
                constraint="uq_user_interaction_states_user_id",
                set_={
                    "state_type": state_type,
                    "state_data": state_data,
                    "updated_at": func.now(),
                },
            )
            .returning(UserInteractionState)
        )
        result = await self.session.execute(statement)
        return result.scalar_one()

    async def get_interaction_state(
        self, user_id: UUID
    ) -> UserInteractionState | None:
        result = await self.session.execute(
            select(UserInteractionState).where(UserInteractionState.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def clear_interaction_state(self, user_id: UUID) -> None:
        await self.session.execute(
            delete(UserInteractionState).where(UserInteractionState.user_id == user_id)
        )

    async def reset_user_data(self, user_id: UUID) -> dict[str, int]:
        activity_result = await self.session.execute(
            delete(ActivityEvent).where(ActivityEvent.user_id == user_id)
        )
        learning_result = await self.session.execute(
            delete(LearningLog).where(LearningLog.user_id == user_id)
        )
        goal_result = await self.session.execute(
            delete(DailyGoal).where(DailyGoal.user_id == user_id)
        )
        conversation_result = await self.session.execute(
            delete(ConversationMessage).where(ConversationMessage.user_id == user_id)
        )
        state_result = await self.session.execute(
            delete(UserInteractionState).where(UserInteractionState.user_id == user_id)
        )
        memory_result = await self.session.execute(
            delete(MemorySummary).where(MemorySummary.user_id == user_id)
        )
        outbound_result = await self.session.execute(
            delete(OutboundMessage).where(OutboundMessage.user_id == user_id)
        )
        readiness_result = await self.session.execute(
            delete(ReadinessScore).where(ReadinessScore.user_id == user_id)
        )
        mastery_result = await self.session.execute(
            delete(TopicMastery).where(TopicMastery.user_id == user_id)
        )
        weekly_plan_result = await self.session.execute(
            delete(WeeklyPlan).where(WeeklyPlan.user_id == user_id)
        )
        return {
            "activity_events_deleted": activity_result.rowcount or 0,
            "learning_logs_deleted": learning_result.rowcount or 0,
            "daily_goals_deleted": goal_result.rowcount or 0,
            "conversation_messages_deleted": conversation_result.rowcount or 0,
            "interaction_states_deleted": state_result.rowcount or 0,
            "memory_summaries_deleted": memory_result.rowcount or 0,
            "outbound_messages_deleted": outbound_result.rowcount or 0,
            "readiness_scores_deleted": readiness_result.rowcount or 0,
            "topic_mastery_deleted": mastery_result.rowcount or 0,
            "weekly_plans_deleted": weekly_plan_result.rowcount or 0,
        }

    async def add_outbound(
        self,
        *,
        user_id: UUID,
        message_type: str,
        content: str,
        delivered: bool,
        provider_message_id: str | None,
        workflow_run_id: UUID | None,
    ) -> None:
        self.session.add(
            OutboundMessage(
                user_id=user_id,
                message_type=message_type,
                content=content,
                delivered=delivered,
                provider_message_id=provider_message_id,
                workflow_run_id=workflow_run_id,
            )
        )

    async def count_outbound_today(
        self, user_id: UUID, message_type: str, day_start: datetime
    ) -> int:
        result = await self.session.execute(
            select(func.count(OutboundMessage.id)).where(
                OutboundMessage.user_id == user_id,
                OutboundMessage.message_type == message_type,
                OutboundMessage.created_at >= day_start,
            )
        )
        return int(result.scalar_one())

    async def start_workflow(
        self, request_id: str, workflow_type: str
    ) -> tuple[WorkflowRun, bool]:
        existing = await self.session.execute(
            select(WorkflowRun).where(WorkflowRun.request_id == request_id)
        )
        if run := existing.scalar_one_or_none():
            return run, False
        run = WorkflowRun(
            request_id=request_id,
            workflow_type=workflow_type,
            status=WorkflowStatus.RUNNING.value,
            started_at=datetime.now(UTC),
        )
        self.session.add(run)
        try:
            await self.session.flush()
            return run, True
        except IntegrityError:
            await self.session.rollback()
            result = await self.session.execute(
                select(WorkflowRun).where(WorkflowRun.request_id == request_id)
            )
            return result.scalar_one(), False

    async def finish_workflow(
        self,
        run: WorkflowRun,
        *,
        result: dict | None = None,
        error: str | None = None,
    ) -> None:
        run.status = (
            WorkflowStatus.FAILED.value if error else WorkflowStatus.SUCCEEDED.value
        )
        run.result = result or {}
        run.error = error
        run.finished_at = datetime.now(UTC)

    async def add_sync_run(
        self,
        source: str,
        status: str,
        records_processed: int,
        started_at: datetime,
        error: str | None = None,
    ) -> None:
        self.session.add(
            SyncRun(
                source=source,
                status=status,
                records_processed=records_processed,
                error=error,
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )
        )

    async def save_score(
        self,
        *,
        user_id: UUID,
        target_role: str,
        overall_score: float,
        confidence: float,
        score_version: str,
        subscores: dict,
        gap_analysis: dict,
        evidence: dict,
    ) -> ReadinessScore:
        score = ReadinessScore(
            user_id=user_id,
            target_role=target_role,
            overall_score=overall_score,
            confidence=confidence,
            score_version=score_version,
            subscores=subscores,
            gap_analysis=gap_analysis,
            evidence=evidence,
        )
        self.session.add(score)
        await self.session.flush()
        return score

    async def latest_score(self, user_id: UUID) -> ReadinessScore | None:
        result = await self.session.execute(
            select(ReadinessScore)
            .where(ReadinessScore.user_id == user_id)
            .order_by(ReadinessScore.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def latest_weekly_plan(self, user_id: UUID) -> WeeklyPlan | None:
        result = await self.session.execute(
            select(WeeklyPlan)
            .where(WeeklyPlan.user_id == user_id)
            .order_by(WeeklyPlan.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def save_weekly_plan(
        self, user_id: UUID, week_start: date, content: str, priorities: list[str]
    ) -> None:
        self.session.add(
            WeeklyPlan(
                user_id=user_id,
                week_start=week_start,
                content=content,
                priorities=priorities,
            )
        )

    async def operational_status(self) -> dict:
        latest_syncs = {}
        for source in ("github", "leetcode"):
            result = await self.session.execute(
                select(SyncRun)
                .where(SyncRun.source == source)
                .order_by(SyncRun.created_at.desc())
                .limit(1)
            )
            run = result.scalar_one_or_none()
            latest_syncs[source] = (
                {
                    "status": run.status,
                    "finished_at": (
                        run.finished_at.isoformat() if run.finished_at else None
                    ),
                    "records_processed": run.records_processed,
                }
                if run
                else None
            )
        workflow_result = await self.session.execute(
            select(WorkflowRun).order_by(WorkflowRun.created_at.desc()).limit(10)
        )
        score_result = await self.session.execute(
            select(ReadinessScore).order_by(ReadinessScore.created_at.desc()).limit(1)
        )
        score = score_result.scalar_one_or_none()
        return {
            "syncs": latest_syncs,
            "latest_readiness": (
                {
                    "score": score.overall_score,
                    "confidence": score.confidence,
                    "version": score.score_version,
                    "created_at": score.created_at.isoformat(),
                }
                if score
                else None
            ),
            "recent_workflows": [
                {
                    "type": run.workflow_type,
                    "status": run.status,
                    "request_id": run.request_id,
                    "created_at": run.created_at.isoformat(),
                }
                for run in workflow_result.scalars()
            ],
        }

    async def prune_raw_records(
        self, *, event_retention_days: int, message_retention_days: int
    ) -> dict[str, int]:
        now = datetime.now(UTC)
        event_cutoff = now - timedelta(days=event_retention_days)
        message_cutoff = now - timedelta(days=message_retention_days)
        model_log_cutoff = now - timedelta(days=30)
        processed_cutoff = now - timedelta(days=7)
        event_result = await self.session.execute(
            delete(ActivityEvent).where(ActivityEvent.created_at < event_cutoff)
        )
        message_result = await self.session.execute(
            delete(ConversationMessage).where(
                ConversationMessage.created_at < message_cutoff
            )
        )
        model_log_result = await self.session.execute(
            delete(ModelCallLog).where(ModelCallLog.created_at < model_log_cutoff)
        )
        processed_result = await self.session.execute(
            delete(ProcessedUpdate).where(
                ProcessedUpdate.processed_at < processed_cutoff
            )
        )
        return {
            "activity_events_deleted": event_result.rowcount or 0,
            "conversation_messages_deleted": message_result.rowcount or 0,
            "model_call_logs_deleted": model_log_result.rowcount or 0,
            "processed_updates_deleted": processed_result.rowcount or 0,
        }
