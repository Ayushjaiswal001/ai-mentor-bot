# 01 — Product Specification: AI Mentor Bot

## 1. Vision

A Telegram bot that behaves like a dedicated personal teacher — not a chatbot. It proactively teaches Ayush (CSE 2nd year, Sem 4) a structured path from Python fundamentals to LangGraph multi-agent systems, tracks everything, and adapts to his performance. End goal: internship-ready AI engineering skill + a portfolio (the bot itself is portfolio piece #1).

**One user initially (Ayush).** Designed so multi-user is a config change, not a rewrite.

## 2. Core experience loops

### 2.1 Daily lesson loop (the heartbeat) — on-demand & resumable
1. Lessons are **on-demand**: Ayush sends `/learn` whenever he wants to study. An optional daily **reminder** (default 20:00 IST, change/disable via `/settings`) nudges: *"📅 Today: Lesson — «Dictionaries» · 2 reviews due · 🔥 streak 6"* with buttons `[Start Lesson] [Reviews first] [Not today]`.
2. `/learn` delivers the lesson (format in §4) chunk by chunk. **A lesson can be stopped mid-way and resumed any time** — the bot stores a progress pointer; the next `/learn` (even days later) resumes at the exact section with a one-line recap.
3. Lesson ends with a 5-question quiz → adaptive rule (§5.3) decides the next lesson's content.
4. Homework is issued; completing the quiz marks the day done and increments the streak (any completed activity that day counts).

### 2.2 Revision loop (spaced repetition)
- Each completed topic becomes a review item on the ladder **[1, 3, 7, 14, 30] days**.
- `/revision` (or the daily push when items are due) runs 3 questions per due topic, sampled from the topic's question bank.
- ≥2/3 correct → promote one rung. <2/3 → demote one rung (min: 1 day), mark topic weak.
- After rung 30 passes, the topic is "retired" (resurfaces only in weekly assessments).

### 2.3 Weekly assessment (Sunday)
- Scope: all topics completed in the last 7 days + the 2 weakest topics overall.
- Format: 6 MCQs + 2 theory questions (free text, LLM rubric-graded) + 1 coding problem.
- Output: a report card — per-topic scores, trend vs last week, 2 concrete focus recommendations. Stored for `/progress` history.

### 2.4 Project coaching loop
- When a phase's topics are done, the bot proposes the phase project(s).
- Project coach breaks the project into 5–10 steps (stored plan), issues one step at a time, reviews submitted code/descriptions against the step's goal, and unlocks the next step.
- Capstone (AI Interview Assistant) works the same way — **the bot coaches the build; the assistant is Ayush's own repo**, not a bot feature.

### 2.5 Socratic free-text mode
- Any non-command text is treated as a question to the mentor about the current/recent topic.
- The mentor answers Socratically with a **hint ladder**: nudge → concept reminder → partial step → full explanation. It never jumps to the full answer first.
- Capped (default 15 free-text exchanges/day) to protect the free LLM tier.

## 3. Commands

| Command | Behavior |
|---|---|
| `/start` | Onboarding: name, timezone, daily hour; offer placement quiz (skip-ahead) or start Phase 1 |
| `/today` | Today's plan: lesson due, reviews due, homework status, streak |
| `/learn` | Start/continue today's lesson |
| `/quiz` | Quiz on the current (or last completed) topic |
| `/revision` | Run due spaced-repetition reviews |
| `/exercise` | Coding exercise for current topic; accepts a code submission, returns rubric feedback |
| `/project` | Project coach: propose/continue current phase project |
| `/progress` | Stats: phase/topic position, quiz averages, weak topics, streak, XP, weekly trend |
| `/roadmap` | Phase map with ✅ done / ▶️ current / 🔒 locked, % complete |
| `/settings` | Change daily hour, timezone, difficulty preference; reset options |
| `/help` | Command reference + how the methodology works |

## 4. Lesson format & Telegram UX

Every lesson is generated against a fixed schema (validated, §02-design):

1. 🎯 **Learning objective** (1–2 lines)
2. **Concept explanation** (short, concrete, beginner-calibrated)
3. **Real-world example** (tied to Ayush's context: student apps, APIs, AI tools)
4. **Diagram suggestion** (described in text v1; rendered image v2)
5. **Code example** (runnable, ≤25 lines, with expected output)
6. ❓ **2–3 interactive checkpoint questions** (active recall — inline buttons or short text; answered before the summary is shown)
7. **Summary** (3–5 bullets)
8. **Quiz** (5 MCQs, inline keyboards, instant per-question feedback + explanation)
9. 📝 **Homework** (one small task, checked next day via self-report button + spot question)

**Telegram constraints handled by design:** messages chunked at ≤3,500 chars with `[Continue ▸]` buttons; MarkdownV2 escaping centralized; quiz answers via callback buttons (`q:{attempt}:{idx}:{choice}`), never free text. Target lesson time: 10–20 minutes.

## 5. Learning methodology — exact rules

### 5.1 Active recall
Checkpoint questions interrupt every lesson (§4.6). Wrong checkpoint answers trigger a one-line Socratic hint, then re-ask once, then explain.

### 5.2 Spaced repetition
Ladder [1, 3, 7, 14, 30] days as in §2.2. Review questions come from the stored question bank first (token-free), LLM-generated only when the bank is thin.

### 5.3 Adaptive difficulty (quiz-driven)
| Lesson quiz score | Action |
|---|---|
| ≥ 80% | Topic complete → advance. Review item created (due +1d). |
| 50–79% | Topic complete but **flagged**: extra homework, recap section prepended to next lesson, review at +1d. |
| < 50% | Topic repeats tomorrow as a **simplified variant** (more analogies, smaller steps). Topic marked weak. Max 2 repeats, then mentor schedules a free-text walkthrough session. |

A user-level difficulty setting (`simpler/normal/harder`) also shifts lesson tone, derived from a rolling 5-quiz average (auto) or `/settings` (manual).

### 5.4 Socratic teaching
Hint ladder everywhere an answer is wrong or help is requested (§2.5). The mentor asks before it tells.

### 5.5 Project-based learning
Every phase ends with project(s) (`content/roadmap.yaml`); exercises (`/exercise`) appear every ~3 topics automatically as homework.

## 6. Progress tracking (stored, surfaced via /progress)

Current phase & topic · completed lessons · all quiz scores + rolling averages · weak topics (with cause: quiz/revision/checkpoint) · revision ladder state per topic · project step progress · daily streak (current + longest) · XP (lesson 10, quiz 5 + score bonus, revision 5, exercise 15, project step 20) · weekly assessment history.

## 7. Gamification (light)

Streaks with 🔥 emoji in daily pushes; XP + levels (cosmetic); phase-completion "certificates" (a formatted summary message). A missed day breaks the streak at the daily nudge (21:30 reminder fires first). No leaderboards in v1 (single user).

## 8. Non-goals (v1)

Multi-user onboarding/marketing · voice or video lessons · rendered diagram images · payments · web dashboard · group chats. (All listed in Future Improvements.)

## 9. Success metrics

- **Consistency:** streak length distribution; ≥5 active days/week.
- **Learning:** rolling quiz average trending ≥75%; weak-topic count not growing week over week.
- **Velocity:** Phase 1 done in ~3 weeks; full roadmap (incl. projects) ≈ 5–6 months at 1 topic/day.
- **Outcome:** weekly assessment scores improve over a 4-week window; capstone shipped.
