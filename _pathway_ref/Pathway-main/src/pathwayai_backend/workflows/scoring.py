from dataclasses import asdict, dataclass

from pathwayai_backend.db.models import ActivityEvent, LearningLog, MemorySummary

SCORE_VERSION = "2026-06-v1"


@dataclass(frozen=True)
class ScoreResult:
    overall_score: float
    confidence: float
    score_version: str
    subscores: dict[str, float]
    gap_analysis: dict[str, list[str]]
    evidence: dict[str, int | float]

    def as_dict(self) -> dict:
        return asdict(self)


def calculate_readiness(
    events: list[ActivityEvent],
    logs: list[LearningLog],
    memories: list[MemorySummary] | None = None,
) -> ScoreResult:
    memories = memories or []
    github_events = [event for event in events if event.source == "github"]
    leetcode_events = [event for event in events if event.source == "leetcode"]
    github_days = len({event.occurred_at.date() for event in github_events})
    leetcode_days = len({event.occurred_at.date() for event in leetcode_events})
    interview_memories = [
        memory for memory in memories if memory.memory_type == "interview_assessment"
    ]

    engineering = min(100.0, github_days / 5 * 100)
    dsa = min(100.0, leetcode_days / 5 * 100)
    learning = min(100.0, len(logs) / 5 * 100)
    interview = min(100.0, len(interview_memories) / 3 * 100)
    consistency = min(100.0, (github_days + leetcode_days) / 7 * 100)

    subscores = {
        "engineering_consistency": round(engineering, 1),
        "dsa_consistency": round(dsa, 1),
        "learning_evidence": round(learning, 1),
        "interview_evidence": round(interview, 1),
        "overall_consistency": round(consistency, 1),
    }
    overall = (
        engineering * 0.25
        + dsa * 0.30
        + learning * 0.15
        + interview * 0.20
        + consistency * 0.10
    )

    missing: list[str] = []
    if github_days < 3:
        missing.append("Insufficient recent engineering activity evidence")
    if leetcode_days < 3:
        missing.append("Insufficient recent DSA consistency evidence")
    if not interview_memories:
        missing.append("No stored interview-depth assessments yet")
    if len(logs) < 3:
        missing.append("Few learning reflections were recorded")

    evidence_units = (
        len(github_events) + len(leetcode_events) + len(logs) + len(memories)
    )
    confidence = min(1.0, evidence_units / 20)
    return ScoreResult(
        overall_score=round(overall, 1),
        confidence=round(confidence, 2),
        score_version=SCORE_VERSION,
        subscores=subscores,
        gap_analysis={"missing_evidence_or_gaps": missing},
        evidence={
            "github_events": len(github_events),
            "github_active_days": github_days,
            "leetcode_events": len(leetcode_events),
            "leetcode_active_days": leetcode_days,
            "learning_logs": len(logs),
            "interview_assessments": len(interview_memories),
        },
    )
