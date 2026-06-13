"""Spaced repetition: due-item queries, review-quiz building, ladder promote/demote.

Ladder (docs/01_PRODUCT_SPEC.md §5.2): indices 0..4 map to intervals [1,3,7,14,30] days.
A review passes when >=2/3 of its questions are correct. Pass → promote one rung (longer
gap). Fail → demote one rung (sooner) and count a lapse. Promote past rung 4 = retired.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.nodes import quiz_master
from app.db.models import Phase, QuestionBank, Quiz, QuizAttempt, ReviewItem, Topic, User, UserState
from app.engines import progress

LADDER = [1, 3, 7, 14, 30]
RETIRED = len(LADDER)  # ladder_index == 5 → topic retired from active revision
REVIEW_QUESTIONS = 3


def is_pass(n_correct: int, n_total: int) -> bool:
    """True when at least two-thirds correct (avoids float rounding: 3*c >= 2*t)."""
    return 3 * n_correct >= 2 * n_total


def apply_ladder(item: ReviewItem, passed: bool, today: date | None = None) -> None:
    """Pure ladder transition — mutates the item, no DB. `today` injectable for tests."""
    today = today or date.today()
    if passed:
        item.ladder_index = min(item.ladder_index + 1, RETIRED)
        item.last_result = "pass"
    else:
        item.ladder_index = max(item.ladder_index - 1, 0)
        item.lapses += 1
        item.last_result = "fail"
    if item.ladder_index >= RETIRED:
        item.due_date = today + timedelta(days=365)  # parked far out; resurfaces in weekly only
    else:
        item.due_date = today + timedelta(days=LADDER[item.ladder_index])


async def due(session: AsyncSession, user: User) -> list[tuple[ReviewItem, Topic]]:
    rows = await session.execute(
        select(ReviewItem, Topic)
        .join(Topic, ReviewItem.topic_id == Topic.id)
        .where(
            ReviewItem.user_id == user.id,
            ReviewItem.due_date <= date.today(),
            ReviewItem.ladder_index < RETIRED,
        )
        .order_by(ReviewItem.due_date, ReviewItem.ladder_index)
    )
    return list(rows.all())


async def count_due(session: AsyncSession, user: User) -> int:
    return (
        await session.scalar(
            select(func.count(ReviewItem.id)).where(
                ReviewItem.user_id == user.id,
                ReviewItem.due_date <= date.today(),
                ReviewItem.ladder_index < RETIRED,
            )
        )
    ) or 0


async def _sample_questions(
    session: AsyncSession, user: User, state: UserState, topic: Topic
) -> list[dict]:
    """Bank-first: reuse least-used stored questions; generate (and bank) only if thin."""
    rows = list(
        (
            await session.execute(
                select(QuestionBank)
                .where(QuestionBank.topic_id == topic.id)
                .order_by(QuestionBank.times_used, QuestionBank.id)
                .limit(REVIEW_QUESTIONS)
            )
        ).scalars()
    )
    if len(rows) >= REVIEW_QUESTIONS:
        for r in rows:
            r.times_used += 1
            r.last_used_at = datetime.now(UTC)
        return [r.question_json for r in rows]

    phase = await session.get(Phase, topic.phase_id)
    profile = await progress.build_profile(session, user, state)
    schema = await quiz_master.generate_quiz(
        session,
        profile=profile,
        topic_title=topic.title,
        topic_slug=topic.slug,
        phase_title=phase.title,
        user_id=user.id,
    )
    for q in schema.questions:
        session.add(QuestionBank(topic_id=topic.id, question_json=q.model_dump()))
    await session.flush()
    return [q.model_dump() for q in schema.questions[:REVIEW_QUESTIONS]]


async def start_revision(
    session: AsyncSession, user: User, state: UserState, item: ReviewItem
) -> tuple[Quiz, QuizAttempt, Topic]:
    topic = await session.get(Topic, item.topic_id)
    questions = await _sample_questions(session, user, state, topic)
    quiz = Quiz(
        user_id=user.id,
        topic_id=topic.id,
        kind="revision",
        questions_json={"topic_slug": topic.slug, "questions": questions},
    )
    session.add(quiz)
    await session.flush()
    attempt = QuizAttempt(quiz_id=quiz.id, user_id=user.id, answers_json={})
    session.add(attempt)
    await session.commit()
    return quiz, attempt, topic


async def record_review(
    session: AsyncSession, user: User, topic_id: int, n_correct: int, n_total: int
) -> dict:
    """Apply the ladder to this topic's review item. Caller commits."""
    passed = is_pass(n_correct, n_total)
    item = await session.scalar(
        select(ReviewItem).where(
            ReviewItem.user_id == user.id, ReviewItem.topic_id == topic_id
        )
    )
    if item is None:  # defensive: shouldn't happen (created on lesson pass)
        item = ReviewItem(user_id=user.id, topic_id=topic_id, ladder_index=0, due_date=date.today())
        session.add(item)
    apply_ladder(item, passed)
    interval = None if item.ladder_index >= RETIRED else LADDER[item.ladder_index]
    return {
        "passed": passed,
        "retired": item.ladder_index >= RETIRED,
        "next_interval_days": interval,
    }
