"""Coding exercises: issue, detect pending submission, grade against a rubric (tier t2).

The exercise spec (title, hints, rubric, starter) lives in Exercise.feedback_json until the
submission is graded, when the grade is merged in under "result". No extra columns needed.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.nodes import evaluator, exercise_writer
from app.agents.schemas import EvalSchema, ExerciseSchema
from app.db.models import Exercise, Phase, Topic, User, UserState
from app.engines import progress


async def get_pending(session: AsyncSession, user: User, state: UserState) -> Exercise | None:
    """An issued-but-not-yet-submitted exercise for the user's current topic, if any."""
    if state.current_topic_id is None:
        return None
    return await session.scalar(
        select(Exercise)
        .where(
            Exercise.user_id == user.id,
            Exercise.topic_id == state.current_topic_id,
            Exercise.status == "issued",
        )
        .order_by(Exercise.id.desc())
        .limit(1)
    )


async def issue(
    session: AsyncSession, user: User, state: UserState
) -> tuple[Exercise, ExerciseSchema] | None:
    if state.current_topic_id is None:
        return None
    topic = await session.get(Topic, state.current_topic_id)
    phase = await session.get(Phase, topic.phase_id)
    profile = await progress.build_profile(session, user, state)
    schema = await exercise_writer.generate_exercise(
        session,
        profile=profile,
        topic_title=topic.title,
        topic_slug=topic.slug,
        phase_title=phase.title,
        user_id=user.id,
    )
    ex = Exercise(
        user_id=user.id,
        topic_id=topic.id,
        prompt_md=schema.prompt_md,
        feedback_json={
            "title": schema.title,
            "hints": schema.hints,
            "rubric": schema.rubric,
            "starter": schema.starter_code,
        },
        status="issued",
    )
    session.add(ex)
    await session.commit()
    return ex, schema


def hints_of(ex: Exercise) -> list[str]:
    return (ex.feedback_json or {}).get("hints", [])


async def submit(
    session: AsyncSession, user: User, state: UserState, ex: Exercise, text: str
) -> EvalSchema:
    topic = await session.get(Topic, ex.topic_id)
    profile = await progress.build_profile(session, user, state)
    spec = ex.feedback_json or {}
    result = await evaluator.evaluate_submission(
        session,
        profile=profile,
        topic_title=topic.title,
        prompt_md=ex.prompt_md,
        rubric=spec.get("rubric", []),
        submission=text,
        user_id=user.id,
    )
    ex.submission_md = text
    ex.feedback_json = {**spec, "result": result.model_dump()}
    ex.status = "reviewed"
    progress.tick_activity(state, progress.XP["exercise"])  # reward the effort, pass or not
    await session.commit()
    return result


async def skip(session: AsyncSession, ex: Exercise) -> None:
    ex.feedback_json = {**(ex.feedback_json or {}), "skipped": True}
    ex.status = "reviewed"
    await session.commit()
