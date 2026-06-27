import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from pathwayai_backend.config import Settings
from pathwayai_backend.db.repositories import Repository
from pathwayai_backend.integrations.telegram import InlineAction, TelegramClient
from pathwayai_backend.llm.embeddings import EmbeddingGateway
from pathwayai_backend.llm.gateway import ModelGateway
from pathwayai_backend.prompts.mentor import (
    CHAT_SUMMARY_PROMPT,
    CODE_REVIEW_PROMPT,
    LOG_EXTRACTION_PROMPT,
    LOG_QUIZ_PROMPT,
    MENTOR_SYSTEM_PROMPT,
    MOCK_INTERVIEW_FINAL_PROMPT,
    MOCK_INTERVIEW_OPENER_PROMPT,
    TUTOR_QUESTION_PROMPT,
)

logger = structlog.get_logger(__name__)


def _short_button_label(text: str, limit: int = 14) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    if " " in cut.strip():
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip() + "…"


class TelegramUpdateService:
    KEYBOARD_REMOVAL_ACTIONS = {"help_returned"}
    SPACED_REPETITION_DAYS = {
        "exposure": 1,
        "conceptual": 3,
        "implementation": 7,
        "interview-ready": 14,
    }
    GOAL_TEMPLATES = {
        "dsa": (
            "DSA day: solve 2 medium problems on the weakest topic, write up the "
            "approach for each, and explain one tradeoff out loud."
        ),
        "systems": (
            "Systems day: design one system end-to-end (API + storage + scaling), "
            "implement one slice in code, and list three failure modes."
        ),
        "review": (
            "Review day: re-quiz the three weakest topics from /status, refresh one "
            "interview story per topic, and log gaps you still feel."
        ),
        "project": (
            "Project day: ship one meaningful PR or feature increment with tests, "
            "and write the interview story for it before logging."
        ),
    }
    MOCK_MAX_TURNS = 5

    def __init__(self, settings: Settings, session: AsyncSession) -> None:
        self.settings = settings
        self.session = session
        self.repository = Repository(session)
        self.telegram = TelegramClient(settings)
        self.models = ModelGateway(settings)
        self.embeddings = EmbeddingGateway(settings)
        self.models.set_call_logger(self._log_model_call)
        # Conversational LangGraph workflows — built lazily so tests
        # that construct the service via object.__new__ don't pay the
        # build cost until they actually drive a graph.
        self._quiz_graph = None
        self._mock_graph = None
        self._chat_graph = None
        self._log_extraction_graph = None

    def _get_quiz_graph(self):
        # getattr fallback covers tests that build the service via
        # object.__new__ without running __init__.
        if getattr(self, "_quiz_graph", None) is None:
            from pathwayai_backend.workflows.conversation import build_quiz_graph

            self._quiz_graph = build_quiz_graph(self)
        return self._quiz_graph

    def _get_mock_graph(self):
        if getattr(self, "_mock_graph", None) is None:
            from pathwayai_backend.workflows.conversation import (
                build_mock_interview_graph,
            )

            self._mock_graph = build_mock_interview_graph(self)
        return self._mock_graph

    def _get_chat_graph(self):
        if getattr(self, "_chat_graph", None) is None:
            from pathwayai_backend.workflows.conversation import build_chat_graph

            self._chat_graph = build_chat_graph(self)
        return self._chat_graph

    def _get_log_extraction_graph(self):
        if getattr(self, "_log_extraction_graph", None) is None:
            from pathwayai_backend.workflows.conversation import (
                build_log_extraction_graph,
            )

            self._log_extraction_graph = build_log_extraction_graph(self)
        return self._log_extraction_graph

    async def _log_model_call(self, **kwargs) -> None:
        try:
            await self.repository.log_model_call(**kwargs)
        except Exception:
            logger.warning("model_call_log_failed", exc_info=True)

    async def _claim_update_safe(self, source: str, external_id: str) -> bool:
        # Dedup should not take the whole bot down if the latest migration
        # has not been applied in the runtime database yet.
        try:
            return await self.repository.claim_update(source, external_id)
        except Exception:
            return True

    async def handle(self, update: dict[str, Any]) -> str:
        update_id = update.get("update_id")
        if update_id is not None:
            claimed = await self._claim_update_safe("telegram", str(update_id))
            if not claimed:
                await self.session.commit()
                return "duplicate_update"

        if callback_query := update.get("callback_query"):
            action = await self._handle_callback(callback_query)
            await self.session.commit()
            return action

        message = update.get("message") or update.get("edited_message")
        if not isinstance(message, dict):
            return "ignored_non_message_update"
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id", ""))
        text = str(message.get("text", "")).strip()
        message_id = str(message.get("message_id", ""))
        if not chat_id or not text or not message_id:
            return "ignored_unsupported_message"
        allowlist = self.settings.telegram_chat_allowlist
        if allowlist and chat_id not in allowlist:
            return "ignored_unknown_chat"

        sender = message.get("from") or {}
        user = await self.repository.get_or_create_user(
            telegram_chat_id=chat_id,
            display_name=str(sender.get("first_name") or self.settings.default_user_name),
            target_role=self.settings.target_role,
            timezone=self.settings.user_timezone,
        )
        await self.repository.add_message(
            user_id=user.id,
            external_message_id=message_id,
            direction="inbound",
            content=text,
            metadata={"update_id": update.get("update_id")},
        )

        if await self._is_rate_limited(user.id):
            logger.warning(
                "rate_limited",
                user_id=str(user.id),
                chat_id=chat_id,
            )
            await self.session.commit()
            return "rate_limited"

        command, argument = self._split_command(text)

        if state := await self.repository.get_interaction_state(user.id):
            if state.state_type == "onboarding" and command in {"/start", "/restart"}:
                response = await self._restart_onboarding(user.id)
                delivery = await self.telegram.send_message(response, chat_id=chat_id)
                await self.repository.add_outbound(
                    user_id=user.id,
                    message_type="onboarding_step",
                    content=response,
                    delivered=delivery.delivered,
                    provider_message_id=delivery.message_id,
                    workflow_run_id=None,
                )
                await self.session.commit()
                return "onboarding_restarted"
            if state.state_type == "quiz_waiting_answer":
                response = await self._handle_quiz_answer(user.id, state.state_data, text)
                delivery = await self.telegram.send_message(response, chat_id=chat_id)
                await self.repository.add_outbound(
                    user_id=user.id,
                    message_type="quiz_answer_processed",
                    content=response,
                    delivered=delivery.delivered,
                    provider_message_id=delivery.message_id,
                    workflow_run_id=None,
                )
                await self.session.commit()
                return "quiz_answer_processed"
            if state.state_type == "onboarding":
                response, completed = await self._continue_onboarding(
                    user.id, state.state_data, text
                )
                delivery = await self.telegram.send_message(response, chat_id=chat_id)
                await self.repository.add_outbound(
                    user_id=user.id,
                    message_type="onboarding_step",
                    content=response,
                    delivered=delivery.delivered,
                    provider_message_id=delivery.message_id,
                    workflow_run_id=None,
                )
                if completed and delivery.delivered and delivery.message_id:
                    try:
                        await self.telegram.pin_message(
                            chat_id=chat_id,
                            message_id=delivery.message_id,
                        )
                    except Exception:
                        logger.warning("onboarding_pin_failed", exc_info=True)
                await self.session.commit()
                return "onboarding_step"
            if state.state_type == "log_waiting_edit":
                response = await self._apply_log_edit(user.id, state.state_data, text)
                delivery = await self.telegram.send_message(response, chat_id=chat_id)
                await self.repository.add_outbound(
                    user_id=user.id,
                    message_type="log_edited",
                    content=response,
                    delivered=delivery.delivered,
                    provider_message_id=delivery.message_id,
                    workflow_run_id=None,
                )
                await self.session.commit()
                return "log_edited"
            if state.state_type == "mock_interview":
                if text.strip().lower() in {"/end", "end", "stop"}:
                    response = await self._finish_mock_interview(
                        user.id, state.state_data, ended_early=True
                    )
                    action = "mock_interview_finished"
                else:
                    response, finished = await self._handle_mock_answer(
                        user.id, state.state_data, text
                    )
                    action = "mock_interview_finished" if finished else "mock_interview_turn"
                delivery = await self.telegram.send_message(response, chat_id=chat_id)
                await self.repository.add_outbound(
                    user_id=user.id,
                    message_type=action,
                    content=response,
                    delivered=delivery.delivered,
                    provider_message_id=delivery.message_id,
                    workflow_run_id=None,
                )
                await self.session.commit()
                return action

        _pending_log_extraction: tuple[UUID, str] | None = None
        if command == "/goals":
            if argument.strip():
                response = await self._record_goals(user.id, argument)
                action = "goals_recorded"
                inline_actions = None
            else:
                response, inline_actions = await self._show_goals(user.id)
                action = "goals_returned"
        elif command == "/log":
            response, inline_actions, _log_id, _log_content = await self._record_log(
                user.id, argument
            )
            action = "learning_log_recorded"
            _pending_log_extraction = (
                (_log_id, _log_content) if _log_id else None
            )
        elif command == "/logs":
            response, inline_actions = await self._show_logs(user.id)
            action = "logs_returned"
        elif command == "/status":
            response = await self._status(user.id)
            action = "status_returned"
            inline_actions = None
        elif command == "/forgetme":
            response = await self._forget_me(user.id, argument)
            action = (
                "memory_reset"
                if argument.strip().lower() == "confirm"
                else "memory_reset_prompt"
            )
            inline_actions = None
        elif command == "/next":
            response = await self._next_plan(user.id)
            action = "plan_returned"
            inline_actions = None
        elif command == "/ask":
            response = await self._answer_question(user.id, argument)
            action = "question_answered"
            inline_actions = None
        elif command == "/activity":
            response = await self._show_activity(user.id)
            action = "activity_returned"
            inline_actions = None
        elif command == "/mastery":
            response, inline_actions = await self._show_mastery(user.id)
            action = "mastery_returned"
        elif command == "/review":
            response = await self._start_review(user.id)
            action = "review_started"
            inline_actions = None
        elif command == "/version":
            from pathwayai_backend.core.version import app_version

            response = f"version: {app_version()}"
            action = "version_returned"
            inline_actions = None
        elif command == "/export":
            response = await self._export_bundle(user.id, argument, chat_id)
            action = "export_sent"
            inline_actions = None
        elif command == "/codereview":
            response, inline_actions, _log_id, _log_content = await self._code_review(
                user.id, argument
            )
            action = "code_review_recorded"
            _pending_log_extraction = (
                (_log_id, _log_content) if _log_id else None
            )
        elif command == "/stories":
            response, inline_actions = await self._show_stories(user.id)
            action = "stories_returned"
        elif command == "/search":
            response, inline_actions = await self._semantic_search(
                user.id, argument
            )
            action = "search_returned"
        elif command == "/mock":
            response = await self._start_mock_interview(user.id, argument)
            action = "mock_interview_started"
            inline_actions = None
        elif command == "/start":
            response = await self._maybe_start_onboarding(user.id) or self._help_text()
            action = "onboarding_step" if "Welcome" in response else "help_returned"
            inline_actions = None
        elif command == "/help":
            response = self._help_text(full=argument.strip().lower() == "all")
            action = "help_returned"
            inline_actions = None
        else:
            placeholder = await self.telegram.send_message(
                "_Thinking..._", chat_id=chat_id
            )
            response = await self._chat(user.id, text)
            action = "chat_reply"
            inline_actions = None
            if placeholder.delivered and placeholder.message_id:
                try:
                    await self.telegram.edit_message(
                        chat_id=chat_id,
                        message_id=placeholder.message_id,
                        text=response,
                    )
                    await self.repository.add_outbound(
                        user_id=user.id,
                        message_type=action,
                        content=response,
                        delivered=True,
                        provider_message_id=placeholder.message_id,
                        workflow_run_id=None,
                    )
                    await self.session.commit()
                    return action
                except Exception:
                    pass

        delivery = await self.telegram.send_message(
            response,
            chat_id=chat_id,
            inline_actions=inline_actions,
            remove_keyboard=action in self.KEYBOARD_REMOVAL_ACTIONS,
        )
        await self.repository.add_outbound(
            user_id=user.id,
            message_type=action,
            content=response,
            delivered=delivery.delivered,
            provider_message_id=delivery.message_id,
            workflow_run_id=None,
        )
        await self.session.commit()
        if _pending_log_extraction is not None:
            log_id, log_content = _pending_log_extraction
            try:
                await self._finalize_log_extraction(
                    log_id, log_content, chat_id, user.id
                )
            except Exception:
                logger.warning("log_finalize_failed", exc_info=True)
        return action

    async def _handle_callback(self, callback_query: dict[str, Any]) -> str:
        callback_id = str(callback_query.get("id", ""))
        data = str(callback_query.get("data", ""))
        message = callback_query.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id", ""))
        sender = callback_query.get("from") or {}
        if not callback_id or not data or not chat_id:
            return "ignored_callback"
        allowlist = self.settings.telegram_chat_allowlist
        if allowlist and chat_id not in allowlist:
            return "ignored_unknown_chat"
        claimed = await self._claim_update_safe("telegram_cb", callback_id)
        if not claimed:
            return "duplicate_callback"

        user = await self.repository.get_or_create_user(
            telegram_chat_id=chat_id,
            display_name=str(sender.get("first_name") or self.settings.default_user_name),
            target_role=self.settings.target_role,
            timezone=self.settings.user_timezone,
        )

        if data.startswith("quiz_log:"):
            log_id = data.split(":", 1)[1]
            response = await self._start_quiz(user.id, log_id)
            await self.telegram.answer_callback(callback_id, "Starting quiz")
            delivery = await self.telegram.send_message(response, chat_id=chat_id)
            await self.repository.add_outbound(
                user_id=user.id,
                message_type="quiz_started",
                content=response,
                delivered=delivery.delivered,
                provider_message_id=delivery.message_id,
                workflow_run_id=None,
            )
            await self.session.commit()
            return "quiz_started"

        if data.startswith("quiz_topic:"):
            topic = data.split(":", 1)[1]
            log = await self.repository.latest_log_for_topic(user.id, topic)
            if log is None:
                response = (
                    f"No log found for topic '{topic}'. Add a /log first and "
                    "I'll quiz you on it."
                )
            else:
                response = await self._start_quiz(user.id, str(log.id))
            await self.telegram.answer_callback(callback_id, "Starting quiz")
            delivery = await self.telegram.send_message(response, chat_id=chat_id)
            await self.repository.add_outbound(
                user_id=user.id,
                message_type="quiz_started",
                content=response,
                delivered=delivery.delivered,
                provider_message_id=delivery.message_id,
                workflow_run_id=None,
            )
            await self.session.commit()
            return "quiz_started"

        if data.startswith("logs:"):
            response, inline_actions = await self._show_logs(user.id)
            await self.telegram.answer_callback(callback_id, "Opening logs")
            delivery = await self.telegram.send_message(
                response, chat_id=chat_id, inline_actions=inline_actions
            )
            await self.repository.add_outbound(
                user_id=user.id,
                message_type="logs_returned",
                content=response,
                delivered=delivery.delivered,
                provider_message_id=delivery.message_id,
                workflow_run_id=None,
            )
            await self.session.commit()
            return "logs_returned"

        if data.startswith("log:delete:"):
            log_id = data.split(":", 2)[2]
            response = await self._delete_log_by_id(user.id, log_id)
            await self.telegram.answer_callback(callback_id, "Deleted")
            delivery = await self.telegram.send_message(response, chat_id=chat_id)
            await self.repository.add_outbound(
                user_id=user.id,
                message_type="log_deleted",
                content=response,
                delivered=delivery.delivered,
                provider_message_id=delivery.message_id,
                workflow_run_id=None,
            )
            await self.session.commit()
            return "log_deleted"

        if data.startswith("log:edit:"):
            log_id = data.split(":", 2)[2]
            response = await self._begin_log_edit(user.id, log_id)
            await self.telegram.answer_callback(callback_id, "Send new text")
            delivery = await self.telegram.send_message(response, chat_id=chat_id)
            await self.repository.add_outbound(
                user_id=user.id,
                message_type="log_edit_requested",
                content=response,
                delivered=delivery.delivered,
                provider_message_id=delivery.message_id,
                workflow_run_id=None,
            )
            await self.session.commit()
            return "log_edit_requested"

        if data == "goal:clear":
            local_day = datetime.now(ZoneInfo(self.settings.user_timezone)).date()
            removed = await self.repository.delete_goal(user.id, local_day)
            response = (
                f"Cleared {removed} goal(s) for today. "
                "Send `/goals <text>` to add new ones."
                if removed
                else "No goals set for today."
            )
            await self.telegram.answer_callback(callback_id, "Goals cleared")
            delivery = await self.telegram.send_message(response, chat_id=chat_id)
            await self.repository.add_outbound(
                user_id=user.id,
                message_type="goal_cleared",
                content=response,
                delivered=delivery.delivered,
                provider_message_id=delivery.message_id,
                workflow_run_id=None,
            )
            await self.session.commit()
            return "goal_cleared"

        if data.startswith("goal:done:") or data.startswith("goal:delete:"):
            action_name, _, goal_id_raw = data.partition(":")[2].partition(":")
            try:
                goal_id = UUID(goal_id_raw)
            except ValueError:
                await self.telegram.answer_callback(callback_id, "Bad goal id")
                return "ignored_callback"
            goal = await self.repository.get_goal_by_id(goal_id)
            if goal is None or goal.user_id != user.id:
                await self.telegram.answer_callback(callback_id, "Goal not found")
                return "ignored_callback"
            if action_name == "done":
                await self.repository.update_goal_status_by_id(
                    goal_id, "completed"
                )
                ack, message_type = "Marked done", "goal_marked_done"
                response = f"✅ Marked done: {goal.content}"
            else:
                await self.repository.delete_goal_by_id(goal_id)
                ack, message_type = "Goal deleted", "goal_deleted"
                response = f"Deleted goal: {goal.content}"
            await self.telegram.answer_callback(callback_id, ack)
            delivery = await self.telegram.send_message(response, chat_id=chat_id)
            await self.repository.add_outbound(
                user_id=user.id,
                message_type=message_type,
                content=response,
                delivered=delivery.delivered,
                provider_message_id=delivery.message_id,
                workflow_run_id=None,
            )
            await self.session.commit()
            return message_type

        if data == "plan:show":
            response = await self._next_plan(user.id)
            await self.telegram.answer_callback(callback_id, "Opening plan")
            delivery = await self.telegram.send_message(response, chat_id=chat_id)
            await self.repository.add_outbound(
                user_id=user.id,
                message_type="plan_returned",
                content=response,
                delivered=delivery.delivered,
                provider_message_id=delivery.message_id,
                workflow_run_id=None,
            )
            await self.session.commit()
            return "plan_returned"

        await self.telegram.answer_callback(callback_id, "Action unavailable")
        return "ignored_callback"

    async def _record_goals(self, user_id, argument: str) -> str:
        if not argument.strip():
            return (
                "Tell me today's concrete goals. Example:\n"
                "/goals Finish auth API refactor\n"
                "/goals Solve 2 graph problems\n\n"
                "Each call appends. View or remove them with /goals.\n"
                "Templates: /goals dsa | systems | review | project"
            )
        token = argument.strip().lower()
        local_day = datetime.now(ZoneInfo(self.settings.user_timezone)).date()
        # Templates expand to a single goal; otherwise split on newlines so
        # `/goals A\nB\nC` becomes three rows.
        if token in self.GOAL_TEMPLATES:
            contents = [self.GOAL_TEMPLATES[token]]
            template_note = f" (template: {token})"
        else:
            contents = [
                line.strip()
                for line in argument.strip().splitlines()
                if line.strip()
            ]
            template_note = ""
        for content in contents:
            await self.repository.add_goal(user_id, local_day, content)
        all_today = await self.repository.goals_for_date(user_id, local_day)
        if len(contents) > 1:
            head = f"{len(contents)} goals added{template_note}."
        else:
            head = f"Goal added{template_note}."
        body = "\n".join(f"- {g.content}" for g in all_today)
        return (
            f"{head} Today's goals ({len(all_today)} total):\n{body}\n\n"
            "I will compare these with observed activity tonight."
        )

    async def _record_log(
        self, user_id, argument: str
    ) -> tuple[str, list[InlineAction] | None, UUID | None, str | None]:
        """Save the log immediately. Extraction is deferred to the caller so we can
        ack first and update the user with the detected topic afterwards."""
        if not argument.strip():
            return (
                "Send me a progress update. Example:\n"
                "/log Implemented token refresh, fixed a webhook bug, and understood why idempotency matters here."
            ), None, None, None
        content = argument.strip()
        log = await self.repository.add_learning_log(user_id, content)
        return (
            "Logged. Indexing topic in the background — you can already tap "
            "Quiz Me when ready.",
            [
                InlineAction("Quiz Me", f"quiz_log:{log.id}"),
                InlineAction("View Logs", "logs:recent"),
            ],
            log.id,
            content,
        )

    async def _finalize_log_extraction(
        self, log_id: UUID, content: str, chat_id: str, user_id: UUID
    ) -> None:
        """Thin invoker for the log_extraction LangGraph workflow.

        The graph: extract → persist → compute_streak → conditional notify.
        Visible in LangSmith Studio as the `log_extraction` graph."""
        graph = self._get_log_extraction_graph()
        try:
            await graph.ainvoke(
                {
                    "log_id": log_id,
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "content": content,
                }
            )
        except Exception:
            logger.warning("log_extraction_graph_failed", exc_info=True)
        # Embedding happens here, after the ack, so /log stays fast.
        embeddings = getattr(self, "embeddings", None)
        if embeddings is None:
            return
        embedding = await embeddings.embed(content)
        if embedding is not None:
            try:
                await self.repository.set_log_embedding(log_id, embedding)
                await self.session.commit()
            except Exception:
                logger.warning("log_embedding_failed", exc_info=True)

    async def _add_memory(
        self,
        user_id: UUID,
        memory_type: str,
        title: str,
        content: str,
        evidence_refs: list[str],
    ):
        """add_memory with a best-effort embedding for semantic search."""
        embeddings = getattr(self, "embeddings", None)
        embedding = await embeddings.embed(content) if embeddings else None
        kwargs = {"embedding": embedding} if embedding is not None else {}
        return await self.repository.add_memory(
            user_id,
            memory_type,
            title,
            content,
            evidence_refs,
            **kwargs,
        )

    async def _is_rate_limited(self, user_id: UUID) -> bool:
        limit = self.settings.chat_rate_limit_per_hour
        if limit <= 0:
            return False
        since = datetime.now(UTC) - timedelta(hours=1)
        try:
            count = await self.repository.inbound_count_since(user_id, since)
        except Exception:
            logger.warning("rate_limit_query_failed", exc_info=True)
            return False
        return count > limit

    async def _current_streak(self, user_id: UUID) -> int:
        tz = ZoneInfo(self.settings.user_timezone)
        today = datetime.now(tz).date()
        timestamps = await self.repository.log_dates(user_id, days=60)
        log_days = {ts.astimezone(tz).date() for ts in timestamps}
        streak = 0
        cursor = today
        while cursor in log_days:
            streak += 1
            cursor -= timedelta(days=1)
        return streak

    async def _extract_log_fields(self, content: str) -> dict:
        try:
            result = await self.models.generate(
                system_prompt=MENTOR_SYSTEM_PROMPT,
                user_prompt=LOG_EXTRACTION_PROMPT.format(
                    log_content=self._wrap_user_text(content)
                ),
                fallback="",
                json_mode=True,
            )
        except Exception:
            return {"extraction_status": "failed"}
        raw = (result.content or "").strip()
        if not raw:
            return {"extraction_status": "failed"}
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {"extraction_status": "failed"}
        try:
            data = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return {"extraction_status": "failed"}
        allowed_difficulty = {"easy", "medium", "hard"}
        difficulty = str(data.get("difficulty", "medium")).lower().strip()
        if difficulty not in allowed_difficulty:
            difficulty = "medium"
        topic = str(data.get("topic", "")).lower().strip()[:120] or None
        return {
            "built": str(data.get("built", "")).strip() or None,
            "topic": topic,
            "difficulty": difficulty,
            "tradeoff": str(data.get("tradeoff", "")).strip() or None,
            "interview_story": str(data.get("interview_story", "")).strip() or None,
            "extraction_status": "ok",
            "topics": [topic] if topic else [],
        }

    async def _show_goals(
        self, user_id: UUID
    ) -> tuple[str, list[InlineAction] | None]:
        local_day = datetime.now(ZoneInfo(self.settings.user_timezone)).date()
        today = await self.repository.goals_for_date(user_id, local_day)
        recent = await self.repository.recent_goals(user_id, limit=20)
        lines: list[str] = ["**My Goals**"]
        actions: list[InlineAction] = []
        if today:
            lines.append(f"Today ({local_day.isoformat()}):")
            for index, goal in enumerate(today, start=1):
                lines.append(
                    f"{index}. [{goal.status}] {goal.content}"
                )
                # 6 buttons max keeps the keyboard manageable on mobile;
                # extra goals stay listed but lose their inline action row.
                if len(actions) < 6 and goal.status != "completed":
                    actions.append(
                        InlineAction(f"Done #{index}", f"goal:done:{goal.id}")
                    )
                if len(actions) < 6:
                    actions.append(
                        InlineAction(
                            f"Delete #{index}", f"goal:delete:{goal.id}"
                        )
                    )
        else:
            lines.append(f"Today ({local_day.isoformat()}): not set")
        # Group prior days' goals by date for a readable history view.
        previous: dict[str, list] = {}
        for goal in recent:
            if goal.goal_date == local_day:
                continue
            previous.setdefault(goal.goal_date.isoformat(), []).append(goal)
        if previous:
            lines.append("")
            lines.append("Previous days:")
            for day_iso in sorted(previous, reverse=True)[:5]:
                for goal in previous[day_iso]:
                    lines.append(
                        f"- {day_iso} [{goal.status}] {goal.content}"
                    )
        lines.append("")
        lines.append("Send `/goals <text>` to add a goal (one per line).")
        if today:
            actions.append(InlineAction("Clear All Today", "goal:clear"))
        actions.append(InlineAction("Next Plan", "plan:show"))
        return "\n".join(lines), actions

    async def _show_logs(
        self, user_id: UUID
    ) -> tuple[str, list[InlineAction] | None]:
        logs = await self.repository.recent_logs_limited(user_id, limit=5)
        if not logs:
            return (
                "No logs yet. Use /log to save what you built or learned.",
                None,
            )
        lines = ["**Recent Logs**"]
        actions: list[InlineAction] = []
        for index, log in enumerate(logs, start=1):
            created = log.created_at.astimezone(ZoneInfo(self.settings.user_timezone))
            tags = []
            if log.topic:
                tags.append(log.topic)
            if log.difficulty:
                tags.append(log.difficulty)
            tag_part = f" [{' · '.join(tags)}]" if tags else ""
            lines.append(
                f"{index}. {created.strftime('%d %b %H:%M')}{tag_part} - {log.content}"
            )
            actions.append(InlineAction(f"Edit #{index}", f"log:edit:{log.id}"))
            actions.append(InlineAction(f"Delete #{index}", f"log:delete:{log.id}"))
        return "\n".join(lines), actions

    async def _delete_log_by_id(self, user_id: UUID, log_id: str) -> str:
        try:
            removed = await self.repository.delete_learning_log(
                user_id, UUID(log_id)
            )
        except ValueError:
            return "That log id is invalid."
        if not removed:
            return "I could not find that log to delete."
        return "Log deleted. Use /logs to see the rest."

    async def _begin_log_edit(self, user_id: UUID, log_id: str) -> str:
        try:
            log = await self.repository.get_learning_log(user_id, UUID(log_id))
        except ValueError:
            return "That log id is invalid."
        if log is None:
            return "I could not find that log."
        await self.repository.upsert_interaction_state(
            user_id,
            "log_waiting_edit",
            {"log_id": str(log.id), "previous": log.content},
        )
        return (
            "Send the corrected log text as your next message. I will replace the "
            "old content and re-extract the topic and story.\n\n"
            f"_Current:_ {log.content}"
        )

    async def _apply_log_edit(
        self, user_id: UUID, state_data: dict[str, Any], text: str
    ) -> str:
        await self.repository.clear_interaction_state(user_id)
        log_id_raw = state_data.get("log_id")
        if not log_id_raw:
            return "I lost track of which log to edit. Open /logs and try again."
        try:
            log_id = UUID(str(log_id_raw))
        except ValueError:
            return "That log id is invalid."
        content = text.strip()
        if not content:
            return "Empty edit ignored. Open /logs and try again."
        await self.repository.update_log_fields(log_id, {"content": content})
        fields = await self._extract_log_fields(content)
        if fields:
            await self.repository.update_log_fields(log_id, fields)
        topic_note = ""
        if fields and fields.get("topic"):
            topic_note = f" Topic now: {fields['topic']}."
        return f"Log updated.{topic_note}"

    ONBOARDING_QUESTIONS = [
        ("target_role", "What role are you targeting? (e.g. 'backend engineer at a startup', 'ML engineer at FAANG')"),
        ("weekly_hours", "How many hours per week can you commit to focused practice?"),
        ("weak_areas", "List 2-3 topics you feel weakest on right now."),
    ]

    async def _maybe_start_onboarding(self, user_id: UUID) -> str | None:
        existing = await self.repository.recent_memories_by_type(
            user_id, "profile", days=365
        )
        if existing:
            return None
        await self.repository.upsert_interaction_state(
            user_id, "onboarding", {"step": 0, "answers": {}}
        )
        first_question = self.ONBOARDING_QUESTIONS[0][1]
        return (
            "**Welcome to PathwayAI**\n"
            "Before we start, three quick questions so I can tailor coaching to you.\n\n"
            f"1/3 — {first_question}"
        )

    async def _restart_onboarding(self, user_id: UUID) -> str:
        await self.repository.upsert_interaction_state(
            user_id, "onboarding", {"step": 0, "answers": {}}
        )
        first_question = self.ONBOARDING_QUESTIONS[0][1]
        return (
            "**Welcome back to onboarding**\n"
            "Let's start over from the first question.\n\n"
            f"1/3 — {first_question}"
        )

    async def _continue_onboarding(
        self, user_id: UUID, state_data: dict[str, Any], text: str
    ) -> tuple[str, bool]:
        """Returns (reply, completed)."""
        step = int(state_data.get("step", 0))
        answers = dict(state_data.get("answers") or {})
        if step >= len(self.ONBOARDING_QUESTIONS):
            await self.repository.clear_interaction_state(user_id)
            return self._help_text(), True
        key, _ = self.ONBOARDING_QUESTIONS[step]
        answers[key] = text.strip()
        next_step = step + 1
        if next_step < len(self.ONBOARDING_QUESTIONS):
            await self.repository.upsert_interaction_state(
                user_id,
                "onboarding",
                {"step": next_step, "answers": answers},
            )
            _, question = self.ONBOARDING_QUESTIONS[next_step]
            return (
                f"{next_step + 1}/{len(self.ONBOARDING_QUESTIONS)} — {question}",
                False,
            )
        await self.repository.clear_interaction_state(user_id)
        profile_lines = "\n".join(f"- {k}: {v}" for k, v in answers.items())
        await self._add_memory(
            user_id,
            "profile",
            "User profile",
            profile_lines,
            [],
        )
        return (
            "**You are set up.** I will use this profile to tailor goals, quizzes "
            "and weekly reviews. Start with `/goals <today's goals>` or just chat.\n\n"
            f"Profile saved:\n{profile_lines}",
            True,
        )

    async def _show_activity(self, user_id: UUID) -> str:
        events = await self.repository.recent_events(user_id, days=7)
        if not events:
            return (
                "No activity events in the last 7 days. Once GitHub and LeetCode "
                "syncs land, your commits and solved problems will show up here."
            )
        by_source: dict[str, Counter] = {}
        for event in events:
            by_source.setdefault(event.source, Counter())[event.event_type] += 1
        lines = ["**Activity (last 7 days)**"]
        for source in sorted(by_source.keys()):
            counts = by_source[source]
            total = sum(counts.values())
            breakdown = ", ".join(
                f"{event_type} ({count})" for event_type, count in counts.most_common()
            )
            lines.append(f"_{source}_ — {total}: {breakdown}")
        lines.append("")
        lines.append("Recent items:")
        for event in events[:10]:
            local_dt = event.occurred_at.astimezone(
                ZoneInfo(self.settings.user_timezone)
            )
            ref = event.payload.get("title") or event.external_ref
            lines.append(
                f"- {local_dt.strftime('%d %b %H:%M')} {event.source}:{event.event_type} — {ref}"
            )
        logged_topics = {
            (log.topic or "").lower()
            for log in await self.repository.recent_logs(user_id, days=7)
            if log.topic
        }
        unlogged_sources = sorted(
            {event.source for event in events if event.source not in logged_topics}
        )
        if unlogged_sources:
            lines.append("")
            lines.append(
                "Heads-up: activity from "
                + ", ".join(unlogged_sources)
                + " has no matching /log entry yet."
            )
        return "\n".join(lines)

    async def _forget_me(self, user_id: UUID, argument: str) -> str:
        if argument.strip().lower() != "confirm":
            return (
                "This will permanently clear your stored memory, logs, goals, "
                "conversation history, onboarding state, and progress tracking.\n\n"
                "If you want to continue, send:\n"
                "`/forgetme confirm`"
            )
        await self.repository.reset_user_data(user_id)
        return (
            "**Your PathwayAI memory has been cleared.**\n"
            "You are starting fresh. Send `/start` to begin onboarding again."
        )

    async def _show_mastery(
        self, user_id: UUID
    ) -> tuple[str, list[InlineAction] | None]:
        rows = await self.repository.all_topic_mastery(user_id)
        if not rows:
            return (
                "No topic mastery recorded yet. Finish a quiz or /mock interview "
                "and I will start tracking levels per topic."
            ), None
        lines = ["**Topic Mastery**"]
        actions: list[InlineAction] = []
        now = datetime.now(UTC)
        for row in rows[:20]:
            due_marker = ""
            is_due = False
            if row.next_due_at is not None:
                due_in = (row.next_due_at - now).days
                if due_in <= 0:
                    due_marker = " (due now)"
                    is_due = True
                else:
                    due_marker = f" (due in {due_in}d)"
            quizzed = (
                row.last_quizzed_at.astimezone(
                    ZoneInfo(self.settings.user_timezone)
                ).strftime("%d %b")
                if row.last_quizzed_at
                else "never"
            )
            lines.append(
                f"- {row.topic}: {row.level} ×{row.quiz_count}, "
                f"last {quizzed}{due_marker}"
            )
            if is_due and len(actions) < 6:
                actions.append(
                    InlineAction(
                        f"Quiz: {row.topic[:18]}", f"quiz_topic:{row.topic}"
                    )
                )
        return "\n".join(lines), (actions or None)

    async def _start_review(self, user_id: UUID) -> str:
        existing = await self.repository.get_interaction_state(user_id)
        if existing is not None:
            return (
                "Finish your current quiz or mock interview first, then run "
                "/review again."
            )
        due = await self.repository.due_topics(user_id, limit=3)
        if not due:
            return (
                "Nothing is due for re-quiz yet. Keep logging and quizzing — "
                "topics resurface here on a spaced-repetition schedule."
            )
        for row in due:
            log = await self.repository.latest_log_for_topic(user_id, row.topic)
            if log is not None:
                return await self._start_quiz(user_id, str(log.id))
        return (
            "Topics are due, but I cannot find a log to quiz from. Add a /log "
            "for one of: " + ", ".join(row.topic for row in due)
        )

    async def _export_bundle(
        self, user_id: UUID, argument: str, chat_id: str
    ) -> str:
        scope = (argument.strip().lower() or "week")
        filename, markdown = await self.build_export_markdown(user_id, scope)
        try:
            await self.telegram.send_document(
                chat_id=chat_id,
                filename=filename,
                content=markdown.encode("utf-8"),
                caption=f"PathwayAI export — {scope}",
            )
        except Exception:
            logger.warning("export_send_failed", exc_info=True)
            return "Export generation failed. Try again in a moment."
        return f"Sent {filename}. Use `/export month` for the past 30 days."

    async def build_export_markdown(
        self, user_id: UUID, scope: str = "week"
    ) -> tuple[str, str]:
        """Render the export bundle; shared by /export and the digest email."""
        days = 7 if scope == "week" else 30 if scope == "month" else 7
        tz = ZoneInfo(self.settings.user_timezone)
        local_today = datetime.now(tz).date()
        start = local_today - timedelta(days=days - 1)
        logs = await self.repository.recent_logs(user_id, days=days)
        goals = await self.repository.goals_in_range(user_id, start, local_today)
        mastery = await self.repository.all_topic_mastery(user_id)
        score = await self.repository.latest_score(user_id)
        plan = await self.repository.latest_weekly_plan(user_id)
        memories = await self.repository.recent_memories(user_id, days=days)

        lines: list[str] = [
            f"# PathwayAI Export ({scope}) — {start.isoformat()} to {local_today.isoformat()}",
            "",
            "## Goals",
        ]
        if goals:
            for goal in goals:
                lines.append(
                    f"- **{goal.goal_date.isoformat()}** [{goal.status}] {goal.content}"
                )
        else:
            lines.append("_No goals set._")

        lines.extend(["", "## Logs"])
        if logs:
            for log in logs:
                date_str = log.created_at.astimezone(tz).strftime("%Y-%m-%d %H:%M")
                tag = []
                if log.topic:
                    tag.append(log.topic)
                if log.difficulty:
                    tag.append(log.difficulty)
                tag_str = f" `{' · '.join(tag)}`" if tag else ""
                lines.append(f"- **{date_str}**{tag_str} — {log.content}")
                if log.interview_story:
                    lines.append(f"  - _Interview story:_ {log.interview_story}")
        else:
            lines.append("_No logs in window._")

        lines.extend(["", "## Topic Mastery"])
        if mastery:
            for row in mastery[:25]:
                lines.append(
                    f"- {row.topic}: {row.level} (quizzes ×{row.quiz_count})"
                )
        else:
            lines.append("_No mastery tracked yet._")

        lines.extend(["", "## Readiness Score"])
        if score is not None:
            lines.append(
                f"- Overall: {score.overall_score:.1f}% (confidence "
                f"{score.confidence:.0%}, model {score.score_version})"
            )
            for axis, value in (score.subscores or {}).items():
                lines.append(f"  - {axis}: {value}")
            gaps = (score.gap_analysis or {}).get("missing_evidence_or_gaps", [])
            if gaps:
                lines.append(f"- Gaps: {', '.join(gaps[:5])}")
        else:
            lines.append("_No readiness score yet._")

        lines.extend(["", "## Weekly Plan"])
        if plan is not None:
            lines.append(plan.content)
        else:
            lines.append("_No weekly plan yet._")

        lines.extend(["", "## Highlights from Memory"])
        if memories:
            for memory in memories[:10]:
                lines.append(f"- **{memory.title}** — {memory.content}")
        else:
            lines.append("_No memory entries in window._")

        filename = f"pathwayai-{scope}-{local_today.isoformat()}.md"
        return filename, "\n".join(lines)

    async def _code_review(
        self, user_id: UUID, argument: str
    ) -> tuple[str, list[InlineAction] | None, UUID | None, str | None]:
        snippet = argument.strip()
        if not snippet:
            return (
                "Paste code after the command. Example:\n"
                "/codereview\n```python\ndef add(a, b):\n    return a+b\n```"
            ), None, None, None
        result = await self.models.generate(
            system_prompt=MENTOR_SYSTEM_PROMPT,
            user_prompt=CODE_REVIEW_PROMPT.format(
                code=self._wrap_user_text(snippet)
            ),
            fallback=(
                "STRENGTHS: function is short and readable\n"
                "BUGS: none obvious from this snippet alone\n"
                "COMPLEXITY: O(1) on the visible operations\n"
                "INTERVIEW_NOTES: be ready to explain edge cases and inputs"
            ),
        )
        review = result.content.strip()
        log_content = (
            f"Code review:\n{snippet}\n\n--- Review ---\n{review}"
        )
        log = await self.repository.add_learning_log(user_id, log_content)
        await self.repository.update_log_fields(
            log.id,
            {"topic": "code_review", "extraction_status": "ok"},
        )
        return (
            f"**Code Review**\n{review}\n\nLogged as a learning entry.",
            [InlineAction("Quiz Me", f"quiz_log:{log.id}")],
            None,  # Skip background extraction; we already set fields
            None,
        )

    async def _show_stories(
        self, user_id: UUID
    ) -> tuple[str, list[InlineAction] | None]:
        logs = await self.repository.logs_with_stories(user_id, limit=30)
        if not logs:
            return (
                "No interview stories yet. Log work with `/log` — I'll extract a "
                "STAR-style story for each entry, and they'll show up here."
            ), None
        by_topic: dict[str, list[tuple[str, UUID]]] = {}
        for log in logs:
            topic = (log.topic or "general").strip().lower() or "general"
            if log.interview_story:
                by_topic.setdefault(topic, []).append(
                    (log.interview_story, log.id)
                )
        lines = ["**Interview Stories**"]
        actions: list[InlineAction] = []
        quiz_added = 0
        for topic in sorted(by_topic.keys()):
            stories = by_topic[topic][:3]
            if not stories:
                continue
            lines.append(f"\n_{topic}_")
            for story, log_id in stories:
                lines.append(f"- {story}")
                if quiz_added < 6:
                    actions.append(
                        InlineAction(
                            f"Quiz: {_short_button_label(topic)}",
                            f"quiz_log:{log_id}",
                        )
                    )
                    quiz_added += 1
        return "\n".join(lines), (actions or None)

    async def _semantic_search(
        self, user_id: UUID, argument: str
    ) -> tuple[str, list[InlineAction] | None]:
        from pathwayai_backend.db.models import LearningLog

        query = argument.strip()
        if not query:
            return (
                "Tell me what to look for. Example:\n"
                "/search webhook idempotency tradeoffs"
            ), None
        embedding = await self.embeddings.embed(query)
        if embedding is not None:
            rows = [
                row
                for row, _distance in await self.repository.semantic_search(
                    user_id, embedding, limit=8
                )
            ]
            mode_note = ""
        else:
            # No embedding provider — degrade to the keyword search.
            rows = await self.repository.search_memory(user_id, query, limit=8)
            mode_note = "\n_Keyword match (semantic search unavailable)._"
        if not rows:
            return (
                f"No matches for “{query}” yet. Log more work with /log and "
                "try again."
            ), None
        tz = ZoneInfo(self.settings.user_timezone)
        lines = [f"**Search: {query}**"]
        actions: list[InlineAction] = []
        for row in rows:
            is_log = isinstance(row, LearningLog)
            date_str = row.created_at.astimezone(tz).strftime("%d %b")
            snippet = " ".join(row.content.split())
            if len(snippet) > 160:
                snippet = snippet[:159].rstrip() + "…"
            if is_log:
                label = row.topic or "log"
                lines.append(f"- 📝 {date_str} `{label}` — {snippet}")
                if len(actions) < 6:
                    actions.append(
                        InlineAction(
                            f"Quiz: {_short_button_label(label)}",
                            f"quiz_log:{row.id}",
                        )
                    )
            else:
                lines.append(f"- 🧠 {date_str} _{row.title}_ — {snippet}")
        return "\n".join(lines) + mode_note, (actions or None)

    async def _start_mock_interview(self, user_id: UUID, argument: str) -> str:
        topic = argument.strip()
        if not topic:
            due = await self.repository.due_topics(user_id, limit=3)
            mastery = await self.repository.all_topic_mastery(user_id)
            level_rank = {
                "exposure": 0, "conceptual": 1,
                "implementation": 2, "interview-ready": 3,
            }
            weakest = sorted(
                mastery, key=lambda r: level_rank.get(r.level, 1)
            )[:3]
            suggestions: list[str] = []
            seen: set[str] = set()
            for row in (*due, *weakest):
                if row.topic in seen:
                    continue
                seen.add(row.topic)
                suggestions.append(f"/mock {row.topic}")
            suggestion_block = ""
            if suggestions:
                suggestion_block = (
                    "\n\nTry one of your due / weakest topics:\n"
                    + "\n".join(suggestions[:3])
                )
            return (
                "Pick a topic. Example:\n"
                "/mock graph algorithms\n"
                "/mock postgres indexes\n"
                "Reply `/end` at any time to stop and get a rubric."
                + suggestion_block
            )
        recent_logs = await self.repository.recent_logs_limited(user_id, limit=10)
        on_topic = [
            log for log in recent_logs if (log.topic or "").lower() == topic.lower()
        ] or recent_logs[:3]
        recent_text = "\n".join(f"- {log.content}" for log in on_topic[:3]) or "None"
        result = await self.models.generate(
            system_prompt=MENTOR_SYSTEM_PROMPT,
            user_prompt=MOCK_INTERVIEW_OPENER_PROMPT.format(
                topic=topic, recent_logs=recent_text
            ),
            fallback=(
                f"Walk me through how you would approach a real problem in {topic}. "
                "Start with how you would structure the solution end-to-end."
            ),
        )
        question = result.content.strip()
        await self.repository.upsert_interaction_state(
            user_id,
            "mock_interview",
            {
                "topic": topic,
                "turn": 1,
                "transcript": [{"role": "interviewer", "content": question}],
            },
        )
        return f"**Mock Interview: {topic}**\n{question}\n\n_Reply `/end` to stop early._"

    async def _handle_mock_answer(
        self, user_id: UUID, state_data: dict[str, Any], answer: str
    ) -> tuple[str, bool]:
        """Thin invoker for the `mock_interview_turn` LangGraph workflow.

        record_user_turn → decide (continue vs finish based on turn count)
        → probe or finalize_interview. Visible in LangSmith Studio."""
        graph = self._get_mock_graph()
        result = await graph.ainvoke(
            {"user_id": user_id, "state_data": state_data, "answer": answer}
        )
        return result["reply"], bool(result.get("finished", False))

    async def _finish_mock_interview(
        self,
        user_id: UUID,
        state_data: dict[str, Any],
        ended_early: bool = False,
    ) -> str:
        topic = str(state_data.get("topic", "general"))
        transcript = list(state_data.get("transcript") or [])
        if not any(msg["role"] == "candidate" for msg in transcript):
            await self.repository.clear_interaction_state(user_id)
            return "Mock interview ended before you answered anything. Start again with `/mock <topic>`."
        transcript_text = "\n".join(
            f"{'Interviewer' if msg['role'] == 'interviewer' else 'Candidate'}: {msg['content']}"
            for msg in transcript
        )
        result = await self.models.generate(
            system_prompt=MENTOR_SYSTEM_PROMPT,
            user_prompt=MOCK_INTERVIEW_FINAL_PROMPT.format(
                topic=topic, transcript=transcript_text
            ),
            fallback=(
                "LEVEL: conceptual\n"
                "STRENGTHS: You engaged with the question and produced a structured answer.\n"
                "GAPS: Push for more concrete implementation detail and named tradeoffs.\n"
                "NEXT: Re-do this topic with a written outline before answering."
            ),
        )
        rubric = result.content.strip()
        await self.repository.clear_interaction_state(user_id)
        local_day = datetime.now(ZoneInfo(self.settings.user_timezone)).date()
        await self._add_memory(
            user_id,
            "mock_interview",
            f"Mock interview {topic} {local_day.isoformat()}",
            f"Topic: {topic}\nEnded early: {ended_early}\n\n{rubric}\n\nTranscript:\n{transcript_text}",
            [],
        )
        level = self._parse_level_line(rubric) or "conceptual"
        mastery = await self._record_mastery(user_id, topic.lower(), level)
        prefix = "**Mock Interview Ended Early**" if ended_early else "**Mock Interview Complete**"
        mastery_line = (
            f"\n_Topic mastery: {topic.lower()} → {mastery.level}. "
            f"Next re-quiz due {mastery.next_due_at.date().isoformat()}._"
        )
        return f"{prefix}\n{rubric}{mastery_line}"

    @staticmethod
    def _split_command(text: str) -> tuple[str, str]:
        """Split a leading /command from its argument, allowing any whitespace
        (including newlines) as the separator so multi-line bodies work."""
        import re

        match = re.match(r"\s*(/\S+)(?:\s+(.*))?$", text, re.DOTALL)
        if not match:
            return text.lower(), ""
        command = match.group(1).split("@", 1)[0].lower()
        argument = (match.group(2) or "").strip()
        return command, argument

    @staticmethod
    def _wrap_user_text(text: str) -> str:
        cleaned = (text or "").replace("</USER_INPUT>", "</USER_INPUT_>")
        return f"<USER_INPUT>{cleaned}</USER_INPUT>"

    @staticmethod
    def _parse_level_line(rubric: str) -> str | None:
        for line in rubric.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("LEVEL:"):
                level = stripped.split(":", 1)[1].strip().lower()
                if level in {
                    "exposure", "conceptual", "implementation", "interview-ready"
                }:
                    return level
        return None

    async def _status(self, user_id) -> str:
        tz = ZoneInfo(self.settings.user_timezone)
        local_today = datetime.now(tz).date()
        week_start = local_today - timedelta(days=6)
        log_timestamps = await self.repository.log_dates(user_id, days=60)
        log_days = {ts.astimezone(tz).date() for ts in log_timestamps}
        streak = 0
        cursor = local_today
        while cursor in log_days:
            streak += 1
            cursor -= timedelta(days=1)
        heatmap_cells = []
        for offset in range(6, -1, -1):
            day = local_today - timedelta(days=offset)
            heatmap_cells.append("X" if day in log_days else ".")
        heatmap = "".join(heatmap_cells)

        goals = await self.repository.goals_in_range(
            user_id, week_start, local_today
        )
        completed = sum(1 for goal in goals if goal.status == "completed")
        partial = sum(1 for goal in goals if goal.status == "partial")
        skipped = sum(1 for goal in goals if goal.status == "skipped")
        goal_line = (
            f"Last 7 days goals: {completed} completed, {partial} partial, "
            f"{skipped} skipped, {len(goals)} set."
        )
        streak_line = f"Log streak: {streak} day(s). Last 7 days: {heatmap}"

        score = await self.repository.latest_score(user_id)
        if score is None:
            return (
                f"{streak_line}\n{goal_line}\n"
                "No readiness score exists yet. The first weekly review will create it."
            )
        missing = score.gap_analysis.get("missing_evidence_or_gaps", [])
        subscore_lines = [
            f"  - {axis}: {value}" for axis, value in (score.subscores or {}).items()
        ]
        subscores_text = "\n".join(subscore_lines) or "  - none recorded"
        return (
            f"{streak_line}\n{goal_line}\n"
            f"Readiness estimate: {score.overall_score:.1f}% "
            f"(confidence {score.confidence:.0%}, model {score.score_version}).\n"
            f"Subscores:\n{subscores_text}\n"
            f"Top gaps: {', '.join(missing[:3]) or 'none recorded'}."
        )

    async def _next_plan(self, user_id) -> str:
        plan = await self.repository.latest_weekly_plan(user_id)
        return plan.content if plan else "No weekly plan exists yet."

    async def _answer_question(self, user_id, argument: str) -> str:
        if not argument.strip():
            return (
                "Ask me any technical question. Example:\n"
                "/ask Explain cursor pagination vs offset pagination and when each breaks down."
            )
        recent_logs = await self.repository.recent_logs_limited(user_id, limit=5)
        local_day = datetime.now(ZoneInfo(self.settings.user_timezone)).date()
        goals = await self.repository.goals_for_date(user_id, local_day)

        if self._is_quiz_request(argument):
            if recent_logs:
                return await self._start_quiz(user_id, str(recent_logs[0].id))
            return (
                "I do not see any recent logs yet. First use /log to save what you completed, "
                "then ask me to quiz you on it."
            )

        if self._is_recent_progress_question(argument):
            if recent_logs:
                latest = recent_logs[0]
                created = latest.created_at.astimezone(
                    ZoneInfo(self.settings.user_timezone)
                )
                return (
                    f"The most recent thing you logged was at {created.strftime('%d %b %H:%M')}: "
                    f"{latest.content}\n\n"
                    "Interview check question:\n"
                    f"What was the key technical idea or tradeoff in that work?"
                )
            return (
                "I do not see any recent logs yet. Use /log right after you complete something, "
                "then I can tell you what you most recently worked on."
            )

        memories = await self.repository.search_memory(user_id, argument)
        memory_text = "\n".join(item.content for item in memories) or "None"
        recent_logs_text = "\n".join(
            f"- {log.content}" for log in recent_logs
        ) or "None"
        result = await self.models.generate(
            system_prompt=MENTOR_SYSTEM_PROMPT,
            user_prompt=TUTOR_QUESTION_PROMPT.format(
                question=self._wrap_user_text(argument),
                goal=(
                    "\n".join(f"- {g.content}" for g in goals)
                    if goals
                    else "No goal declared today"
                ),
                recent_logs=recent_logs_text,
                memory=memory_text,
            ),
            fallback=(
                "The model providers are unavailable right now. Record the question "
                "with `/log` and retry when Groq or Hugging Face is configured."
            ),
        )
        return result.content

    async def _start_quiz(self, user_id: UUID, log_id: str) -> str:
        existing = await self.repository.get_interaction_state(user_id)
        if existing is not None and existing.state_type == "quiz_waiting_answer":
            current = existing.state_data or {}
            questions = list(current.get("questions") or [])
            index = int(current.get("current_index", 0))
            if questions and index < len(questions):
                return (
                    "You already have a quiz in progress. Answer the current "
                    f"question first:\n{questions[index]}"
                )
        log = await self.repository.get_learning_log(user_id, UUID(log_id))
        if log is None:
            return "I could not find that log anymore. Try logging it again and then tap Quiz Me."
        result = await self.models.generate(
            system_prompt=MENTOR_SYSTEM_PROMPT,
            user_prompt=LOG_QUIZ_PROMPT.format(
                log_content=log.content,
                topic=log.topic or "unknown",
                built=log.built or "see raw log",
                difficulty=log.difficulty or "medium",
                tradeoff=log.tradeoff or "not extracted",
            ),
            fallback=(
                "Q1: Explain the core idea behind what you just logged.\n"
                "Q2: How would you implement or debug it in code?\n"
                "Q3: What tradeoff or failure mode matters most here?"
            ),
        )
        questions = self._parse_quiz_questions(result.content)
        await self.repository.upsert_interaction_state(
            user_id,
            "quiz_waiting_answer",
            {
                "log_id": str(log.id),
                "log_content": log.content,
                "questions": questions,
                "current_index": 0,
                "answers": [],
                "levels": [],
            },
        )
        return f"**Quiz Time**\n{questions[0]}"

    @staticmethod
    def _is_idk_answer(answer: str) -> bool:
        """True when the user clearly didn't attempt the question — teach
        instead of grade. Covers explicit 'I don't know' phrasing plus very
        short non-attempts (e.g. '?', 'no', 'pass')."""
        normalized = answer.strip().lower()
        if not normalized:
            return True
        idk_phrases = {
            "idk",
            "i dont know",
            "i don't know",
            "dont know",
            "don't know",
            "no idea",
            "not sure",
            "skip",
            "pass",
            "next",
            "teach me",
            "tell me",
            "?",
        }
        if normalized in idk_phrases:
            return True
        # Very short non-attempts ("no", "nope", "n/a") that aren't real answers.
        short_skips = {"no", "nope", "n/a", "na", "??", "???"}
        if normalized in short_skips:
            return True
        return False

    @staticmethod
    def _parse_quiz_teach(raw: str) -> dict[str, str]:
        teach = ""
        nxt = ""
        for line in (raw or "").splitlines():
            stripped = line.strip()
            upper = stripped.upper()
            if upper.startswith("TEACH:"):
                teach = stripped[len("TEACH:") :].strip()
            elif upper.startswith("NEXT:"):
                nxt = stripped[len("NEXT:") :].strip()
        if not teach:
            teach = (
                "No worries — here's the short version: re-read your log and "
                "focus on the one tradeoff or failure mode you'd defend in an "
                "interview."
            )
        if not nxt:
            nxt = "Try this question again after one more pass on the log."
        return {"teach": teach, "next": nxt}

    async def _handle_quiz_answer(
        self, user_id: UUID, state_data: dict[str, Any], answer: str
    ) -> str:
        """Thin invoker for the `quiz_answer` LangGraph workflow.

        The graph routes to grade vs teach based on `_is_idk_answer`,
        records the turn, and conditionally presents the next question
        or finalizes the quiz with a mastery update. Visible in
        LangSmith Studio as the `quiz_answer` graph."""
        graph = self._get_quiz_graph()
        result = await graph.ainvoke(
            {"user_id": user_id, "state_data": state_data, "answer": answer}
        )
        return result["reply"]

    async def _resolve_quiz_topic(
        self, user_id: UUID, state_data: dict[str, Any], log_content: str
    ) -> str | None:
        log_id_raw = state_data.get("log_id")
        if log_id_raw:
            try:
                log = await self.repository.get_learning_log(
                    user_id, UUID(str(log_id_raw))
                )
            except (ValueError, AttributeError):
                log = None
            if log and log.topic:
                return log.topic
        return None

    async def _record_mastery(
        self, user_id: UUID, topic: str, level: str
    ) -> Any:
        days = self.SPACED_REPETITION_DAYS.get(level, 3)
        next_due = datetime.now(UTC) + timedelta(days=days)
        return await self.repository.upsert_topic_mastery(
            user_id=user_id,
            topic=topic,
            level=level,
            next_due_at=next_due,
        )

    CONVERSATION_COMPACT_THRESHOLD = 40
    CONVERSATION_COMPACT_BATCH = 30

    async def _maybe_compact_conversation(self, user_id: UUID) -> None:
        try:
            total = await self.repository.conversation_message_count(user_id)
        except Exception:
            logger.warning("compact_count_failed", exc_info=True)
            return
        if total < self.CONVERSATION_COMPACT_THRESHOLD:
            return
        oldest = await self.repository.oldest_conversation_messages(
            user_id, limit=self.CONVERSATION_COMPACT_BATCH
        )
        if len(oldest) < self.CONVERSATION_COMPACT_BATCH:
            return
        transcript = "\n".join(
            f"{'User' if msg.direction == 'inbound' else 'Mentor'}: "
            f"{self._wrap_user_text(msg.content) if msg.direction == 'inbound' else msg.content}"
            for msg in oldest
        )
        try:
            result = await self.models.generate(
                system_prompt=MENTOR_SYSTEM_PROMPT,
                user_prompt=CHAT_SUMMARY_PROMPT.format(transcript=transcript),
                fallback="",
            )
        except Exception:
            logger.warning("compact_llm_failed", exc_info=True)
            return
        summary = (result.content or "").strip()
        if not summary:
            return
        local_today = datetime.now(ZoneInfo(self.settings.user_timezone)).date()
        await self._add_memory(
            user_id,
            "chat_summary",
            f"Chat summary {local_today.isoformat()}",
            summary,
            [],
        )
        await self.repository.delete_conversation_messages(
            user_id, [msg.id for msg in oldest]
        )

    async def _chat(self, user_id, text: str) -> str:
        """Thin invoker for the `chat` LangGraph workflow.

        maybe_compact → load_context → maybe_remember_instruction → llm_reply.
        Visible in LangSmith Studio as the `chat` graph."""
        graph = self._get_chat_graph()
        result = await graph.ainvoke({"user_id": user_id, "text": text})
        return result["reply"]

    @staticmethod
    def _looks_like_instruction(text: str) -> bool:
        normalized = text.lower()
        triggers = (
            "won't study", "wont study", "won't be able to study",
            "wont be able to study", "can't study", "cant study",
            "no study today", "skip today", "skipping today",
            "not studying", "off today", "taking a break",
            "i am busy", "i'm busy", "im busy", "travel", "travelling",
            "sick", "unwell", "rest day",
            "focus on", "want to focus", "let's focus", "lets focus",
            "from now on", "going forward", "please remember",
            "remember that", "note that",
        )
        return any(trigger in normalized for trigger in triggers)

    @staticmethod
    def _help_text(full: bool = False) -> str:
        core = (
            "**PathwayAI — Core Commands**\n"
            "/goals <text> · /goals - set or view today's goal\n"
            "/log <what you built or learned>\n"
            "/ask <technical question>\n"
            "/status - streak, goal stats, readiness\n"
            "/mock <topic> - run a mock interview\n"
            "/review - re-quiz a due topic\n"
            "/help all - full command list\n\n"
            "Free-text replies become a real conversation — I remember.\n"
            "First run? Send /start for a quick 3-question intake."
        )
        if not full:
            return core
        return (
            "**How To Use PathwayAI**\n"
            "Use the slash-command menu (≡) next to the message box, or type:\n"
            "/goals <text> - set or update today's goal\n"
            "/goals dsa | systems | review | project - apply a template\n"
            "/goals - view and manage today's plus recent goals\n"
            "/log <what you learned or built>\n"
            "  e.g. /log fixed N+1 query in feed loader\n"
            "  e.g. /log built JWT auth middleware; tradeoff: stateless vs revocation\n"
            "/ask <technical question>\n"
            "/logs - recent learning logs (Edit / Delete inline)\n"
            "/activity - GitHub / LeetCode activity in the last 7 days\n"
            "/mastery - per-topic level and re-quiz due dates\n"
            "/review - re-quiz the next topic due for spaced repetition\n"
            "/stories - interview stories grouped by topic\n"
            "/search <query> - semantic search across logs and memory\n"
            "/mock <topic> - start a multi-turn mock interview (`/end` to stop)\n"
            "/codereview <code> - structured review and log it\n"
            "/export week|month - markdown export bundle\n"
            "/status - streak, goal stats, and readiness score\n"
            "/next - latest weekly plan\n"
            "/version - running build\n"
            "/forgetme confirm - wipe stored memory and start fresh\n\n"
            "After you log work, tap Quiz Me to test your understanding.\n"
            "You can also just chat freely — I remember the conversation.\n"
            "First run? Send /start for a quick 3-question intake."
        )

    @staticmethod
    def _parse_quiz_questions(content: str) -> list[str]:
        questions: list[str] = []
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("Q1:") or stripped.startswith("Q2:") or stripped.startswith("Q3:"):
                questions.append(stripped.split(":", 1)[1].strip())
        return questions[:3] or [
            "Explain the core idea behind what you just logged.",
            "How would you implement or debug it in practice?",
            "What tradeoff or failure mode matters most here?",
        ]

    @staticmethod
    def _parse_quiz_evaluation(content: str) -> dict[str, str]:
        result = {
            "level": "conceptual",
            "feedback": "You showed some understanding, but you need more specific implementation detail.",
            "next": "Explain one concrete example from your own work.",
        }
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("LEVEL:"):
                result["level"] = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("FEEDBACK:"):
                result["feedback"] = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("NEXT:"):
                result["next"] = stripped.split(":", 1)[1].strip()
        return result

    @staticmethod
    def _summarize_level(levels: list[str]) -> str:
        ranking = {
            "exposure": 0,
            "conceptual": 1,
            "implementation": 2,
            "interview-ready": 3,
        }
        if not levels:
            return "conceptual"
        average = sum(ranking.get(level, 1) for level in levels) / len(levels)
        if average >= 2.5:
            return "interview-ready"
        if average >= 1.5:
            return "implementation"
        if average >= 0.5:
            return "conceptual"
        return "exposure"

    @staticmethod
    def _is_recent_progress_question(question: str) -> bool:
        normalized = question.lower()
        triggers = (
            "what topic i just completed",
            "what did i just complete",
            "what did i just finish",
            "what did i recently complete",
            "what did i recently finish",
            "what did i just log",
            "what was my latest log",
            "what did i last study",
            "what topic did i just finish",
        )
        return any(trigger in normalized for trigger in triggers)

    @staticmethod
    def _is_quiz_request(question: str) -> bool:
        normalized = question.lower()
        triggers = (
            "ask me few questions",
            "ask me a few questions",
            "quiz me",
            "test me",
            "ask questions based on my log",
            "based on my log",
            "from my log",
            "on my recent log",
            "ask me questions on this",
        )
        return any(trigger in normalized for trigger in triggers)
