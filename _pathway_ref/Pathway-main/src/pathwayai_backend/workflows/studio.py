"""Module-level graph factories for LangGraph Studio.

`langgraph dev` reads `langgraph.json` and imports the entries below to
visualize each graph's topology. The graphs work with real dependencies
when invoked through the running app; for Studio inspection we pass a
stub service that satisfies the attribute lookups during compile but is
not expected to execute every node.

To launch Studio:

    uv run langgraph dev

Then open the URL the CLI prints. Each graph shows its nodes and edges
(parallel and conditional included). Set `LANGSMITH_TRACING=true` in
your environment to ship live traces from the real app to LangSmith.
"""

from typing import Any
from unittest.mock import MagicMock

from pathwayai_backend.config import get_settings


def _stub_service() -> Any:
    """A no-op stand-in that exposes the attributes graph builders read
    at compile time. The graph topology is fully described by the
    builder call; nodes that need real IO will only execute when the
    graph is invoked from the running FastAPI app."""

    settings = get_settings()

    stub = MagicMock()
    stub.settings = settings
    stub.MOCK_MAX_TURNS = 5
    stub._wrap_user_text = lambda text: f"<USER_INPUT>{text}</USER_INPUT>"

    # Static helpers used by quiz nodes — copy real implementations.
    from pathwayai_backend.services.telegram_updates import TelegramUpdateService

    stub._is_idk_answer = TelegramUpdateService._is_idk_answer
    stub._parse_quiz_evaluation = TelegramUpdateService._parse_quiz_evaluation
    stub._parse_quiz_teach = TelegramUpdateService._parse_quiz_teach
    stub._summarize_level = TelegramUpdateService._summarize_level
    stub._looks_like_instruction = TelegramUpdateService._looks_like_instruction

    return stub


def make_mentor_engine():
    """Return a MentorWorkflowEngine with stub IO for Studio rendering.

    The compiled graphs (`_morning_graph`, `_evening_graph`,
    `_weekly_graph`) are exposed via the engine instance below."""
    from pathwayai_backend.workflows.mentor import MentorWorkflowEngine

    settings = get_settings()
    repository = MagicMock()
    model_gateway = MagicMock()
    telegram = MagicMock()
    return MentorWorkflowEngine(
        settings=settings,
        repository=repository,
        model_gateway=model_gateway,
        telegram=telegram,
    )


# ---------------------------------------------------------------------
# Graphs exposed to LangGraph Studio
# ---------------------------------------------------------------------

_engine = make_mentor_engine()
morning_graph = _engine._morning_graph
evening_graph = _engine._evening_graph
weekly_graph = _engine._weekly_graph

_stub = _stub_service()

from pathwayai_backend.workflows.conversation import (  # noqa: E402
    build_chat_graph,
    build_log_extraction_graph,
    build_mock_interview_graph,
    build_quiz_graph,
)

quiz_graph = build_quiz_graph(_stub)
mock_interview_graph = build_mock_interview_graph(_stub)
chat_graph = build_chat_graph(_stub)
log_extraction_graph = build_log_extraction_graph(_stub)


__all__ = [
    "chat_graph",
    "evening_graph",
    "log_extraction_graph",
    "mock_interview_graph",
    "morning_graph",
    "quiz_graph",
    "weekly_graph",
]
