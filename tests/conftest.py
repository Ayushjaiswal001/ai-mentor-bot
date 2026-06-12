from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import Base, Phase, Topic, User, UserState


@pytest.fixture
async def session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest.fixture
async def env(session):
    """A user positioned at topic 1 of a two-topic mini-curriculum."""
    phase = Phase(slug="p1", title="Phase One", sort_order=0)
    session.add(phase)
    await session.flush()
    t1 = Topic(phase_id=phase.id, slug="variables", title="Variables", sort_order=0)
    t2 = Topic(phase_id=phase.id, slug="data-types", title="Data Types", sort_order=1)
    session.add_all([t1, t2])
    await session.flush()
    user = User(tg_user_id=111, first_name="Ayush")
    session.add(user)
    await session.flush()
    state = UserState(user_id=user.id, current_phase_id=phase.id, current_topic_id=t1.id)
    session.add(state)
    await session.commit()
    return SimpleNamespace(session=session, user=user, state=state, phase=phase, t1=t1, t2=t2)
