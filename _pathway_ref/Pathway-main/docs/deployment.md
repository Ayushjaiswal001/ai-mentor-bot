# Deployment

## Requirements

Your host should support:

- Python 3.12
- outbound HTTPS
- PostgreSQL connectivity
- a public HTTPS URL for Telegram webhooks

## Typical Flow

1. Provision the database.
2. Set environment variables from `.env.example`.
3. Run migrations:

```bash
uv run alembic upgrade head
```

4. Start the app:

```bash
uv run pathwayai-backend
```

5. Configure the Telegram webhook after the app is publicly reachable:

```bash
uv run pathwayai-set-webhook
```

## GitHub Actions

The repository includes workflows for CI, deploy hooks, scheduled syncs, and recurring mentor triggers.

If you keep those workflows enabled, set the matching GitHub secrets used by your environment.

## Post-Deploy Checks

- `GET /health` returns `200`
- `GET /ready` reports required services correctly
- Telegram webhook setup succeeds
- scheduled trigger calls authenticate successfully
