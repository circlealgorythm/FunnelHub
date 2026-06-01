# session-handoff.md

## Summary

FunnelHub is being set up as a Harness-engineering project. GetCourse keeps courses/payments/access. FunnelHub owns bots, email, inbox, lead database, imports, broadcasts, and analytics.

## Current Feature

`<нет>`

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
- Added future `knowledge-rag` feature to the roadmap after manual broadcasts and before autoposting.
- Documented RAG architecture in `.harness/docs/knowledge-rag.md`: structured operational data stays SQL/API/report driven; RAG is for unstructured scenario, inbox, product, objections, documents, policies, and operator knowledge.
- Preferred future implementation: PostgreSQL + pgvector, separated from the core lead schema.
- Implemented `funnel-engine` skeleton in `src/funnelhub/services/funnel_engine.py`.
- Funnel definitions now load from YAML/JSON data files and are validated before use.
- Added placeholder scenario in `content/funnels/example.yml`; real customer script content is still pending.
- Funnel scheduling currently uses existing `funnel_states`: start state, due-state lookup, one-step send, step advance, and completion.
- Added dry-run sender interface so Telegram/email adapters can be connected later without hardcoding channel logic into the engine.
- Added `.harness/docs/funnel-engine.md` and tests in `tests/test_funnel_engine.py`.
- Added `PyYAML`/`types-PyYAML` and copied `content/` into the Docker image.
- Implemented Telegram funnel runner service in `src/funnelhub/services/funnel_runner.py`.
- Added worker entrypoint `python -m funnelhub.funnel_worker`.
- Added Docker Compose `funnel-worker` service under the `worker` profile, so it does not start during normal local `docker compose up`.
- Runner sends due Telegram steps through `send_telegram_text_message(...)`, records outbound `messages`, advances `funnel_states`, and rolls back failed states for retry.
- Added runner env settings: `DEFAULT_FUNNEL_PATH`, `FUNNEL_RUNNER_INTERVAL_SECONDS`, and `FUNNEL_RUNNER_BATCH_SIZE`.
- Added runner test in `tests/test_funnel_runner.py`.
- Implemented default funnel autostart for Telegram linking.
- `POST /api/messenger/link` starts the default funnel after successful Telegram linking.
- Telegram `/start <token>` starts the same default funnel after successful linking.
- Repeated Telegram linking reuses the existing `funnel_states` row and does not create duplicates.
- Implemented VK parity for the current messenger layer.
- Added VK environment settings: `VK_GROUP_SCREEN_NAME`, `VK_GROUP_ACCESS_TOKEN`, `VK_CALLBACK_SECRET`, `VK_CONFIRMATION_CODE`, and `VK_API_VERSION`.
- `/join/{token}` can now render a VK deep link via `https://vk.me/<screen_name>?ref=<token>`.
- `POST /api/messenger/link` starts the default funnel for VK as well as Telegram.
- Added `POST /webhooks/vk` for VK Callback API `confirmation` and `message_new`.
- VK `message_new` can link a lead from `message.ref`, JSON `message.payload`, or `/start <token>` text.
- VK `message_new` with `/stop`, `stop`, `стоп`, or `отписаться` unsubscribes the VK identity.
- Added VK outbound sending through `messages.send` with URL keyboard support and `messages` persistence.
- Funnel definitions now support `messenger`, `telegram`, `vk`, and `email` channels. `messenger` routes through the subscribed Telegram/VK identity.
- `content/funnels/example.yml` now uses `channel: messenger`, so the same placeholder funnel can run in Telegram or VK.
- Added `docker-compose.prod.yml` and `Caddyfile` scaffolding for later production deployment.
- User asked not to deploy FunnelHub yet; only HTTPS/VK approval preparation was performed.
- Connected to VPS `31.129.110.56` via SSH from `.env`; server is Ubuntu 24.04.4 LTS.
- Installed Caddy/UFW on the VPS, allowed ports 22/80/443, and enabled Caddy.
- Configured temporary Caddy response for `bot.aisukam.ru`: `/health` returns `ok`, `/webhooks/vk` returns VK confirmation string `dbcd0b9d`.
- Let's Encrypt certificate for `bot.aisukam.ru` was issued by Caddy and HTTPS works.
- User later approved production deployment.
- Updated `docker-compose.prod.yml` to run `app`, `telegram-bot`, `funnel-worker`, `postgres`, and `redis`; host Caddy remains outside Docker and proxies to `127.0.0.1:8000`.
- Uploaded the current project to `/opt/funnelhub` on VPS `31.129.110.56`.
- Installed Docker 29.1.3 and Docker Compose 2.40.3 on the VPS.
- Built and started the production Docker stack.
- Applied production Alembic migrations through `0002_bot_link_tokens`.
- Switched `/etc/caddy/Caddyfile` from temporary VK confirmation responder to reverse proxying the real FunnelHub app.
- Production `https://bot.aisukam.ru/health` now returns the real FastAPI health response.
- Production GetCourse smoke webhook created a test lead and returned a public `join_url`.
- Production join page rendered Telegram and VK deep links.
- Production VK confirmation POST returned `dbcd0b9d`.
- Production logs show Telegram polling started for `@vedicschool_aisu_bot`; worker pass logs are healthy after migrations.
- Added real consultation scenario in `content/funnels/aisu_consultation.yml`.
- Set default funnel path to `content/funnels/aisu_consultation.yml`.
- The real scenario has 26 scheduled messenger steps. Long messages were split below platform-size limits.
- Added questionnaire support: `kind: question`, text buttons, stored answers, pending question metadata, and delayed reminders.
- The first questionnaire answer sends the second question immediately; the second answer sends the personalized response immediately.
- If answers arrive late, the scheduled chain continues from the current position and is not rewound.
- Telegram and VK incoming text now route into questionnaire answer handling after link/start.
- CTA buttons from the scenario point to `https://aisukam.ru/courses`.
- Three lesson video/page links are present from the current scenario and can be replaced later when final video assets are ready.

## Next Recommended Step

Recommended next feature: configure GetCourse to call `https://bot.aisukam.ru/webhooks/getcourse`, then run a real Telegram/VK user-path smoke from a phone/account before restarting ads.

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
- 2026-05-27 after Windows reinstall check: Docker 29.5.2 and Docker Compose v5.1.4 are available.
- 2026-05-27 after Windows reinstall check: `.env`, `.env.example`, `Dockerfile`, and `docker-compose.yml` exist; required `.env` keys are present without printing secret values.
- 2026-05-27 after Windows reinstall check: `docker compose config --quiet` passed.
- 2026-05-27 after Windows reinstall check: `docker compose up -d --build` passed; app, PostgreSQL, and Redis are running.
- 2026-05-27 after Windows reinstall check: `docker compose exec -T app alembic current` returned `0002_bot_link_tokens (head)` and `alembic upgrade head` passed.
- 2026-05-27 after Windows reinstall check: `docker compose exec -T app ruff check .`, `docker compose exec -T app mypy src`, and `docker compose exec -T app pytest -x` passed; pytest reported 22 tests passed.
- 2026-05-27 after Windows reinstall check: `/health` returned OK, webhook -> join page -> messenger link smoke passed, and PostgreSQL contains all 15 expected domain tables.
- 2026-05-28 local `ruff check .`, `mypy src`, and `pytest -x` passed after `funnel-engine`; pytest reported 29 tests passed.
- 2026-05-28 Docker `ruff check .`, `mypy src`, and `pytest -x` passed after `funnel-engine`; pytest reported 29 tests passed.
- 2026-05-28 local `ruff check .`, `mypy src`, and `pytest -x` passed after `funnel-runner`; pytest reported 30 tests passed.
- 2026-05-28 Docker `docker compose config --quiet`, `docker compose --profile worker config --quiet`, `ruff check .`, `mypy src`, and `pytest -x` passed after `funnel-runner`; pytest reported 30 tests passed.
- 2026-05-28 local `ruff check .`, `mypy src`, and `pytest -x` passed after `funnel-autostart`; pytest reported 31 tests passed.
- 2026-05-28 Docker `docker compose config --quiet`, `docker compose --profile worker config --quiet`, `ruff check .`, `mypy src`, and `pytest -x` passed after `funnel-autostart`; pytest reported 31 tests passed.
- 2026-05-31 local `ruff check .`, `mypy src`, `pytest -x`, and `docker compose config --quiet` passed after VK integration; pytest reported 46 tests passed.
- 2026-05-31 `docker compose -f docker-compose.prod.yml config --quiet` passed.
- 2026-05-31 VPS HTTPS smoke passed: `https://bot.aisukam.ru/health` returned `ok`; `/webhooks/vk` returned `dbcd0b9d`.
- 2026-06-01 local `ruff check .`, `mypy src`, `pytest -x`, `docker compose config --quiet`, and `docker compose -f docker-compose.prod.yml config --quiet` passed after real scenario integration; pytest reported 49 tests passed.
- 2026-06-01 production deploy passed: Docker stack up, migrations applied, Caddy reverse proxy active, health/webhook/join/VK-confirmation smoke checks passed.
