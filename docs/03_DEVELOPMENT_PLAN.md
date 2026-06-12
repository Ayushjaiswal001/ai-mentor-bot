# 03 — Development Plan: AI Mentor Bot

Estimates assume Ayush + AI pair-programming, ~1.5–2 h/day alongside Sem 4. Checkbox state lives in `SESSION_STATE.md` (this file is the reference plan; that file is the live tracker).

## 1. MVP definition

**MVP = M0 + M1:** a bot you can actually learn from today — `/start` onboarding, `/learn` generates and delivers a real lesson for Phase 1 Topic 1, inline 5-MCQ quiz with scoring and the adaptive rule, `/progress`, `/roadmap`, SQLite persistence, polling mode, $0 LLM usage. No scheduler, no SRS, no agents graph yet.

Rationale: the teaching loop is the product. Everything else multiplies its value but only if the loop is good.

## 2. Milestones

### M0 — Scaffold · **4–6 h · P0**
Repo, pyproject (uv), ruff, pydantic-settings config, SQLAlchemy models + Alembic migration, `seed.py` for `content/roadmap.yaml`, pytest skeleton, CI (lint+test).
**Accept:** `seed` populates phases/topics/projects; `pytest` green in CI.

### M1 — MVP teaching loop · **12–16 h · P0**
| Task | Est |
|---|---|
| Bot bootstrap (ptb v21 polling), allowlist + error middleware | 2 h |
| `/start` onboarding conversation → users/user_state | 2 h |
| LLM Router (tiers, fallback, schema-validate+retry, budget guard) | 3 h |
| Lesson prompt + `LessonSchema` + learning engine + chunked delivery | 3 h |
| Quiz engine + inline keyboards + adaptive rule + question bank write | 3 h |
| `/learn` `/quiz` `/progress` `/roadmap` `/help` handlers | 2 h |
| Manual E2E in real chat; fix round | 1 h |

**Accept:** full learn→checkpoint→quiz→advance loop works in Telegram; <50% score visibly produces a simplified repeat next time.

### M2 — Memory & schedule · **10–14 h · P0**
APScheduler + jobstore; `daily_lesson`, `revision_scan`, `streak_nudge` jobs (idempotent); `/today`; streak+XP; `review_items` + SRS ladder + `/revision`; weak-topic capture from wrong answers.
**Accept:** bot messages proactively at the set hour; ladder promote/demote verified with simulated dates in tests.

### M3 — Adaptive depth & exercises · **8–12 h · P1**
Simplified/advanced lesson variants (cached separately); `/exercise` issue→submit→T2 rubric feedback; Socratic hint ladder on wrong answers; free-text mentor chat with daily cap.
**Accept:** a deliberately bad submission gets specific, kind, actionable feedback; hint ladder never gives the answer first.

### M4 — Projects & weekly assessment · **8–10 h · P1**
Project coach (plan_json once via T2, step-at-a-time guidance, step review); Sunday assessment job (6 MCQ + 2 theory rubric-graded + 1 coding) + report card stored in `assessments`.
**Accept:** Phase-1 Calculator project runs end-to-end as a coached, multi-day flow; Sunday produces a real report card.

### M5 — Multi-agent upgrade (LangGraph) · **10–14 h · P2**
Wire existing nodes into the supervisor graph; writer→critic revise loop (max 2); prompt versioning logged; 10-task golden eval set in CI; compare lesson quality pre/post on the golden set.
**Accept:** all features behave identically or better; critic measurably catches schema/length/checkpoint violations.

### M6 — Ship & harden · **6–8 h · P2**
Dockerfile + compose; deploy to chosen host; sqlite backup job; full CI/CD (tag → GHCR → deploy); README runbook (start/stop/logs/backup/restore).
**Accept:** bot survives host reboot unattended; backup restore drill done once.

### Later — P3 backlog
Postgres migration (3–4 h) · Redis jobstore/cache · webhook mode behind Cloudflare Tunnel · placement quiz · `/settings` extras.

## 3. Timeline & priority order

```
M0 → M1 → M2  (P0, ~26–36 h ≈ weeks 1–3)   ← bot is genuinely useful here
→ M3 → M4    (P1, ~16–22 h ≈ weeks 4–5)
→ M5 → M6    (P2, ~16–22 h ≈ weeks 6–7)
Total ≈ 58–80 h ≈ 6–8 weeks part-time
```

Ayush starts **learning from the bot at end of M1** (~week 2) and keeps learning while later milestones land — the bot teaches Python while its own LangChain/LangGraph layers are being built. By Phase 10–11 of the curriculum, he'll be reading this codebase as course material.

## 4. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Free-tier rate limits / model retirement | Med | Router fallback chain; caps; config-only model names; question-bank/cache degrade mode |
| LLM returns invalid JSON | Med | Pydantic validation + 2 feedback retries; bank/cache fallback; it's handled, not hoped away |
| MarkdownV2 escaping bugs | High | Single formatting choke point + unit tests (notorious ptb pain) |
| Scope creep (it's a fun project) | High | Milestone gates; SESSION_STATE.md tracker; "Later P3" list exists precisely for this |
| Sem-4 workload stalls the build | Med | Each milestone leaves a working bot; M1 alone is already valuable |
| Windows dev friction (async, paths) | Low | Plain asyncio works fine; Docker for prod parity |

## 5. Future improvements (post-v1)

Rendered diagrams (mermaid.ink/QuickChart) · voice lessons (TTS) · web dashboard (FastAPI + React, reuses engines) · GitHub integration (verify project commits, auto-detect homework done) · RAG over Ayush's own notes (TurboVec dogfood) · Notion progress sync · multi-user mode + placement onboarding · interview-prep mode feeding off the capstone.
