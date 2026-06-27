# Security Policy

## Reporting a vulnerability

**Please do not file public GitHub issues for security problems.**

If you've found a vulnerability — credential leakage, prompt-injection
bypass, auth bypass, SQL/command injection, an unsafe webhook handler,
anything that could expose user data or take over the bot — report it
privately via GitHub's
[Security Advisories](https://github.com/ayush-projects/PathwayAI/security/advisories/new)
tab. If that's not available to you, email the maintainer directly (see
`pyproject.toml`).

Please include:

- A clear description of the issue and its impact.
- Steps to reproduce, or a proof-of-concept.
- Affected versions or commits.
- Any suggested fix, if you have one.

You'll get an acknowledgement within 72 hours and a status update within
seven days. Confirmed vulnerabilities are disclosed via GitHub Security
Advisories once a fix is available.

## Scope

In scope:

- The backend service (`src/pathwayai_backend/`)
- Migrations (`migrations/`)
- The Telegram webhook handler and signed-secret check
- The admin endpoints (`/admin/*`) and internal trigger endpoints

Out of scope:

- Vulnerabilities in third-party services (Telegram, Groq, Hugging Face,
  Neon, GitHub Actions, SMTP providers). Report those upstream.
- Self-hosted misconfiguration (running with `INTERNAL_TRIGGER_SECRET`
  unchanged, exposing `/admin/*` publicly without a reverse-proxy
  allowlist, etc.) — please open a docs issue instead.

## Supported versions

The `main` branch is the only supported version. Backports to older
tagged releases are best-effort.
