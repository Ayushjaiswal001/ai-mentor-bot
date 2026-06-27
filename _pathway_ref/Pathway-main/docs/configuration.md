# Configuration

PathwayAI reads configuration from environment variables and `.env`.

## Minimum Local Setup

```env
DATABASE_URL=
INTERNAL_TRIGGER_SECRET=
```

## Telegram

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_WEBHOOK_SECRET=
APP_BASE_URL=
```

Telegram features are enabled only when the bot token and chat ID are configured.

## Model Providers

```env
GROQ_API_KEY=
HUGGINGFACE_API_TOKEN=
```

If neither provider is configured, some workflows use deterministic fallback responses.

## GitHub Activity

```env
GITHUB_USERNAME=
GITHUB_TOKEN=
```

## LeetCode Activity

```env
LEETCODE_USERNAME=
LEETCODE_SESSION=
LEETCODE_CSRF_TOKEN=
```

`LEETCODE_USERNAME` is the main requirement in this repository. Session and CSRF values are optional.

## Weekly Digest Email

```env
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
DIGEST_EMAIL_FROM=
DIGEST_EMAIL_TO=
```

The digest is off unless `SMTP_HOST` and `DIGEST_EMAIL_TO` are both set. Port
465 uses implicit TLS; any other port uses STARTTLS. `DIGEST_EMAIL_FROM` falls
back to `SMTP_USERNAME` when unset. The `weekly-digest` GitHub Actions workflow
calls `POST /admin/weekly-digest` every Monday morning, which mails the same
markdown bundle as `/export week`.

## Database Notes

- Use a non-production database for local development.
- If you use a separate migration connection string, set `MIGRATION_DATABASE_URL`.
- Run Alembic before starting the app after schema changes.
