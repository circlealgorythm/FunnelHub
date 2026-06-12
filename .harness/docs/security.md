# Security Notes

Use this file for changes touching auth, secrets, webhooks, external APIs, uploads, public routes,
deployment scripts, or user data.

## Secrets

- Do not commit tokens, passwords, SSH credentials, API keys, webhook secrets, private URLs with
  embedded credentials, or production database dumps.
- Keep production secrets in environment variables or deployment-only `.env` files.
- Do not print secrets in terminal output, logs, test failures, or Harness docs.
- When a tracked file previously contained a secret, rotate the secret; removing it from git is not
  enough.

## Webhooks and Public Endpoints

- Prefer signed or secret-protected webhooks.
- Validate provider signatures/secrets before mutating state.
- Keep idempotency keys for repeated provider events.
- Strip transport secrets from persisted raw payloads.
- Avoid query-string secrets when access logs may capture URLs.

## User Data

- Store only data needed for communication, attribution, consent, and support.
- Treat email, phone, messenger IDs, GetCourse IDs, UTM payloads, and message history as sensitive.
- Production smoke data must be cleaned up unless the test intentionally verifies a real lead flow.

## File and Path Safety

- Resolve public/static file paths under the intended root before serving.
- Reject path traversal and never serve repository or environment files through SPA fallbacks.
- Validate uploaded CSV/XLSX type and parse through structured libraries.

## External Messaging

- Respect unsubscribe and provider bounce/complaint states.
- Do not send Telegram/VK messages unless an active subscribed messenger identity exists.
- For mass sends, keep per-recipient history and duplicate protection.

