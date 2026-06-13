"""Project coaching: propose a step plan (t2), guide step-by-step, review the finished build."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.nodes import project as project_node
from app.agents.nodes import socratic
from app.agents.schemas import EvalSchema, ProjectPlan, ProjectStep
from app.db.models import Phase, Project, ProjectProgress, User, UserState
from app.engines import progress as progress_engine


async def _phase_id(session: AsyncSession, state: UserState) -> int | None:
    if state.current_phase_id is not None:
        return state.current_phase_id
    return await session.scalar(
        select(Project.phase_id)
        .join(Phase, Project.phase_id == Phase.id)
        .order_by(Phase.sort_order.desc())
        .limit(1)
    )


async def get_in_progress(
    session: AsyncSession, user: User, state: UserState
) -> ProjectProgress | None:
    """An active or proposed (not-done) project for the user's current phase."""
    phase_id = await _phase_id(session, state)
    if phase_id is None:
        return None
    rows = await session.execute(
        select(ProjectProgress)
        .join(Project, ProjectProgress.project_id == Project.id)
        .where(
            ProjectProgress.user_id == user.id,
            Project.phase_id == phase_id,
            ProjectProgress.status != "done",
        )
        .order_by(ProjectProgress.id)
    )
    return rows.scalars().first()


async def propose_next(
    session: AsyncSession, user: User, state: UserState
) -> tuple[ProjectProgress, Project] | None:
    """Pick the current phase's first project the user hasn't started, build & store a plan."""
    phase_id = await _phase_id(session, state)
    if phase_id is None:
        return None
    started_ids = {
        pid
        for (pid,) in (
            await session.execute(
                select(ProjectProgress.project_id).where(ProjectProgress.user_id == user.id)
            )
        ).all()
    }
    projects = list(
        (
            await session.execute(
                select(Project).where(Project.phase_id == phase_id).order_by(Project.id)
            )
        ).scalars()
    )
    project = next((p for p in projects if p.id not in started_ids), None)
    if project is None:
        return None

    phase = await session.get(Phase, project.phase_id)
    profile = await progress_engine.build_profile(session, user, state)
    plan = await project_node.generate_plan(
        session,
        profile=profile,
        project_title=project.title,
        project_slug=project.slug,
        phase_title=phase.title,
        brief=project.brief_md,
        user_id=user.id,
    )
    pp = ProjectProgress(
        user_id=user.id,
        project_id=project.id,
        plan_json=plan.model_dump(),
        current_step=0,
        total_steps=len(plan.steps),
        status="proposed",
    )
    session.add(pp)
    await session.commit()
    return pp, project


def plan_of(pp: ProjectProgress) -> ProjectPlan:
    return ProjectPlan.model_validate(pp.plan_json)


def current_step(pp: ProjectProgress) -> ProjectStep | None:
    steps = plan_of(pp).steps
    if 0 <= pp.current_step < len(steps):
        return steps[pp.current_step]
    return None


async def start(session: AsyncSession, pp: ProjectProgress) -> None:
    pp.status = "active"
    pp.current_step = 0
    await session.commit()


async def advance(session: AsyncSession, user: User, state: UserState, pp: ProjectProgress) -> dict:
    """Mark the current step done; move to the next. Returns the new position."""
    pp.current_step += 1
    progress_engine.tick_activity(state, progress_engine.XP["project_step"])
    completed_all = pp.current_step >= pp.total_steps
    await session.commit()
    return {
        "completed_all": completed_all,
        "step": current_step(pp),
        "index": pp.current_step,
        "total": pp.total_steps,
    }


async def guidance(
    session: AsyncSession, user: User, state: UserState, pp: ProjectProgress
) -> str:
    step = current_step(pp)
    plan = plan_of(pp)
    profile = await progress_engine.build_profile(session, user, state)
    question = (
        f"I'm building the project '{plan.title}' and I'm stuck on this step: "
        f"{step.title} — {step.goal}. {step.details_md} "
        "Give me a hint to move forward, not the full solution."
    )
    return await socratic.answer_question(
        session,
        profile=profile,
        topic_title=plan.title,
        phase_title="project work",
        question=question,
        user_id=user.id,
    )


async def review_final(
    session: AsyncSession, user: User, state: UserState, pp: ProjectProgress, text: str
) -> EvalSchema:
    plan = plan_of(pp)
    project = await session.get(Project, pp.project_id)
    profile = await progress_engine.build_profile(session, user, state)
    result = await project_node.review_project(
        session,
        profile=profile,
        project_title=project.title,
        overview=plan.overview,
        submission=text,
        user_id=user.id,
    )
    pp.status = "done"
    pp.notes_md = text[:4000]
    progress_engine.tick_activity(state, progress_engine.XP["project_step"] * 2)  # completion bonus
    await session.commit()
    return result
