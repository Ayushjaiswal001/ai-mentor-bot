# Quickstart

## Prerequisites

- Python `3.12+`
- `uv`
- PostgreSQL-compatible database

Optional for the full experience:

- Telegram bot credentials
- Groq and/or Hugging Face API credentials
- GitHub username/token
- LeetCode username

## Install

```bash
cp .env.example .env
uv sync --dev
uv run alembic upgrade head
uv run pathwayai-backend
```

The app starts at `http://127.0.0.1:8000` by default.

OpenAPI docs are available at `http://127.0.0.1:8000/docs`.

## Basic Verification

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
uv run pytest
```
