from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from pathwayai_backend.workflows.scoring import SCORE_VERSION, calculate_readiness


def test_readiness_score_is_deterministic_and_evidence_based() -> None:
    now = datetime.now(UTC)
    events = [
        SimpleNamespace(source="github", occurred_at=now - timedelta(days=day))
        for day in range(5)
    ]
    events += [
        SimpleNamespace(source="leetcode", occurred_at=now - timedelta(days=day))
        for day in range(4)
    ]
    logs = [SimpleNamespace(content=f"log {index}") for index in range(5)]
    memories = [
        SimpleNamespace(memory_type="interview_assessment") for _ in range(2)
    ]

    score = calculate_readiness(events, logs, memories)

    assert score.score_version == SCORE_VERSION
    assert score.overall_score == 87.3
    assert score.confidence == 0.8
    assert score.evidence["github_active_days"] == 5
    assert score.evidence["leetcode_active_days"] == 4


def test_readiness_reports_missing_evidence() -> None:
    score = calculate_readiness([], [])

    assert score.overall_score == 0
    assert score.confidence == 0
    assert len(score.gap_analysis["missing_evidence_or_gaps"]) == 4
