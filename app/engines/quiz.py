"""Quiz lifecycle: generate, answer (idempotent), finalize with the adaptive rule.

Adaptive rule (docs/01_PRODUCT_SPEC.md §5.3):
  >=80%  advance to next topic           (outcome "advance")
  50-79  advance but flag topic as weak  (outcome "flagged")
  <50    stay; next lesson = simplified  (outcome "repeat")
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.nodes import quiz_master
from app.agents.schemas import QuizSchema
from app.db.models import (
    Phase,
    QuestionBank,
    Quiz,
    QuizAttempt,
    ReviewItem,
    Topic,
    User,
    UserState,
)
from app.engines import learning, progress


async def start_for_topic(
    session: AsyncSession, user: User, state: UserState, topic: Topic, kind: str = "lesson"
) -> tuple[Quiz, QuizAttempt]:
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
    quiz = Quiz(user_id=user.id, topic_id=topic.id, kind=kind, questions_json=schema.model_dump())
    session.add(quiz)
    await session.flush()
    for q in schema.questions:
        session.add(QuestionBank(topic_id=topic.id, question_json=q.model_dump()))
    attempt = QuizAttempt(quiz_id=quiz.id, user_id=user.id, answers_json={})
    session.add(attempt)
    await session.commit()
    return quiz, attempt


def questions_of(quiz: Quiz) -> QuizSchema:
    return QuizSchema.model_validate(quiz.questions_json)


def record_answer(attempt: QuizAttempt, quiz: Quiz, q_idx: int, choice: int) -> dict | None:
    """Store one answer. Returns feedback dict, or None if q_idx was already answered."""
    if str(q_idx) in attempt.answers_json:
        return None
    q = questions_of(quiz).questions[q_idx]
    attempt.answers_json = {**attempt.answers_json, str(q_idx): choice}
    correct = choice == q.correct_index
    return {
        "correct": correct,
        "correct_option": q.options[q.correct_index],
        "explanation": q.explanation,
        "answered": len(attempt.answers_json),
        "total": len(questions_of(quiz).questions),
    }


async def finalize(
    session: AsyncSession, user: User, state: UserState, quiz: Quiz, attempt: QuizAttempt
) -> dict:
    qs = questions_of(quiz).questions
    n = len(qs)
    n_correct = sum(
        1 for i, q in enumerate(qs) if attempt.answers_json.get(str(i)) == q.correct_index
    )
    score = round(100 * n_correct / n, 1)
    attempt.score_pct = score
    attempt.finished_at = datetime.now(UTC)
    attempt.weak_tags_json = {
        "tags": [q.concept_tag for i, q in enumerate(qs)
                 if attempt.answers_json.get(str(i)) != q.correct_index]
    }

    outcome = "advance" if score >= 80 else ("flagged" if score >= 50 else "repeat")
    xp_gain = progress.XP["quiz"] + (progress.XP["quiz_bonus"] if score >= 80 else 0)
    next_title: str | None = None

    if quiz.kind == "lesson":
        # consume the active lesson for this topic, if any
        if state.active_lesson_id:
            from app.db.models import Lesson

            lesson = await session.get(Lesson, state.active_lesson_id)
            if lesson and lesson.topic_id == quiz.topic_id:
                await learning.complete_lesson(session, state, lesson)
                xp_gain += progress.XP["lesson"]
        if outcome in ("advance", "flagged"):
            await _ensure_review_item(session, user.id, quiz.topic_id)
            nxt = await learning.next_topic(session, state)
            if nxt is not None:
                state.current_topic_id = nxt.id
                state.current_phase_id = nxt.phase_id
                next_title = nxt.title
            else:
                state.current_topic_id = None
                next_title = None

    progress.tick_activity(state, xp_gain)
    await session.commit()
    return {
        "score": score,
        "n_correct": n_correct,
        "n_total": n,
        "outcome": outcome,
        "next_topic_title": next_title,
        "weak_tags": attempt.weak_tags_json["tags"],
        "streak": state.streak_count,
        "xp_gain": xp_gain,
        "xp_total": state.xp,
    }


async def _ensure_review_item(session: AsyncSession, user_id: int, topic_id: int) -> None:
    item = await session.scalar(
        select(ReviewItem).where(ReviewItem.user_id == user_id, ReviewItem.topic_id == topic_id)
    )
    if item is None:
        session.add(
            ReviewItem(
                user_id=user_id,
                topic_id=topic_id,
                ladder_index=0,
                due_date=date.today() + timedelta(days=1),
            )
        )
