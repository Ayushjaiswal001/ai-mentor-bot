"""Load content/roadmap.yaml into the curriculum tables. Idempotent — upserts by slug.

Usage: python -m app.scripts.seed
"""

import asyncio
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Phase, Project, Topic

TITLE_OVERRIDES = {
    "oop": "OOP",
    "working-with-apis": "Working with APIs",
    "what-is-ml": "What is ML?",
    "fastapi-basics": "FastAPI Basics",
    "get-and-post": "GET and POST",
    "async-in-fastapi": "Async in FastAPI",
    "rag": "RAG",
    "rag-with-langchain": "RAG with LangChain",
    "what-are-ai-agents": "What are AI Agents?",
    "lstm": "LSTM",
    "pdf-chatbot": "PDF Chatbot",
    "notes-api": "Notes API",
    "todo-api": "Todo API",
    "ai-interview-assistant": "AI Interview Assistant",
}


def derive_title(slug: str) -> str:
    return TITLE_OVERRIDES.get(slug, slug.replace("-", " ").title())


def load_roadmap(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


async def seed(session: AsyncSession, roadmap: dict) -> dict[str, int]:
    counts = {"phases": 0, "topics": 0, "projects": 0}

    for p_idx, p in enumerate(roadmap["phases"]):
        phase = await session.scalar(select(Phase).where(Phase.slug == p["slug"]))
        if phase is None:
            phase = Phase(slug=p["slug"], title="", sort_order=p_idx)
            session.add(phase)
        phase.title = p.get("title") or derive_title(p["slug"])
        phase.sort_order = p_idx
        await session.flush()  # ensure phase.id for children
        counts["phases"] += 1

        for t_idx, t_slug in enumerate(p.get("topics") or []):
            topic = await session.scalar(
                select(Topic).where(Topic.phase_id == phase.id, Topic.slug == t_slug)
            )
            if topic is None:
                topic = Topic(phase_id=phase.id, slug=t_slug, title="", sort_order=t_idx)
                session.add(topic)
            topic.title = derive_title(t_slug)
            topic.sort_order = t_idx
            counts["topics"] += 1

        for proj in p.get("projects") or []:
            if isinstance(proj, str):
                proj = {"slug": proj}
            row = await session.scalar(
                select(Project).where(Project.phase_id == phase.id, Project.slug == proj["slug"])
            )
            if row is None:
                row = Project(phase_id=phase.id, slug=proj["slug"], title="")
                session.add(row)
            row.title = proj.get("title") or derive_title(proj["slug"])
            row.brief_md = proj.get("brief")
            counts["projects"] += 1

    await session.commit()
    return counts


async def main() -> None:
    from app.db.session import SessionLocal, init_db

    Path("data").mkdir(exist_ok=True)
    await init_db()
    roadmap = load_roadmap(Path("content/roadmap.yaml"))
    async with SessionLocal() as session:
        counts = await seed(session, roadmap)
    print(f"Seeded (processed): {counts}")


if __name__ == "__main__":
    asyncio.run(main())
