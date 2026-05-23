# session-handoff.md

## Summary

FunnelHub is being set up as a Harness-engineering project. GetCourse keeps courses/payments/access. FunnelHub owns bots, email, inbox, lead database, imports, broadcasts, and analytics.

## Current Feature

<нет>

## Last Actions

- Created `.harness/` workspace files.
- Moved project agent instructions into `.harness/AGENTS.md`.
- Captured methodology, scope, stack, risks, DoD, and roadmap.
- Created initial FastAPI scaffold under `src/funnelhub`.
- Added `/health`, `tests/test_health.py`, `pyproject.toml`, Dockerfile, Docker Compose, `.env.example`, README, and `.gitignore`.
- Created local Python 3.12 `.venv` and installed dependencies.
- Installed/verified Docker Desktop integration.
- Fixed Docker Compose project naming with `name: funnelhub`.
- Fixed Dockerfile editable install order and added `.dockerignore`.
- Built and started Docker Compose stack: app, PostgreSQL, Redis.
- Verified `/health` via localhost.
- Inspected provided GetCourse export sample. It contains headers only, no user rows. Documented encoding, delimiter, and columns in `.harness/docs/getcourse-export.md`.
- Inspected XLSX export with one user row. Headerless columns 14-21 contain custom field values such as `Да`, so import must preserve them and allow manual mapping to consent fields.
- Added SQLAlchemy core data models, Alembic setup, and migration `0001_core_data_model`.
- Applied migration to local Docker PostgreSQL successfully.
- Documented schema in `.harness/docs/data-model.md`.
- Captured GetCourse webhook.site screenshots were summarized in `.harness/docs/getcourse-webhook.md`: GetCourse sends GET query params, no body/form values, with profile fields, UTM fields, and `custom_<field_id>` parameters.
- Captured GetCourse account fields API raw JSON was summarized in `.harness/docs/getcourse-webhook.md`. Correct checkbox IDs are `10558670`, `10575005`, `10616540`, `10661024`, `10682753`, `10682754`, `10683365`, `11344348`. Earlier screenshot-only read of `10663365/11344349` was corrected by raw JSON.
- Consent meaning from raw JSON: all eight checkbox fields imply personal data + privacy policy consent when checked; all except `10616540` include an offer agreement link. Offer URLs differ per field.
- Implemented `GET/POST /webhooks/getcourse`.
- Added async SQLAlchemy session dependency in `src/funnelhub/db/session.py`.
- Added webhook router in `src/funnelhub/api/webhooks.py`.
- Added ingestion service in `src/funnelhub/services/getcourse_webhook.py`.
- Webhook now creates/updates leads, contacts, GetCourse external IDs, email subscriptions, UTM rows, custom fields, and events.
- Added tests in `tests/test_getcourse_webhook.py`.
- Added semantic consent normalization from mapped GetCourse checkbox custom fields.
- Mapped custom fields with `Да` now create/update `lead_consents`: all mapped fields grant `personal_data` and `privacy_policy`; all except `10616540` also grant `offer_agreement`.
- Added `bot_link_tokens` model/table and migration `0002_bot_link_tokens`.
- GetCourse webhook response now includes `bot_link_token` and `join_url`.
- Added local join page at `GET /join/{token}`.
- Added messenger linking API at `POST /api/messenger/link`.
- Added bot-linking docs in `.harness/docs/bot-linking.md`.
- The provided Telegram bot token was not written to repository files. Real Telegram adapter should use environment config later.
- Added aiogram-based Telegram polling adapter in `src/funnelhub/telegram_bot.py`.
- Added `TELEGRAM_BOT_TOKEN` config/env example; the actual token remains outside repo files.
- Telegram adapter handles `/start <token>` and links the Telegram user through the existing linking service.
- Added Telegram `/status` and `/stop`.
- Added Telegram outbound text sending service in `src/funnelhub/services/telegram_messaging.py`.
- Outbound Telegram sends write to `messages`; `/stop` marks `messenger_identities.is_subscribed=false`.

## Next Recommended Step

Choose the next feature. Recommended next feature: `funnel-engine` once the funnel scenario is available.

## Verification

- `ruff check .` passed via `.venv`.
- `mypy src` passed via `.venv`.
- `pytest -x` passed via `.venv`: 1 test passed.
- `docker --version` passed: Docker 29.4.3.
- `docker compose version` passed: Docker Compose v5.1.3.
- `docker compose config --quiet` passed.
- `docker compose up -d --build` passed.
- `GET http://localhost:8000/health` returned `{\"status\":\"ok\",\"service\":\"FunnelHub\"}`.
- `ruff check .` passed after core data model changes.
- `mypy src` passed after core data model changes.
- `pytest -x` passed after core data model changes: 2 tests passed.
- `docker compose exec -T app alembic upgrade head` passed.
- PostgreSQL contains 14 domain tables plus `alembic_version`.
- `docker compose exec -T app pytest -x` passed: 2 tests passed.
- GetCourse webhook payload discovery recorded from screenshots.
- `ruff check .` passed after `getcourse-webhook`.
- `mypy src` passed after `getcourse-webhook`.
- `pytest -x` passed after `getcourse-webhook`: 7 tests passed.
- `docker compose up -d --build` passed after `getcourse-webhook`.
- `docker compose exec -T app ruff check .` passed.
- `docker compose exec -T app mypy src` passed.
- `docker compose exec -T app pytest -x` passed: 7 tests passed.
- Smoke-tested `GET /webhooks/getcourse` on `localhost:8000`: first request created a lead, repeated request deduplicated to the same lead.
- `ruff check .` passed after consent normalization follow-up.
- `mypy src` passed after consent normalization follow-up.
- `pytest -x` passed after consent normalization follow-up: 9 tests passed.
- `docker compose exec -T app ruff check .` passed after consent normalization follow-up.
- `docker compose exec -T app mypy src` passed after consent normalization follow-up.
- `docker compose exec -T app pytest -x` passed after consent normalization follow-up: 9 tests passed.
- Smoke-tested consent derivation through `GET /webhooks/getcourse` on `localhost:8000`; `custom_10558670=Да` created `personal_data`, `privacy_policy`, and `offer_agreement`.
- `docker compose up -d` passed after starting Docker Desktop.
- `docker compose exec -T app alembic upgrade head` applied `0002_bot_link_tokens`.
- `ruff check .` passed after `bot-linking`.
- `mypy src` passed after `bot-linking`.
- `pytest -x` passed after `bot-linking`: 14 tests passed.
- `docker compose exec -T app ruff check .` passed after `bot-linking`.
- `docker compose exec -T app mypy src` passed after `bot-linking`.
- `docker compose exec -T app pytest -x` passed after `bot-linking`: 14 tests passed.
- Smoke-tested webhook -> join page -> messenger link on `localhost:8000`; Telegram identity link returned `created:true`.
- Installed updated dependencies in local `.venv` after adding `aiogram`.
- `ruff check .` passed after Telegram adapter follow-up.
- `mypy src` passed after Telegram adapter follow-up.
- `pytest -x` passed after Telegram adapter follow-up: 16 tests passed.
- `docker compose up -d --build` passed after adding `aiogram`.
- `docker compose exec -T app ruff check .` passed after Telegram adapter follow-up.
- `docker compose exec -T app mypy src` passed after Telegram adapter follow-up.
- `docker compose exec -T app pytest -x` passed after Telegram adapter follow-up: 16 tests passed.
- `ruff check .` passed after Telegram commands/outbound follow-up.
- `mypy src` passed after Telegram commands/outbound follow-up.
- `pytest -x` passed after Telegram commands/outbound follow-up: 22 tests passed.
- `docker compose exec -T app ruff check .` passed after Telegram commands/outbound follow-up.
- `docker compose exec -T app mypy src` passed after Telegram commands/outbound follow-up.
- `docker compose exec -T app pytest -x` passed after Telegram commands/outbound follow-up: 22 tests passed.
