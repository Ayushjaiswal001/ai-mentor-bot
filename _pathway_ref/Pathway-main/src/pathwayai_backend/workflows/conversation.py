"""LangGraph workflows for the four conversational sub-flows.

Each flow is built on the TelegramUpdateService instance so node
functions can reuse the service's repository, model gateway, telegram
client, and prompt-wrapping helpers without circular imports.

  quiz_answer
    START → branch_mode (idk? → teach | grade → evaluate)
          → record_turn → has_next?
          (yes → present_next_question | no → finalize) → END

  mock_interview_turn
    START → record_user_turn → decide
          (continue → probe | finish → finalize_interview) → END

  chat
    START → maybe_compact → load_context → maybe_remember_instruction
          → llm_reply → END

  log_extraction
    START → extract → persist → notify? (streak ≥ 2 OR topic? → notify | END)

The graphs return a plain dict; the calling service method extracts the
user-facing reply and any flags it needs.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, TypedDict
from uuid import UUID
from zoneinfo import ZoneInfo

from langgraph.graph import END, START, StateGraph


# ---------------------------------------------------------------------
# State types
# ---------------------------------------------------------------------


class QuizState(TypedDict, total=False):
    user_id: UUID
    state_data: dict[str, Any]
    answer: str
    question: str
    current_index: int
    questions: list
    log_content: str
    mode: str  # "teach" | "grade"
    feedback: str
    next_action: str
    level: str
    reply: str
    finished: bool


class MockState(TypedDict, total=False):
    user_id: UUID
    state_data: dict[str, Any]
    answer: str
    reply: str
    finished: bool


class ChatState(TypedDict, total=False):
    user_id: UUID
    text: str
    goals: list
    recent_logs: list
    memories: list
    history: list
    reply: str


class LogExtractionState(TypedDict, total=False):
    log_id: UUID
    user_id: UUID
    chat_id: str
    content: str
    fields: dict[str, Any]
    streak: int
    notify_text: str
    critic_verdict: str  # "accept" | "reject" | "skipped"
    critic_attempts: int


# ---------------------------------------------------------------------
# Builders — each takes a TelegramUpdateService and returns a compiled
# graph. Keeping them out of the service module avoids a 2000-line file
# and lets LangSmith Studio pick them up by name.
# ---------------------------------------------------------------------


def build_quiz_graph(service):
    graph = StateGraph(QuizState)

    async def branch_mode(state: QuizState) -> QuizState:
        questions = list(state["state_data"].get("questions") or [])
        current_index = int(state["state_data"].get("current_index", 0))
        log_content = str(state["state_data"].get("log_content", ""))
        if current_index >= len(questions):
            return {
                **state,
                "questions": questions,
                "current_index": current_index,
                "log_content": log_content,
                "question": "",
                "mode": "done",
            }
        question = str(questions[current_index])
        mode = "teach" if service._is_idk_answer(state["answer"]) else "grade"
        return {
            **state,
            "questions": questions,
            "current_index": current_index,
            "log_content": log_content,
            "question": question,
            "mode": mode,
        }

    async def evaluate_answer(state: QuizState) -> QuizState:
        from pathwayai_backend.prompts.mentor import (
            MENTOR_SYSTEM_PROMPT,
            QUIZ_EVALUATION_PROMPT,
        )

        result = await service.models.generate(
            system_prompt=MENTOR_SYSTEM_PROMPT,
            user_prompt=QUIZ_EVALUATION_PROMPT.format(
                question=state["question"],
                log_content=state["log_content"],
                answer=state["answer"],
            ),
            fallback=(
                "LEVEL: conceptual\n"
                "FEEDBACK: You showed partial understanding, but your answer "
                "needs more precision and implementation detail.\n"
                "NEXT: Explain one concrete example or failure mode from your work."
            ),
        )
        parsed = service._parse_quiz_evaluation(result.content)
        return {
            **state,
            "feedback": parsed["feedback"],
            "next_action": parsed["next"],
            "level": parsed["level"],
        }

    async def critique_level(state: QuizState) -> QuizState:
        """Second LLM call that may downgrade an overgenerous grade.
        Never upgrades. If the critic is unavailable we keep the
        grader's verdict — failing open is safe because the grader is
        already conservative on the fallback path."""
        import json as _json

        from pathwayai_backend.prompts.mentor import (
            MENTOR_SYSTEM_PROMPT,
            QUIZ_LEVEL_CRITIC_PROMPT,
        )

        levels_rank = {
            "exposure": 0,
            "conceptual": 1,
            "implementation": 2,
            "interview-ready": 3,
        }
        verdict_blob = f"LEVEL: {state['level']}\nFEEDBACK: {state['feedback']}"
        try:
            result = await service.models.generate(
                system_prompt=MENTOR_SYSTEM_PROMPT,
                user_prompt=QUIZ_LEVEL_CRITIC_PROMPT.format(
                    question=state["question"],
                    answer=service._wrap_user_text(state["answer"]),
                    verdict=verdict_blob,
                ),
                fallback=(
                    f'{{"final_level": "{state["level"]}", '
                    f'"reason": "critic unavailable"}}'
                ),
                json_mode=True,
            )
        except Exception:
            return state
        raw = (result.content or "").strip()
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return state
        try:
            data = _json.loads(raw[start : end + 1])
        except _json.JSONDecodeError:
            return state
        critic_level = str(data.get("final_level", "")).lower().strip()
        if critic_level not in levels_rank:
            return state
        # The critic prompt forbids upgrading; defensive code enforces
        # that here so a misbehaving model can't inflate grades.
        if levels_rank[critic_level] > levels_rank[state["level"]]:
            return state
        return {**state, "level": critic_level}

    async def teach_answer(state: QuizState) -> QuizState:
        from pathwayai_backend.prompts.mentor import (
            MENTOR_SYSTEM_PROMPT,
            QUIZ_TEACH_PROMPT,
        )

        result = await service.models.generate(
            system_prompt=MENTOR_SYSTEM_PROMPT,
            user_prompt=QUIZ_TEACH_PROMPT.format(
                question=state["question"],
                log_content=state["log_content"],
                answer=state["answer"],
            ),
            fallback=(
                "TEACH: Re-read your log entry and identify one concrete "
                "implementation step and one tradeoff or failure mode.\n"
                "NEXT: Restate the answer in your own words next time."
            ),
        )
        parsed = service._parse_quiz_teach(result.content)
        return {
            **state,
            "feedback": parsed["teach"],
            "next_action": parsed["next"],
            "level": "exposure",
        }

    async def record_turn(state: QuizState) -> QuizState:
        # Append the turn to in-memory state_data; persistence happens at
        # present_next_question or finalize, depending on whether more
        # questions remain.
        sd = dict(state["state_data"])
        answers = list(sd.get("answers") or [])
        levels = list(sd.get("levels") or [])
        entry = {
            "question": state["question"],
            "answer": state["answer"],
            "feedback": state["feedback"],
        }
        if state["mode"] == "teach":
            entry["mode"] = "taught"
        answers.append(entry)
        levels.append(state["level"])
        sd["answers"] = answers
        sd["levels"] = levels
        return {**state, "state_data": sd}

    async def present_next_question(state: QuizState) -> QuizState:
        next_index = state["current_index"] + 1
        sd = {**state["state_data"], "current_index": next_index}
        await service.repository.upsert_interaction_state(
            state["user_id"], "quiz_waiting_answer", sd
        )
        title = "Teach Mode" if state["mode"] == "teach" else "Quick Feedback"
        reply = (
            f"**{title}**\n{state['feedback']}\n\n"
            f"**Next Question**\n{state['questions'][next_index]}"
        )
        return {**state, "state_data": sd, "reply": reply, "finished": False}

    async def finalize(state: QuizState) -> QuizState:
        await service.repository.clear_interaction_state(state["user_id"])
        levels = list(state["state_data"].get("levels") or [])
        strongest = service._summarize_level(levels)
        local_today = datetime.now(
            ZoneInfo(service.settings.user_timezone)
        ).date()
        await service._add_memory(
            state["user_id"],
            "quiz_assessment",
            f"Quiz assessment {local_today.isoformat()}",
            (
                f"Log: {state['log_content']}\n"
                f"Overall level: {strongest}\n"
                f"Final feedback: {state['feedback']}\n"
                f"Next action: {state['next_action']}"
            ),
            [],
        )
        mastery_topic = await service._resolve_quiz_topic(
            state["user_id"], state["state_data"], state["log_content"]
        )
        mastery_line = ""
        if mastery_topic:
            mastery = await service._record_mastery(
                state["user_id"], mastery_topic, strongest
            )
            mastery_line = (
                f"\n_Topic mastery: {mastery_topic} → {mastery.level}. "
                f"Next re-quiz due {mastery.next_due_at.date().isoformat()}._"
            )
        reply = (
            f"**Quiz Complete**\n"
            f"Overall level: {strongest}\n"
            f"{state['feedback']}\n\n"
            f"**Next Action**\n{state['next_action']}{mastery_line}"
        )
        return {**state, "reply": reply, "finished": True}

    async def already_done(state: QuizState) -> QuizState:
        await service.repository.clear_interaction_state(state["user_id"])
        return {
            **state,
            "reply": "The quiz is already complete. Log more work and tap Quiz Me again.",
            "finished": True,
        }

    def mode_router(state: QuizState) -> str:
        if state["mode"] == "done":
            return "already_done"
        return "teach" if state["mode"] == "teach" else "grade"

    def has_next_router(state: QuizState) -> str:
        next_index = state["current_index"] + 1
        return "next" if next_index < len(state["questions"]) else "finalize"

    graph.add_node("branch_mode", branch_mode)
    graph.add_node("already_done", already_done)
    graph.add_node("evaluate", evaluate_answer)
    graph.add_node("critique_level", critique_level)
    graph.add_node("teach", teach_answer)
    graph.add_node("record_turn", record_turn)
    graph.add_node("present_next_question", present_next_question)
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "branch_mode")
    graph.add_conditional_edges(
        "branch_mode",
        mode_router,
        {"grade": "evaluate", "teach": "teach", "already_done": "already_done"},
    )
    # Grade path runs through the critic; teach path skips it (the
    # teach prompt doesn't produce a LEVEL to second-guess).
    graph.add_edge("evaluate", "critique_level")
    graph.add_edge("critique_level", "record_turn")
    graph.add_edge("teach", "record_turn")
    graph.add_conditional_edges(
        "record_turn",
        has_next_router,
        {"next": "present_next_question", "finalize": "finalize"},
    )
    graph.add_edge("present_next_question", END)
    graph.add_edge("finalize", END)
    graph.add_edge("already_done", END)
    return graph.compile(name="quiz_answer")


def build_mock_interview_graph(service):
    graph = StateGraph(MockState)

    async def record_user_turn(state: MockState) -> MockState:
        sd = dict(state["state_data"])
        transcript = list(sd.get("transcript") or [])
        transcript.append({"role": "candidate", "content": state["answer"]})
        sd["transcript"] = transcript
        return {**state, "state_data": sd}

    def decide(state: MockState) -> str:
        turn = int(state["state_data"].get("turn", 1))
        return "finish" if turn >= service.MOCK_MAX_TURNS else "continue"

    async def probe(state: MockState) -> MockState:
        from pathwayai_backend.prompts.mentor import (
            MENTOR_SYSTEM_PROMPT,
            MOCK_INTERVIEW_TURN_PROMPT,
        )

        sd = state["state_data"]
        transcript = sd.get("transcript") or []
        transcript_text = "\n".join(
            f"{'Interviewer' if turn['role'] == 'interviewer' else 'Candidate'}: "
            f"{turn['content']}"
            for turn in transcript
        )
        result = await service.models.generate(
            system_prompt=MENTOR_SYSTEM_PROMPT,
            user_prompt=MOCK_INTERVIEW_TURN_PROMPT.format(
                topic=sd.get("topic", "general"),
                transcript=transcript_text,
                answer=service._wrap_user_text(state["answer"]),
            ),
            fallback=(
                "Okay. Push deeper: what is the dominant failure mode of your "
                "approach, and how would you detect it in production?"
            ),
        )
        next_question = result.content.strip()
        next_turn = int(sd.get("turn", 1)) + 1
        new_transcript = list(transcript)
        new_transcript.append({"role": "interviewer", "content": next_question})
        new_sd = {
            **sd,
            "turn": next_turn,
            "transcript": new_transcript,
        }
        await service.repository.upsert_interaction_state(
            state["user_id"], "mock_interview", new_sd
        )
        reply = (
            f"{next_question}\n\n"
            f"_Turn {next_turn}/{service.MOCK_MAX_TURNS}. `/end` to stop._"
        )
        return {**state, "state_data": new_sd, "reply": reply, "finished": False}

    async def finalize_interview(state: MockState) -> MockState:
        final = await service._finish_mock_interview(
            state["user_id"], state["state_data"]
        )
        return {**state, "reply": final, "finished": True}

    graph.add_node("record_user_turn", record_user_turn)
    graph.add_node("probe", probe)
    graph.add_node("finalize_interview", finalize_interview)

    graph.add_edge(START, "record_user_turn")
    graph.add_conditional_edges(
        "record_user_turn",
        decide,
        {"continue": "probe", "finish": "finalize_interview"},
    )
    graph.add_edge("probe", END)
    graph.add_edge("finalize_interview", END)
    return graph.compile(name="mock_interview_turn")


def build_chat_graph(service):
    graph = StateGraph(ChatState)

    async def maybe_compact(state: ChatState) -> ChatState:
        await service._maybe_compact_conversation(state["user_id"])
        return state

    async def load_context(state: ChatState) -> ChatState:
        # Sequential, single AsyncSession — safe.
        local_now = datetime.now(ZoneInfo(service.settings.user_timezone))
        goals = await service.repository.goals_for_date(
            state["user_id"], local_now.date()
        )
        recent_logs = await service.repository.recent_logs_limited(
            state["user_id"], limit=5
        )
        memories = await service.repository.recent_memories(state["user_id"], days=14)
        history = await service.repository.recent_conversation_messages(
            state["user_id"], limit=12
        )
        return {
            **state,
            "goals": goals,
            "recent_logs": recent_logs,
            "memories": memories,
            "history": history,
        }

    async def maybe_remember_instruction(state: ChatState) -> ChatState:
        if service._looks_like_instruction(state["text"]):
            local_now = datetime.now(ZoneInfo(service.settings.user_timezone))
            await service._add_memory(
                state["user_id"],
                "user_instruction",
                f"Instruction {local_now.date().isoformat()}",
                state["text"],
                [],
            )
        return state

    async def llm_reply(state: ChatState) -> ChatState:
        from pathwayai_backend.prompts.mentor import (
            CHAT_PROMPT,
            MENTOR_SYSTEM_PROMPT,
        )

        recent_logs_text = "\n".join(
            f"- {log.content}" for log in state["recent_logs"]
        ) or "None"
        memory_text = "\n".join(
            f"- {item.title}: {item.content}" for item in state["memories"][:8]
        ) or "None"
        transcript_lines: list[str] = []
        for msg in state["history"]:
            if msg.direction == "inbound":
                transcript_lines.append(f"User: {msg.content}")
            else:
                transcript_lines.append(f"Mentor: {msg.content}")
        transcript = "\n".join(transcript_lines) or "None"
        goals = state.get("goals") or []
        goal_text = (
            "\n".join(f"- {g.content}" for g in goals)
            if goals
            else "No goal declared today"
        )
        result = await service.models.generate(
            system_prompt=MENTOR_SYSTEM_PROMPT,
            user_prompt=CHAT_PROMPT.format(
                goal=goal_text,
                recent_logs=recent_logs_text,
                memory=memory_text,
                transcript=transcript,
                message=service._wrap_user_text(state["text"]),
            ),
            fallback=(
                "Noted. Tell me a bit more about what you want from today's session "
                "so I can adapt — even a quick constraint helps."
            ),
        )
        return {**state, "reply": result.content}

    graph.add_node("maybe_compact", maybe_compact)
    graph.add_node("load_context", load_context)
    graph.add_node("maybe_remember_instruction", maybe_remember_instruction)
    graph.add_node("llm_reply", llm_reply)

    graph.add_edge(START, "maybe_compact")
    graph.add_edge("maybe_compact", "load_context")
    graph.add_edge("load_context", "maybe_remember_instruction")
    graph.add_edge("maybe_remember_instruction", "llm_reply")
    graph.add_edge("llm_reply", END)
    return graph.compile(name="chat")


def build_log_extraction_graph(service):
    """Log extraction graph with a single-shot self-evaluator.

    extract → critique → (accept → persist | reject → reextract → persist)
    → compute_streak → conditional notify.

    The critic is a separate LLM call that checks whether the extracted
    `topic` is actually evidenced in the raw log. A "reject" verdict
    discards the fields and reruns extraction once with stricter context;
    if the rerun still hallucinates, we persist no fields rather than
    polluting topic mastery."""
    import json as _json

    graph = StateGraph(LogExtractionState)

    async def extract(state: LogExtractionState) -> LogExtractionState:
        fields = await service._extract_log_fields(state["content"])
        attempts = int(state.get("critic_attempts", 0)) + 1
        return {**state, "fields": fields or {}, "critic_attempts": attempts}

    async def critique(state: LogExtractionState) -> LogExtractionState:
        # Cheap exit: no topic was extracted, nothing to verify.
        fields = state.get("fields") or {}
        if not fields.get("topic"):
            return {**state, "critic_verdict": "skipped"}

        from pathwayai_backend.prompts.mentor import (
            LOG_EXTRACTION_CRITIC_PROMPT,
            MENTOR_SYSTEM_PROMPT,
        )

        extracted_blob = _json.dumps(
            {
                "topic": fields.get("topic"),
                "difficulty": fields.get("difficulty"),
                "built": fields.get("built"),
                "interview_story": fields.get("interview_story"),
            },
            sort_keys=True,
        )
        try:
            result = await service.models.generate(
                system_prompt=MENTOR_SYSTEM_PROMPT,
                user_prompt=LOG_EXTRACTION_CRITIC_PROMPT.format(
                    log_content=service._wrap_user_text(state["content"]),
                    extracted=extracted_blob,
                ),
                fallback='{"verdict": "accept", "reason": "critic unavailable"}',
                json_mode=True,
            )
        except Exception:
            return {**state, "critic_verdict": "accept"}
        raw = (result.content or "").strip()
        verdict = "accept"
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = _json.loads(raw[start : end + 1])
                parsed = str(data.get("verdict", "")).lower().strip()
                if parsed in {"accept", "reject"}:
                    verdict = parsed
            except _json.JSONDecodeError:
                pass
        return {**state, "critic_verdict": verdict}

    def critic_router(state: LogExtractionState) -> str:
        verdict = state.get("critic_verdict", "accept")
        attempts = int(state.get("critic_attempts", 0))
        if verdict == "reject" and attempts < 2:
            return "retry"
        if verdict == "reject":
            return "drop"
        return "accept"

    async def drop_fields(state: LogExtractionState) -> LogExtractionState:
        """Critic rejected twice — discard fields so we don't pollute
        mastery with a hallucinated topic. Notify path still runs in
        case the streak is worth surfacing."""
        return {**state, "fields": {}}

    async def persist(state: LogExtractionState) -> LogExtractionState:
        fields = state.get("fields") or {}
        if fields:
            try:
                await service.repository.update_log_fields(state["log_id"], fields)
                await service.session.commit()
            except Exception:
                # _finalize_log_extraction logs this; keep the graph going
                # so we still try to notify if the streak is worth surfacing.
                return {**state, "fields": {}}
        return state

    async def compute_streak(state: LogExtractionState) -> LogExtractionState:
        streak = await service._current_streak(state["user_id"])
        return {**state, "streak": streak}

    async def notify(state: LogExtractionState) -> LogExtractionState:
        fields = state.get("fields") or {}
        topic = fields.get("topic")
        difficulty = fields.get("difficulty")
        streak = state.get("streak", 0)
        parts: list[str] = []
        if topic:
            parts.append(
                f"Indexed: topic = {topic}"
                + (f" · difficulty = {difficulty}" if difficulty else "")
            )
        if streak >= 2:
            parts.append(f"🔥 Streak: {streak} days")
        if parts:
            try:
                await service.telegram.send_message(
                    "\n".join(parts), chat_id=state["chat_id"]
                )
            except Exception:
                pass
        return {**state, "notify_text": "\n".join(parts)}

    def should_notify(state: LogExtractionState) -> str:
        fields = state.get("fields") or {}
        streak = state.get("streak", 0)
        if fields.get("topic") or streak >= 2:
            return "notify"
        return "skip"

    graph.add_node("extract", extract)
    graph.add_node("critique", critique)
    graph.add_node("drop_fields", drop_fields)
    graph.add_node("persist", persist)
    graph.add_node("compute_streak", compute_streak)
    graph.add_node("notify", notify)

    graph.add_edge(START, "extract")
    graph.add_edge("extract", "critique")
    graph.add_conditional_edges(
        "critique",
        critic_router,
        {"accept": "persist", "retry": "extract", "drop": "drop_fields"},
    )
    graph.add_edge("drop_fields", "compute_streak")
    graph.add_edge("persist", "compute_streak")
    graph.add_conditional_edges(
        "compute_streak",
        should_notify,
        {"notify": "notify", "skip": END},
    )
    graph.add_edge("notify", END)
    return graph.compile(name="log_extraction")


__all__ = [
    "build_chat_graph",
    "build_log_extraction_graph",
    "build_mock_interview_graph",
    "build_quiz_graph",
    "QuizState",
    "MockState",
    "ChatState",
    "LogExtractionState",
]


# Re-export utility for the log_extraction node so the service can stay
# uncoupled from the timedelta import here.
_ = timedelta
_ = UTC
