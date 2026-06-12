---
title: AI Mentor Bot
emoji: 🤖
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# AI Mentor Bot 🤖🎓

A personal AI mentor on Telegram that teaches Ayush a structured roadmap — Python fundamentals → FastAPI → ML → ANN/RNN/LSTM → Transformers → LLMs → Agents → LangChain → LangGraph — with daily lessons, active recall, spaced repetition, adaptive difficulty, and project coaching.

**Status:** `DESIGN_COMPLETE — AWAITING APPROVAL` (no code yet, by design)

## If you are an AI assistant resuming work

**Read [SESSION_STATE.md](SESSION_STATE.md) first.** It contains the resume protocol, decisions made, build tracker, and the exact next task. Do not re-derive the design.

## Documents

| File | Purpose |
|---|---|
| [SESSION_STATE.md](SESSION_STATE.md) | Session continuity + build tracker (source of truth for progress) |
| [docs/01_PRODUCT_SPEC.md](docs/01_PRODUCT_SPEC.md) | Product specification — features, UX flows, learning methodology rules |
| [docs/02_ENGINEERING_DESIGN.md](docs/02_ENGINEERING_DESIGN.md) | Architecture, multi-agent framework, DB schema, prompt architecture, deployment |
| [docs/03_DEVELOPMENT_PLAN.md](docs/03_DEVELOPMENT_PLAN.md) | Milestones, task breakdown, estimates, priorities, risks |
| [content/roadmap.yaml](content/roadmap.yaml) | Curriculum seed data (phases → topics → projects) |

## Stack (decided — see Decisions log in SESSION_STATE.md)

Python 3.12 · python-telegram-bot v21 · FastAPI · SQLAlchemy 2 async + SQLite→Postgres · Alembic · APScheduler · LangGraph + Gemini free tier (tiered model routing, Groq fallback) · Docker · GitHub Actions
