# Usage

## Main Endpoints

- `GET /health`
- `GET /ready`
- `POST /telegram/webhook`
- `POST /telegram/send`
- `POST /tutor/message`
- `POST /internal/triggers/{type}`
- `GET /internal/status`

## Telegram Commands

- `/goals`
- `/log`
- `/logs`
- `/ask`
- `/status`
- `/next`
- `/menu`
- `/help`

## Internal Triggers

These routes require the internal trigger secret header.

- `morning-checkin`
- `github-sync`
- `leetcode-sync`
- `evening-reflection`
- `weekly-review`
- `memory-compaction`

Each trigger call should include a unique `request_id` so retries stay idempotent.
