from pathlib import Path

from sqlalchemy import func, select

from app.db.models import Phase, Project, Topic
from app.scripts.seed import load_roadmap, seed

ROADMAP_PATH = Path(__file__).resolve().parents[2] / "content" / "roadmap.yaml"

EXPECTED = {"phases": 12, "topics": 75, "projects": 10}


async def test_seed_loads_full_roadmap(session):
    counts = await seed(session, load_roadmap(ROADMAP_PATH))
    assert counts == EXPECTED


async def test_seed_is_idempotent(session):
    roadmap = load_roadmap(ROADMAP_PATH)
    await seed(session, roadmap)
    await seed(session, roadmap)
    assert await session.scalar(select(func.count(Phase.id))) == EXPECTED["phases"]
    assert await session.scalar(select(func.count(Topic.id))) == EXPECTED["topics"]
    assert await session.scalar(select(func.count(Project.id))) == EXPECTED["projects"]


async def test_titles_order_and_capstone_brief(session):
    await seed(session, load_roadmap(ROADMAP_PATH))

    oop = await session.scalar(select(Topic).where(Topic.slug == "oop"))
    assert oop.title == "OOP"

    first_phase = await session.scalar(select(Phase).where(Phase.sort_order == 0))
    assert first_phase.slug == "python-fundamentals"

    capstone = await session.scalar(
        select(Project).where(Project.slug == "ai-interview-assistant")
    )
    assert capstone.brief_md and "resume upload" in capstone.brief_md.lower()
