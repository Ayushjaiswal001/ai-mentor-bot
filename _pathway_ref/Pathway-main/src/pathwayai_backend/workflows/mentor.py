"""LangGraph workflows for the three scheduled mentor flows.

Each scheduled flow is a small StateGraph with named nodes so the run
can be visualized in LangSmith Studio and inspected node-by-node:

  morning_checkin
    START → load_events → load_logs → load_goal → load_instructions
          → load_due_topics → load_streak → merge_context
          → branch_mode (rest_day? → compose_light | compose_full)
          → compose (retry-wrapped) → deliver → END

  evening_reflection
    START → load_events → load_logs → load_goal → load_instructions
          → load_streak → merge_context
          → has_goal? (yes → score_goal → compose | no → compose)
          → compose (retry-wrapped) → deliver → END

  weekly_review
    START → evaluate → enough_evidence?
          (yes → compose → persist → deliver | no → compose_thin → persist → deliver)
          → END

State is a TypedDict that fans pieces of context in from the loader
nodes and gets read by the compose/score nodes downstream. Loaders run
sequentially because they share one AsyncSession — splitting them gives
LangSmith per-step timing without the concurrency hazard.
"""

import json
from datetime import date, datetime, timedelta
from typing import Any, TypedDict
from uuid import UUID
from zoneinfo import ZoneInfo

from langgraph.graph import END, START, StateGraph

from pathwayai_backend.config import Settings
from pathwayai_backend.db.repositories import Repository
from pathwayai_backend.integrations.telegram import TelegramClient
from pathwayai_backend.llm.gateway import ModelGateway
from pathwayai_backend.prompts.mentor import (
    EVENING_PROMPT,
    GOAL_OUTCOME_PROMPT,
    MENTOR_SYSTEM_PROMPT,
    MORNING_PROMPT,
    WEEKLY_REVIEW_PROMPT,
)
from pathwayai_backend.workflows.scoring import calculate_readiness

_REST_DAY_TRIGGERS = (
    "rest day",
    "won't study",
    "wont study",
    "not available",
    "taking a break",
    "sick",
    "travelling",
    "traveling",
)


class MentorState(TypedDict, total=False):
    user_id: UUID
    workflow_run_id: UUID

    # Pieces written by the loader nodes
    events: list
    logs: list
    goals: list
    instructions_raw: list
    due_topics: list
    streak: int

    # Aggregated text views consumed by compose nodes
    context: str
    instructions: str

    # Branching flags
    rest_day: bool
    has_goal: bool
    enough_evidence: bool

    # Output
    message: str
    provider: str
    delivered: bool
    provider_message_id: str | None
    score: dict[str, Any]


class MentorWorkflowEngine:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: Repository,
        model_gateway: ModelGateway,
        telegram: TelegramClient,
    ) -> None:
        from pathwayai_backend.llm.embeddings import EmbeddingGateway

        self.settings = settings
        self.repository = repository
        self.model_gateway = model_gateway
        self.telegram = telegram
        self.embeddings = EmbeddingGateway(settings)
        self._morning_graph = self._build_morning_graph()
        self._evening_graph = self._build_evening_graph()
        self._weekly_graph = self._build_weekly_graph()

    async def run_morning(
        self, user_id: UUID, workflow_run_id: UUID
    ) -> dict[str, Any]:
        result = await self._morning_graph.ainvoke(
            {"user_id": user_id, "workflow_run_id": workflow_run_id}
        )
        return self._public_result(result)

    async def run_evening(
        self, user_id: UUID, workflow_run_id: UUID
    ) -> dict[str, Any]:
        result = await self._evening_graph.ainvoke(
            {"user_id": user_id, "workflow_run_id": workflow_run_id}
        )
        return self._public_result(result)

    async def run_weekly(
        self, user_id: UUID, workflow_run_id: UUID
    ) -> dict[str, Any]:
        result = await self._weekly_graph.ainvoke(
            {"user_id": user_id, "workflow_run_id": workflow_run_id}
        )
        public = self._public_result(result)
        public["score"] = result["score"]
        return public

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _build_morning_graph(self):
        graph = StateGraph(MentorState)
        graph.add_node("load_events", self._load_events)
        graph.add_node("load_logs", self._load_logs)
        graph.add_node("load_goal", self._load_goal)
        graph.add_node("load_instructions", self._load_instructions)
        graph.add_node("load_due_topics", self._load_due_topics)
        graph.add_node("load_streak", self._load_streak)
        graph.add_node("merge_context", self._merge_context)
        graph.add_node("compose", self._compose_morning_with_retry)
        graph.add_node("deliver", self._deliver_morning)

        graph.add_edge(START, "load_events")
        graph.add_edge("load_events", "load_logs")
        graph.add_edge("load_logs", "load_goal")
        graph.add_edge("load_goal", "load_instructions")
        graph.add_edge("load_instructions", "load_due_topics")
        graph.add_edge("load_due_topics", "load_streak")
        graph.add_edge("load_streak", "merge_context")
        graph.add_edge("merge_context", "compose")
        graph.add_edge("compose", "deliver")
        graph.add_edge("deliver", END)
        return graph.compile()

    def _build_evening_graph(self):
        graph = StateGraph(MentorState)
        graph.add_node("load_events", self._load_events)
        graph.add_node("load_logs", self._load_logs)
        graph.add_node("load_goal", self._load_goal)
        graph.add_node("load_instructions", self._load_instructions)
        graph.add_node("load_streak", self._load_streak)
        graph.add_node("merge_context", self._merge_context)
        graph.add_node("score_goal", self._score_today_goal)
        graph.add_node("compose", self._compose_evening_with_retry)
        graph.add_node("deliver", self._deliver_evening)

        graph.add_edge(START, "load_events")
        graph.add_edge("load_events", "load_logs")
        graph.add_edge("load_logs", "load_goal")
        graph.add_edge("load_goal", "load_instructions")
        graph.add_edge("load_instructions", "load_streak")
        graph.add_edge("load_streak", "merge_context")
        # Conditional: only score the goal when there is one to score.
        graph.add_conditional_edges(
            "merge_context",
            self._has_goal_router,
            {"score": "score_goal", "skip": "compose"},
        )
        graph.add_edge("score_goal", "compose")
        graph.add_edge("compose", "deliver")
        graph.add_edge("deliver", END)
        return graph.compile()

    def _build_weekly_graph(self):
        graph = StateGraph(MentorState)
        graph.add_node("evaluate", self._evaluate_week)
        graph.add_node("compose", self._compose_weekly_with_retry)
        graph.add_node("compose_thin", self._compose_weekly_thin)
        graph.add_node("persist", self._persist_weekly)
        graph.add_node("deliver", self._deliver_weekly)

        graph.add_edge(START, "evaluate")
        # Conditional: when there's barely any evidence, use the thin
        # composer that doesn't pretend to a confident weekly verdict.
        graph.add_conditional_edges(
            "evaluate",
            self._enough_evidence_router,
            {"full": "compose", "thin": "compose_thin"},
        )
        graph.add_edge("compose", "persist")
        graph.add_edge("compose_thin", "persist")
        graph.add_edge("persist", "deliver")
        graph.add_edge("deliver", END)
        return graph.compile()

    # ------------------------------------------------------------------
    # Loader nodes (sequential; share one AsyncSession)
    # ------------------------------------------------------------------

    async def _load_events(self, state: MentorState) -> MentorState:
        events = await self.repository.recent_events(state["user_id"], days=2)
        return {**state, "events": events}

    async def _load_logs(self, state: MentorState) -> MentorState:
        logs = await self.repository.recent_logs(state["user_id"], days=2)
        return {**state, "logs": logs}

    async def _load_goal(self, state: MentorState) -> MentorState:
        goals = await self.repository.goals_for_date(
            state["user_id"], self._local_date()
        )
        return {**state, "goals": goals, "has_goal": bool(goals)}

    async def _load_instructions(self, state: MentorState) -> MentorState:
        instructions = await self.repository.recent_memories_by_type(
            state["user_id"], "user_instruction", days=7
        )
        return {**state, "instructions_raw": instructions}

    async def _load_due_topics(self, state: MentorState) -> MentorState:
        due_topics = await self.repository.due_topics(state["user_id"], limit=5)
        return {**state, "due_topics": due_topics}

    async def _load_streak(self, state: MentorState) -> MentorState:
        log_timestamps = await self.repository.log_dates(state["user_id"], days=60)
        tz = ZoneInfo(self.settings.user_timezone)
        log_days = {ts.astimezone(tz).date() for ts in log_timestamps}
        streak = 0
        cursor = self._local_date()
        while cursor in log_days:
            streak += 1
            cursor -= timedelta(days=1)
        return {**state, "streak": streak}

    async def _merge_context(self, state: MentorState) -> MentorState:
        events = state.get("events", [])
        logs = state.get("logs", [])
        goals = state.get("goals") or []
        due_topics = state.get("due_topics", [])
        streak = state.get("streak", 0)
        instructions = state.get("instructions_raw", [])
        context = {
            "today_goals": [g.content for g in goals] or "No goals declared yet",
            "recent_events": [
                {
                    "source": event.source,
                    "type": event.event_type,
                    "occurred_at": event.occurred_at.isoformat(),
                    "details": event.payload,
                }
                for event in events[:20]
            ],
            "recent_logs": [
                {
                    "content": log.content,
                    "topic": log.topic,
                    "difficulty": log.difficulty,
                }
                for log in logs[:10]
            ],
            "topics_due_for_review": [
                {"topic": row.topic, "level": row.level} for row in due_topics
            ],
            "log_streak_days": streak,
        }
        instructions_text = "\n".join(
            f"- {item.created_at.date().isoformat()}: {item.content}"
            for item in instructions
        ) or "None"
        rest_day = any(
            trigger in (item.content or "").lower()
            for item in instructions
            for trigger in _REST_DAY_TRIGGERS
        )
        return {
            **state,
            "context": str(context),
            "instructions": instructions_text,
            "rest_day": rest_day,
        }

    # ------------------------------------------------------------------
    # Conditional routers
    # ------------------------------------------------------------------

    @staticmethod
    def _has_goal_router(state: MentorState) -> str:
        return "score" if state.get("has_goal") else "skip"

    @staticmethod
    def _enough_evidence_router(state: MentorState) -> str:
        score = state.get("score") or {}
        # "Enough" = at least one log OR a real readiness signal.
        if score.get("overall_score", 0) >= 20:
            return "full"
        evidence = (score.get("evidence") or {}).get("logs_count", 0)
        return "full" if evidence >= 3 else "thin"

    # ------------------------------------------------------------------
    # Scoring (evening, conditional)
    # ------------------------------------------------------------------

    async def _score_today_goal(self, state: MentorState) -> MentorState:
        today = self._local_date()
        goals = state.get("goals") or []
        if not goals:
            return state
        logs = await self.repository.recent_logs(state["user_id"], days=1)
        events = await self.repository.recent_events(state["user_id"], days=1)
        logs_block = (
            "\n".join(f"- {log.content}" for log in logs[:10]) or "None"
        )
        events_block = (
            "\n".join(
                f"- {event.source}:{event.event_type}" for event in events[:15]
            )
            or "None"
        )
        # Score each goal independently so attribution is honest. A small
        # number of goals × one cheap JSON call each is fine; users rarely
        # have more than 3 in a day.
        newly_completed: list[str] = []
        for goal in goals:
            result = await self.model_gateway.generate(
                system_prompt=MENTOR_SYSTEM_PROMPT,
                user_prompt=GOAL_OUTCOME_PROMPT.format(
                    goal=goal.content,
                    instructions=state.get("instructions", "None"),
                    logs=logs_block,
                    events=events_block,
                ),
                fallback="",
                json_mode=True,
            )
            status = self._parse_goal_status(result.content)
            if not status:
                continue
            previous_status = goal.status
            await self.repository.update_goal_status_by_id(goal.id, status)
            outcome_content = f"Status: {status}. Goal: {goal.content}"
            await self.repository.add_memory(
                state["user_id"],
                "goal_outcome",
                f"Goal outcome {today.isoformat()}",
                outcome_content,
                [],
                embedding=await self.embeddings.embed(outcome_content),
            )
            if status == "completed" and previous_status != "completed":
                newly_completed.append(goal.content)
        if newly_completed:
            streak_line = ""
            streak = state.get("streak", 0)
            if streak >= 2:
                streak_line = f"\n🔥 Streak: {streak} days"
            bullet_list = "\n".join(f"• {item}" for item in newly_completed)
            try:
                await self.telegram.send_message(
                    f"🎯 Goal{'s' if len(newly_completed) > 1 else ''} "
                    f"completed:\n{bullet_list}\n"
                    "Nice — marked done for today."
                    f"{streak_line}"
                )
            except Exception:
                pass
        return state

    @staticmethod
    def _parse_goal_status(raw: str) -> str | None:
        text = (raw or "").strip()
        if not text:
            return None
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
        status = str(data.get("status", "")).lower().strip()
        if status in {"completed", "partial", "skipped"}:
            return status
        return None

    # ------------------------------------------------------------------
    # Compose nodes (LLM calls, retry-wrapped with a deterministic fallback)
    # ------------------------------------------------------------------

    async def _compose_morning_with_retry(self, state: MentorState) -> MentorState:
        return await self._compose_with_retry(
            state,
            prompt=MORNING_PROMPT.format(
                context=state["context"],
                instructions=state.get("instructions", "None"),
            ),
            fallback=(
                "Good morning. What are your concrete goals today? "
                "Reply with `/goals <your goals>`. Choose work that creates interview "
                "evidence: one implementation task, one problem-solving task, and one "
                "concept you can explain without notes."
            ),
        )

    async def _compose_evening_with_retry(self, state: MentorState) -> MentorState:
        return await self._compose_with_retry(
            state,
            prompt=EVENING_PROMPT.format(
                context=state["context"],
                instructions=state.get("instructions", "None"),
            ),
            fallback=(
                "How did today actually go compared with your stated goals? Tell me what "
                "you completed, what blocked you, and explain one technical decision you "
                "made as if I were interviewing you."
            ),
        )

    async def _compose_weekly_with_retry(self, state: MentorState) -> MentorState:
        score = state["score"]
        fallback = (
            f"Weekly readiness estimate: {score['overall_score']}% "
            f"(confidence {score['confidence']:.0%}). "
            f"Missing evidence or gaps: "
            f"{', '.join(score['gap_analysis']['missing_evidence_or_gaps']) or 'none'}. "
            "Next week: ship one meaningful project increment, practice DSA on at "
            "least three days, and complete two interview-style explanations."
        )
        return await self._compose_with_retry(
            state,
            prompt=WEEKLY_REVIEW_PROMPT.format(context=state["context"]),
            fallback=fallback,
        )

    async def _compose_weekly_thin(self, state: MentorState) -> MentorState:
        """Weekly composer for sparse-evidence weeks. Avoids the LLM
        pretending it has data it doesn't and gives a directive plan
        instead."""
        score = state["score"]
        message = (
            "Not enough evidence to grade this week. "
            f"Readiness model: {score['overall_score']}% "
            f"(confidence {score['confidence']:.0%}).\n\n"
            "Next week's plan:\n"
            "1. Ship one project increment with tests — even a small PR counts.\n"
            "2. Log every session with `/log` so the model has signal to read.\n"
            "3. Run `/mock` on the topic you're weakest in and post the transcript."
        )
        return {**state, "message": message, "provider": "deterministic"}

    async def _compose_with_retry(
        self, state: MentorState, *, prompt: str, fallback: str
    ) -> MentorState:
        # LangGraph doesn't ship a first-class retry primitive; the model
        # gateway already retries inside, but we add one outer attempt
        # with the deterministic fallback so a node failure can't take a
        # scheduled flow down.
        try:
            result = await self.model_gateway.generate(
                system_prompt=MENTOR_SYSTEM_PROMPT,
                user_prompt=prompt,
                fallback=fallback,
            )
            return {**state, "message": result.content, "provider": result.provider}
        except Exception:
            return {**state, "message": fallback, "provider": "fallback"}

    # ------------------------------------------------------------------
    # Weekly: evaluate + persist
    # ------------------------------------------------------------------

    async def _evaluate_week(self, state: MentorState) -> MentorState:
        events = await self.repository.recent_events(state["user_id"], days=7)
        logs = await self.repository.recent_logs(state["user_id"], days=7)
        memories = await self.repository.recent_memories(state["user_id"], days=30)
        score = calculate_readiness(events, logs, memories)
        context = {
            "score": score.as_dict(),
            "recent_events": [
                {"source": event.source, "type": event.event_type}
                for event in events[:50]
            ],
            "learning_logs": [log.content for log in logs[:20]],
            "interview_assessments": [
                memory.content
                for memory in memories
                if memory.memory_type == "interview_assessment"
            ][:10],
        }
        return {**state, "score": score.as_dict(), "context": str(context)}

    async def _persist_weekly(self, state: MentorState) -> MentorState:
        score = state["score"]
        await self.repository.save_score(
            user_id=state["user_id"],
            target_role=self.settings.target_role,
            overall_score=score["overall_score"],
            confidence=score["confidence"],
            score_version=score["score_version"],
            subscores=score["subscores"],
            gap_analysis=score["gap_analysis"],
            evidence=score["evidence"],
        )
        priorities = score["gap_analysis"]["missing_evidence_or_gaps"][:3]
        today = self._local_date()
        week_start = today - timedelta(days=today.weekday())
        await self.repository.save_weekly_plan(
            state["user_id"],
            week_start,
            state["message"],
            priorities,
        )
        await self.repository.add_memory(
            state["user_id"],
            "weekly_review",
            f"Weekly review {self._local_date().isoformat()}",
            state["message"],
            [],
            embedding=await self.embeddings.embed(state["message"]),
        )
        return state

    # ------------------------------------------------------------------
    # Delivery nodes
    # ------------------------------------------------------------------

    async def _deliver_morning(self, state: MentorState) -> MentorState:
        return await self._deliver(state, "morning_checkin")

    async def _deliver_evening(self, state: MentorState) -> MentorState:
        return await self._deliver(state, "evening_reflection")

    async def _deliver_weekly(self, state: MentorState) -> MentorState:
        return await self._deliver(state, "weekly_review")

    async def _deliver(self, state: MentorState, message_type: str) -> MentorState:
        delivery = await self.telegram.send_message(state["message"])
        await self.repository.add_outbound(
            user_id=state["user_id"],
            message_type=message_type,
            content=state["message"],
            delivered=delivery.delivered,
            provider_message_id=delivery.message_id,
            workflow_run_id=state["workflow_run_id"],
        )
        return {
            **state,
            "delivered": delivery.delivered,
            "provider_message_id": delivery.message_id,
        }

    # ------------------------------------------------------------------

    def _local_date(self) -> date:
        return datetime.now(ZoneInfo(self.settings.user_timezone)).date()

    @staticmethod
    def _public_result(state: MentorState) -> dict[str, Any]:
        return {
            "message": state["message"],
            "provider": state["provider"],
            "delivered": state.get("delivered", False),
            "provider_message_id": state.get("provider_message_id"),
        }
