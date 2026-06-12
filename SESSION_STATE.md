# SESSION_STATE.md — Continuity & Build Tracker

> **Resume protocol (for any AI session, any model):**
> 1. Read THIS file fully. It is the single source of truth for "where are we".
> 2. Do NOT re-read all docs. Read only the doc section relevant to the next unchecked task (pointers below).
> 3. Do the next unchecked task in **Build Tracker**. Small, complete increments only.
> 4. Before ending the session (or when context feels ~70% consumed): update **Status**, check off tasks, append to **Decisions** if any were made, and add anything surprising to **Notes**.
> 5. Never rewrite history in this file — append.

---

## Status

- **Phase:** `M1 CODE COMPLETE ✅ — bot RUNNING locally, awaiting Ayush's live E2E test`
- **Last updated:** 2026-06-12 (Session 1 cont. — M1 built: 16/16 tests pass, ruff clean, bot started in polling mode, "Application started" confirmed. All 4 .env keys filled incl. Groq fallback.)
- **Next action:** Ayush tests in Telegram (/start → /learn → checkpoints → quiz → /progress /roadmap). Record results + bugs here, then M2 (scheduler, /today, streak jobs, /revision SRS).
- **Dev commands:** run bot: double-click `run_bot.bat` (or `.venv\Scripts\python -m app.main`; Ctrl+C stops; only ONE instance at a time — two cause a Telegram getUpdates conflict) · test: `.venv\Scripts\python -m pytest -q` · lint: `.venv\Scripts\ruff check .` · migrate: `.venv\Scripts\alembic upgrade head` · seed: `.venv\Scripts\python -m app.scripts.seed`

## Document map (read only what you need)

| Need | Read |
|---|---|
| What the product does, UX, learning rules | `docs/01_PRODUCT_SPEC.md` |
| Architecture, agents, DB schema, prompts, deploy | `docs/02_ENGINEERING_DESIGN.md` |
| Task order, estimates, milestone acceptance criteria | `docs/03_DEVELOPMENT_PLAN.md` |
| Curriculum seed data | `content/roadmap.yaml` |

## Token-saving protocol for build sessions

1. **Model tiering for the build itself:** boilerplate/CRUD/test scaffolding → delegate to a **Haiku** subagent (`Agent` tool, `model: "haiku"`); architecture decisions, agent prompts, tricky async code → main model. One module per delegation, with the relevant design-doc excerpt pasted into the subagent prompt (subagents start cold).
2. Generate code **module by module** in the milestone order below. Never regenerate a finished module; edit it.
3. Don't paste whole docs into context — `SESSION_STATE.md` + one doc section is enough.
4. The bot's own runtime token strategy (LLM router tiers, caching, caps) is in `docs/02_ENGINEERING_DESIGN.md §5` — it is a product feature, separate from this build protocol.

## Build Tracker (mirror of docs/03_DEVELOPMENT_PLAN.md — check off here)

### M0 — Scaffold (P0) ✅ 2026-06-12
- [x] Repo init (git), `pyproject.toml` (pip/setuptools), ruff config, `.env.example`, `.gitignore`
- [x] `app/config.py` (pydantic-settings)
- [x] SQLAlchemy models (14 tables) + Alembic init + migration `7fc1fa8a1239` applied
- [x] `app/scripts/seed.py` — idempotent upsert; verified counts 12/75/10
- [x] pytest skeleton (3 passing) + CI workflow `.github/workflows/ci.yml`
- [ ] *(deferred to Ayush)* first git commit + GitHub repo creation

### M1 — MVP teaching loop (P0) — code ✅ 2026-06-12
- [x] Bot bootstrap (ptb v21 polling), error middleware + Event logging, allowlist gatekeeper
- [x] `/start` onboarding (reminder-hour picker; tz defaults Asia/Kolkata) → users + user_state
- [x] LLM router `app/agents/llm_router.py` (t0/t1/t2, Gemini REST primary, Groq fallback, schema-validate + 1 retry w/ error feedback, daily budget caps, llm_usage events)
- [x] Lesson: schema + Jinja2 prompts + engine (cache per topic+variant, resume via progress_idx) + HTML chunked delivery + checkpoint Qs w/ hint ladder (1 hint, then explain)
- [x] `/learn` (generate → deliver → checkpoints → summary → homework → quiz CTA)
- [x] Quiz engine: 5 MCQ inline quiz, idempotent answers, adaptive rule (≥80 advance / 50–79 flag / <50 repeat simplified), question bank persisted, review item on pass
- [x] `/quiz`, `/progress`, `/roadmap`, `/help`, free-text stub
- [x] 16/16 unit tests green (FakeLLM); bot launches, "Application started"
- [ ] E2E manual test in real Telegram chat by Ayush → record results here

### M2 — Memory & schedule (P0)
- [ ] APScheduler + SQLAlchemy jobstore; jobs: daily_lesson, revision_scan, streak_nudge
- [ ] `/today`; streaks + XP in progress engine
- [ ] review_items + SRS ladder [1,3,7,14,30] + `/revision` flow
- [ ] Weak-topic tracking from quiz answers

### M3 — Adaptive & exercises (P1)
- [ ] simplified/advanced lesson variants
- [ ] `/exercise` + submission + T2 rubric feedback
- [ ] Socratic hint ladder; free-text mentor chat (daily cap)

### M4 — Projects & weekly assessment (P1)
- [ ] Project coach engine (`plan_json` steps, check-ins), `/project`
- [ ] Sunday weekly assessment job + report card

### M5 — Multi-agent upgrade (P2)
- [ ] LangGraph supervisor graph replaces direct calls (same engine interfaces)
- [ ] writer→critic loop, prompt versioning, 10-task golden eval set

### M6 — Ship & harden (P2)
- [ ] Dockerfile + compose; deploy to chosen host; sqlite backup job
- [ ] Full CI/CD (build, push GHCR, deploy step); runbook in README

### Later (P3)
- [ ] Postgres migration · Redis jobstore/cache · webhook mode

## Decisions log (ADR-lite — append only)

| # | Decision | Why |
|---|---|---|
| 1 | `python-telegram-bot` v21 (async) over aiogram | Best docs/community for a learner-maintained bot; v21 is fully async |
| 2 | Gemini free tier primary; Groq (llama-3.3-70b) fallback; OpenAI optional | $0 cost for a student; router makes providers swappable |
| 3 | SQLite + SQLAlchemy 2 async + Alembic now; Postgres later via same ORM | Zero-ops start; migration is a URL change + alembic upgrade |
| 4 | APScheduler (sqlalchemy jobstore) over Celery/Redis | No broker needed at single-user scale; Redis optional later |
| 5 | Long polling for dev AND prod v1; webhook only if/when hosted multi-user | Single user → polling is simpler, needs no public HTTPS |
| 6 | LangGraph multi-agent introduced at M5, but engine/agent **interfaces** designed for it from M0 | Ship value first; refactor risk contained by stable interfaces; dogfoods Ayush's own curriculum |
| 7 | Commands give explicit intent → supervisor is deterministic code for commands; LLM routing only for free text | Big token saving; less latency |
| 8 | Lessons cached per (topic, variant); quiz question bank reused for revision | Major token saving on the free tier |
| 9 | "AI Interview Assistant" final project = curriculum content the bot COACHES Ayush to build, not a bot feature | Keeps bot scope sane; matches learning goal |
| 10 | Lessons are ON-DEMAND and RESUMABLE (`progress_idx` per lesson, `active_lesson_id` in user_state); fixed daily delivery replaced by optional reminder (default 20:00 IST, change/off via /settings) | Ayush wants flexible timing + pause/resume |
| 11 | Hosting: Ayush's PC during M0–M5 (fine — lessons on-demand); M6 deploy = Hugging Face Spaces Docker (free, NO credit card) + Neon Postgres free tier (HF disk is ephemeral) + UptimeRobot ping vs 48h sleep. Oracle/Fly ruled out (card issue) | No-credit-card constraint; PC not always on |
| 12 | Start at Phase 1 Topic 1; placement quiz → Later/P3 backlog | Ayush's choice |
| 13 | python-telegram-bot v21 confirmed; Gemini API key available; Groq fallback key optional/later | Ayush approved |

## Open questions for Ayush

*(none — all five answered 2026-06-12 and folded into Decisions #10–13)*

## Notes / surprises

- **Py3.12 + ptb v21 gotcha:** `asyncio.run(init_db())` before `run_polling()` crashes (`no current event loop`) — fixed by moving `init_db()` into the app's `post_init` hook. Don't reintroduce.
- LLM calls are plain REST via httpx (no Gemini/Groq SDKs) — provider swap = .env change.
- Telegram output is HTML parse mode via `app/bot/formatting.py` (md→html, the ONLY allowed path out). MarkdownV2 deliberately avoided.
- Repo layer from design §9 skipped for M1 (engines query directly) — revisit only if it hurts.
- Python 3.12.7 + git 2.46 present on Ayush's PC; venv at `.venv/` works fine.
- `uv` not assumed — plain pip + setuptools used; pyproject is PEP 621 so uv works later if wanted.
- Alembic uses async env.py reading `DATABASE_URL` from app settings; `alembic/` excluded from ruff.
- Dev DB `data/mentor.db` exists, migrated + seeded. `data/` is gitignored.
- M1 deps still to add when needed: `python-telegram-bot~=21.0`, `fastapi`, `uvicorn`, `apscheduler`, `google-genai`, `jinja2`.
