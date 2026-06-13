# SESSION_STATE.md — Continuity & Build Tracker

> **Resume protocol (for any AI session, any model):**
> 1. Read THIS file fully. It is the single source of truth for "where are we".
> 2. Do NOT re-read all docs. Read only the doc section relevant to the next unchecked task (pointers below).
> 3. Do the next unchecked task in **Build Tracker**. Small, complete increments only.
> 4. Before ending the session (or when context feels ~70% consumed): update **Status**, check off tasks, append to **Decisions** if any were made, and add anything surprising to **Notes**.
> 5. Never rewrite history in this file — append.

---

## Status

- **Phase:** `M3 CODE COMPLETE ✅ — deploying to Render. Bot LIVE on Render. Next: M4 (projects + weekly assessment)`
- **Last updated:** 2026-06-13 (Session 1 cont. — M3 built: /exercise AI-graded, Socratic free-text mentor, /settings, lesson variants. 30/30 tests. Pushing to GitHub→Render.)
- **Next action:** confirm Render redeploy polling (409 probe) + healthz; Ayush live-tests /exercise + free-text chat + /settings. Then M4: project coach (plan→steps→review) + Sunday weekly assessment + report card.
- **Deploy:** `git push origin main` → GitHub `Ayushjaiswal001/ai-mentor-bot` → **Render auto-deploys** (~3-5 min). Render URL https://ai-mentor-bot-ztj4.onrender.com. Bot @trainmemybot. Neon Postgres (Singapore). Keep-alive = GitHub Actions `keepalive.yml` every 10 min.
- **⚠️ Run rules:** the CLOUD bot is now the live instance. Do NOT run `run_bot.bat` locally while the Space is running (two pollers fight over getUpdates). For local dev: pause the Space (Settings → Pause) first. Local `.env` now points at Neon too — local runs share the same cloud DB (no split progress).
- **Dev commands:** test: `.venv\Scripts\python -m pytest -q` · lint: `.venv\Scripts\ruff check .` · seed: `.venv\Scripts\python -m app.scripts.seed` · deploy: `git push --force https://Ayushjaiswal001:<HF_TOKEN>@huggingface.co/spaces/Ayushjaiswal001/ai-mentor-bot main` · secrets: `.venv\Scripts\python -m app.scripts.set_space_secrets Ayushjaiswal001/ai-mentor-bot <HF_TOKEN>` · test: `.venv\Scripts\python -m pytest -q` · lint: `.venv\Scripts\ruff check .` · migrate: `.venv\Scripts\alembic upgrade head` · seed: `.venv\Scripts\python -m app.scripts.seed`

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
- [x] E2E manual test in real Telegram chat by Ayush → **"test successful"** 2026-06-12 (cloud bot, Neon DB)

### M2 — Memory & schedule (P0) — code ✅ 2026-06-12
- [x] Scheduling via PTB **JobQueue** (not standalone APScheduler+jobstore — see Decision #17): `heartbeat` every 30 min → per-user daily reminder at `reminder_hour` + evening streak nudge at 21:00 local; idempotent via `job_marker` events; tz-aware (zoneinfo + tzdata dep)
- [x] `/today` (+ shared `today_view` reused by the reminder job); streaks + XP already in progress engine
- [x] review_items + SRS ladder [1,3,7,14,30] (`engines/revision.py`, pure `apply_ladder`) + `/revision` flow (3 Q, bank-first sampling, ≥2/3 = pass→promote / else demote); `nav:revise` button on /today + post-review
- [x] Weak tags captured per quiz attempt (`weak_tags_json`); progress.weak_topics derives from lesson quizzes
- [x] 24/24 tests green (8 new: ladder promote/demote/floor/retire, is_pass, due filtering, bank-reuse-no-LLM, revision finalize promotes); full app import smoke OK
- [ ] Live E2E by Ayush: /today, /revision (after a lesson creates a due item — note: first review is due +1 day, so test by completing a lesson then waiting a day OR temporarily backdating). Reminder fires at chosen hour.

### M3 — Adaptive & exercises (P1) — code ✅ 2026-06-13
- [x] simplified/advanced lesson variants — `pick_variant` now honors `state.difficulty` (harder→advanced, simpler→simplified, plus failed-retake→simplified)
- [x] `/exercise` + submission + **T2** rubric feedback (`engines/exercises.py`; spec+grade stored in Exercise.feedback_json — NO migration); 💡 Hint ladder + ⏭ Skip buttons
- [x] Free-text **Socratic mentor** chat (`engines/mentor.py` + `handlers/chat.py`): any non-command text → graded as exercise submission if one is pending, else Socratic answer; daily cap via FREETEXT_DAILY_CAP (events type "freetext")
- [x] `/settings` (difficulty + reminder hour) ; LLM router gained `generate_text` (json_mode param) for prose
- [x] 30/30 tests (6 new: exercise issue/submit/skip, variant-by-difficulty, mentor answer+cap); app wiring smoke OK
- [ ] Live test by Ayush after deploy: /exercise → submit code → graded; type a question → Socratic reply; /settings → set Harder → next /learn is deeper

### M4 — Projects & weekly assessment (P1)
- [ ] Project coach engine (`plan_json` steps, check-ins), `/project`
- [ ] Sunday weekly assessment job + report card

### M5 — Multi-agent upgrade (P2)
- [ ] LangGraph supervisor graph replaces direct calls (same engine interfaces)
- [ ] writer→critic loop, prompt versioning, 10-task golden eval set

### M6 — Ship & harden (P2) — host part DONE EARLY ✅ 2026-06-12
- [x] Dockerfile (root, HF-compatible, health server on :7860)
- [x] ~~Deploy: HF Space~~ ABANDONED — HF blocks Telegram egress (see CRITICAL FINDING). Migrated to Render.
- [x] Code on GitHub (public) + `render.yaml` blueprint + port-first startup; Neon DB retained
- [x] Ayush deployed on Render via Blueprint (blueprint exs-d8mim0bbc2fs73e1ge9g); secrets set; FIRST getUpdates probe = 409 → **bot IS polling from Render ✅** (Render reaches Telegram, unlike HF). Bot = **@trainmemybot** ("MyAImentor").
- [x] Render URL: **https://ai-mentor-bot-ztj4.onrender.com** — /healthz {"ok":true}, root alive ✅
- [x] Keep-alive: **GitHub Actions `keepalive.yml`** pings /healthz every 10 min (active, first run triggered). NOTE: GH cron can lag + auto-disables after 60 days repo inactivity → OPTIONAL upgrade: cron-job.org monitor on the same URL for tighter timing.
- [x] Ayush live test against @trainmemybot — **confirmed running** 2026-06-12 (Render bot replied; Gemini reachable from Render).
- [ ] Backup story for Neon (free tier has limited point-in-time restore) — revisit at M2 close
- [ ] Full CI/CD (GitHub repo + Action → auto-push to HF); runbook in README

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
| 14 | Hosting deployed EARLY (was M6): HF Space `Ayushjaiswal001/ai-mentor-bot` (Docker SDK, private) + Neon Postgres free (Singapore). Polling mode kept; FastAPI /healthz on :7860 satisfies HF health check + serves as keep-alive ping target | Ayush wanted 24/7 without PC/phone; no credit card on either platform |
| 15 | `config.py` normalizes any Postgres URL (postgres→postgresql+asyncpg, sslmode→ssl, drops channel_binding) — paste raw Neon string anywhere and it works | Beginner-proof config |
| 16 | Secrets pushed via HF API (`app/scripts/set_space_secrets.py`), not the web UI. GROQ_API_KEY turned out EMPTY (earlier filled-check was a false positive from the placeholder comment) — Gemini-only until Ayush adds a Groq key | — |
| 17 | Scheduling = PTB JobQueue (in-process), NOT standalone APScheduler + SQLAlchemy jobstore as design §10 first said. Jobs are code-defined recurring scans re-registered each boot; only durable state is in Postgres; idempotency via `job_marker` events. Simpler, one process, survives HF container restarts. Revisit only at multi-instance scale | Avoids an asyncpg-jobstore complication; PTB JobQueue is the native fit |
| 18 | `/revision` reviews ONE most-due topic per invocation (loops via "Review now (n)" button) rather than batching all due topics into one mega-quiz | Keeps the inline-button quiz machinery reused as-is; better UX in chat |

## Open questions for Ayush

*(none — all five answered 2026-06-12 and folded into Decisions #10–13)*

## ⛔ CRITICAL FINDING (2026-06-12): Hugging Face Spaces CANNOT host this bot

Proven by an in-container network probe (`app/diagnostics.py`):
- `example.com` → 200, `generativelanguage.googleapis.com` (Gemini) → connects in 0.1s → **general egress works**.
- `api.telegram.org` (149.154.166.110) → **ConnectTimeout on BOTH IPv4 and IPv6**.
- ⇒ HF Spaces blocks egress to Telegram's IP range. Polling AND webhook both fail (replies also need outbound to api.telegram.org). **HF is a dead end for any Telegram bot. Do not retry HF.**
- The single-loop + resilient-bootstrap rewrite (commits after 69ca93d) is GOOD and host-agnostic — keep it. The diagnostic call was removed from `amain` (module kept for future host checks).
- The earlier M1 "test successful" was the LOCAL bot (running on Ayush's PC at the time), not the cloud one.

**DECISION MADE (Ayush): Render.** Code now on GitHub: **https://github.com/Ayushjaiswal001/ai-mentor-bot** (public, secrets gitignored). `render.yaml` blueprint committed. `main.py` opens health port first (parallel to bot bootstrap) so Render's health check passes fast. Neon DB unchanged. HF Space can be deleted later.
**PENDING (Ayush, in browser):** sign up render.com w/ GitHub → New+ → Blueprint → pick repo → paste 4 secrets (TELEGRAM_BOT_TOKEN, ALLOWED_TG_USER_IDS, GEMINI_API_KEY, DATABASE_URL; GROQ/OPENAI optional) → deploy. Then cron-job.org ping on `https://<render-url>/healthz` every 10 min (Render free spins down after 15 min idle; Render URL is PUBLIC so no auth header needed — simpler than the old HF/private plan).
**Deploy workflow now:** `git push origin main` → Render auto-deploys (autoDeploy:true). HF push no longer used.

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
