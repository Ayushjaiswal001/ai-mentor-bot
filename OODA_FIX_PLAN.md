# OODA Fix Plan — AI Mentor Bot (@trainmemybot)

## ✅ CONFIRMED ROOT CAUSE (2026-06-27) — fix this FIRST
**Symptom:** bot silent to all commands. **Evidence:** startup log clean ("bot polling started", `/healthz` 200), but `getUpdates` returns *no-poller* on repeated probes → **the polling task died after startup while uvicorn kept serving `/healthz` 200**, so Render's health check never fails and never restarts the dead poller. In `app/main.py` the updater runs as an unsupervised background task (`app.updater.start_polling()` then `await server.serve()`); if it dies (transient Telegram Conflict / network blip / a second poller on the token), nothing restarts it.

**Fix (Antigravity, cheap model):**
```
1) Make /healthz truthful so Render auto-restarts a dead poller:
   In app/api/health.py the healthz route must return 503 if the bot updater is not running.
   Pass the Application into the health app (app.state) and check `app.updater is not None and app.updater.running`; return {"ok": False} with HTTP 503 otherwise. Render's healthCheckPath will then restart the container when polling dies → self-healing.
2) Guarantee a SINGLE poller on the token: confirm no local `python -m app.main` is running on the PC and Antigravity is NOT running the bot locally while Render is live. Do NOT call getUpdates against the token (it forces a Conflict that can kill the poller).
3) (Hardening) In app/main.py, supervise polling: if app.updater stops, log and exit the process (raise) so Render restarts cleanly, instead of hanging in server.serve() with a dead poller.
Verify: after deploy, send /learn to @trainmemybot from chat (do NOT use getUpdates probes); it must reply. Leave idle 20 min, retry — must still reply.
```
---


Hand to Antigravity. Mechanical fixes — **run it on a cheaper model** (Haiku/Sonnet-class); no deep reasoning needed. Repo: `D:\ai-mentor-bot` (Render + Neon, PTB polling, Gemini+Groq).

## OBSERVE (verified 2026-06-26)
- Bot is **alive**: @trainmemybot polling (getUpdates 409), Render `/healthz` 200, no webhook, 0 pending.
- Last commit `e4df402` already added `pool_pre_ping=True, pool_recycle=300` to `app/db/session.py` (stale-conn fix, deployed).
- Local `.env` has no LLM/DB keys (irrelevant — Render holds the real env).
- Uncommitted junk: `_pathway_ref/`, `count_events.py`.
- **Unknown:** the exact failing symptom/stack trace (needs Render logs).

## ORIENT (most-likely root causes, ranked)
1. **Neon pooled endpoint × asyncpg** — if Render `DATABASE_URL` uses the `-pooler` (PgBouncer) host, asyncpg's prepared-statement cache throws intermittent `prepared statement "__asyncpg_..." already exists` / `another operation is in progress`. Top suspect for random failures.
2. **Idle staleness after Render sleep** — partly fixed (pre_ping+recycle); can still surface as first-query-after-idle errors.
3. **LLM failures** — Gemini free-tier rate limits or stale model id, with **no Groq fallback** if `GROQ_API_KEY` isn't set on Render → all lesson/quiz generation fails.
4. **Render free 750 h/month** — keepalive runs it ~730 h; possible end-of-month suspension + GH-Actions keepalive can lag/auto-disable after repo inactivity.

## DECIDE (fix strategy)
- **DB:** point the app at Neon's **direct** endpoint (drop `-pooler`) — a low-traffic bot doesn't need PgBouncer and this kills cause #1 outright. Keep `pool_pre_ping`+`pool_recycle`, and add asyncpg `connect_args={"statement_cache_size": 0}` as belt-and-suspenders. Wrap engine ops with a 1-retry on `OperationalError/InterfaceError`.
- **LLM:** ensure `GEMINI_API_KEY` + `GROQ_API_KEY` are set on Render; confirm model ids in `app/agents/llm_router.py` are current; router already retries + falls back.
- **Ops:** confirm keepalive workflow is active; remove debug files.

## ACT — Antigravity phases (copy-paste, in order)

### Phase 1 — Confirm the real error (Observe)
```
In D:\ai-mentor-bot: open the Render dashboard logs for service ai-mentor-bot and find the recurring exception (look for asyncpg/SQLAlchemy OperationalError, "prepared statement already exists", "connection closed", or Gemini/LLM 429/4xx). Also message @trainmemybot with /learn and /quiz after it's been idle 20+ min and record any failure. Paste the stack trace here before changing code. Also check Render → service → Environment: is DATABASE_URL the -pooler host? Is GROQ_API_KEY set? Is GEMINI_API_KEY set?
```

### Phase 2 — Harden the DB layer
```
Edit app/db/session.py: build the async engine with pool_pre_ping=True, pool_recycle=300, and connect_args={"statement_cache_size": 0} (asyncpg, PgBouncer-safe). Add a small async retry helper (1 retry on sqlalchemy.exc.OperationalError/InterfaceError/DBAPIError disconnect) and confirm engines/handlers use SessionLocal per-request (no long-lived session across awaits). 
On Render, change DATABASE_URL to the Neon DIRECT endpoint (same string WITHOUT "-pooler"). Keep app/config.py's normalize_db_url (it already strips channel_binding and maps sslmode→ssl). Run `.venv\Scripts\python -m pytest -q` and `ruff check .`; both must pass. Commit + push (Render auto-deploys).
```

### Phase 3 — LLM resilience
```
Verify Render env has GEMINI_API_KEY and GROQ_API_KEY (get a free Groq key at console.groq.com if missing — enables fallback in app/agents/llm_router.py). Confirm LLM_T0/T1/T2 model ids are still valid Gemini models. After deploy, message @trainmemybot /learn end-to-end and confirm a lesson generates (proves DB + LLM path).
```

### Phase 4 — Verify + clean up
```
Add _pathway_ref/ and count_events.py to .gitignore (or delete count_events.py). Confirm the keepalive GitHub Action is enabled and green (Render free sleeps; it must ping /healthz). Final checks: getUpdates returns 409 (polling), GET https://ai-mentor-bot-ztj4.onrender.com/healthz returns 200, and a full /learn → quiz works from Telegram. Commit + push.
```

## VERIFY
- `pytest` green, `ruff` clean.
- After idle, first `/learn` and `/quiz` succeed (no DB/LLM error) — repeat 3×.
- `getUpdates` 409 + `/healthz` 200 stable; keepalive green.

## NOTES
- One token, one instance — don't run a second poller on @trainmemybot's token while Render is live.
- If logs (Phase 1) show a different root cause, fix THAT first; Phases 2–3 are the high-probability defaults, not a guess to apply blindly.
