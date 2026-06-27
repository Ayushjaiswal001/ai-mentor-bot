# Contributing to PathwayAI

Thanks for considering a contribution. PathwayAI is a Telegram-driven
interview-readiness mentor backend; the code lives in `src/pathwayai_backend/`
and tests in `tests/`.

## Quick start

You need Python 3.12, [uv](https://docs.astral.sh/uv/), and Docker (for the
local Postgres + pgvector container).

```bash
# 1. install Python deps (locked)
uv sync --locked --dev

# 2. start Postgres with pgvector preinstalled
docker compose up -d

# 3. copy the env template and edit it
cp .env.example .env
# at minimum: DATABASE_URL=postgresql://pathwayai:pathwayai@127.0.0.1:5432/pathwayai

# 4. apply migrations
uv run alembic upgrade head

# 5. run the API
uv run pathwayai-backend
```

Telegram, Groq, Hugging Face, GitHub, LeetCode, SMTP, and Google Calendar
are all optional — leave the relevant env vars blank and the workflow that
needs them will skip or use a deterministic fallback. See
[docs/configuration.md](docs/configuration.md) for the full env reference.

## Running tests

```bash
uv run pytest          # unit + handler tests (no external services)
uv run ruff check      # lint
uv run ruff format     # auto-format
```

The integration test in `tests/test_database_integration.py` is skipped
unless `TEST_DATABASE_URL` is set. To run it locally:

```bash
TEST_DATABASE_URL=postgresql://pathwayai:pathwayai@127.0.0.1:5432/pathwayai \
  uv run pytest -m integration
```

## Pull request expectations

- One logical change per PR. Pure refactors are fine but please flag them
  in the description.
- Tests for new code. If a bug fix lands, add a regression test that
  fails on `main` and passes on your branch.
- Ruff stays green. CI runs `ruff check` + `pytest` against
  `pgvector/pgvector:pg17`.
- New env vars go in `.env.example`, `docs/configuration.md`, and (if
  user-visible) the README.
- Migrations: one Alembic file per PR, named
  `YYYYMMDD_NNNN_short_description.py`, with a non-destructive `upgrade()`
  and a real `downgrade()`. The `vector` extension is created in
  migration `20260610_0006`; CI uses an image that ships it preinstalled.

## Commit style

Short imperative subject lines ("Add semantic search", "Fix LeetCode
snapshot bug"), no trailing period. Body when it helps reviewers.

## Reporting bugs / suggesting features

Use the GitHub issue templates under
[.github/ISSUE_TEMPLATE/](.github/ISSUE_TEMPLATE/). For security issues
see [SECURITY.md](SECURITY.md) — please don't file public issues for
those.

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md).
By participating, you agree to abide by its terms.
