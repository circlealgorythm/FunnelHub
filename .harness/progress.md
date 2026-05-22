# progress.md

## Current State

- Project: FunnelHub.
- Methodology: Harness-engineering.
- Current feature: <нет>.
- WIP: none.
- Repo source of truth lives in `.harness/`.

## Decisions

- GetCourse remains responsible for courses, payments, installments, access, login/password issuance, and the student cabinet.
- FunnelHub server is the source of truth for lead communication, bot/email subscriptions, funnel state, inbox, imports, broadcasts, and analytics.
- GetCourse webhook test confirmed that GetCourse can call an external URL with GET query parameters, including profile fields, UTM fields, and `custom_<field_id>` parameters.
- GetCourse webhook MVP accepts the captured `GET` query-string payload at `/webhooks/getcourse`, while also allowing `POST` JSON/form payloads for compatibility.
- GetCourse webhook ingestion deduplicates by GetCourse user ID first, then normalized email, then normalized phone.
- GetCourse `custom_*` webhook fields are stored in `lead_custom_fields` by key; semantic consent normalization remains deferred until custom-field meaning is mapped.
- GetCourse account fields API exposes custom field IDs, type, order, context, and descriptions.
- Raw GetCourse account fields JSON is the source of truth for consent checkbox mapping.
- All eight user checkbox custom fields imply personal data and privacy policy consent when checked; all except `10616540` also include an offer agreement link.
- Backend stack: Python 3.12+, FastAPI, PostgreSQL, Redis, SQLAlchemy/Alembic.
- Admin MVP: server-rendered FastAPI pages with Jinja2/HTMX, mobile-friendly for inbox replies.
- Telegram: aiogram 3.x.
- VK: VK API / Callback API through a channel adapter.
- Max: future channel adapter, not MVP-critical.
- Email: external provider API/SMTP; do not use GetCourse email processes as communication source of truth.

## Completed

- Project architecture captured in `.harness/AGENTS.md`.
- Harness-engineering files created in `.harness/`.
- Created initial FastAPI scaffold with `src/funnelhub`.
- Added `/health` endpoint and unit test.
- Added `pyproject.toml`, Dockerfile, Docker Compose, `.env.example`, README, and `.gitignore`.
- Created local `.venv` with Python 3.12 and installed project dev dependencies.
- Verified Docker Desktop / Docker Compose.
- Fixed Docker Compose project naming for the Cyrillic workspace path with `name: funnelhub`.
- Fixed Dockerfile layer order so editable package install sees `src`.
- Added `.dockerignore`.
- Added SQLAlchemy core data models.
- Added Alembic setup and initial migration `0001_core_data_model`.
- Added PostgreSQL tables for leads, contacts, UTM, custom fields, consents, messenger identities, email subscriptions, funnel states, inbox conversations, messages, import batches/rows, and events.
- Documented schema in `.harness/docs/data-model.md`.
- Documented GetCourse webhook payload discovery process in `.harness/docs/getcourse-webhook.md`.
- Captured real GetCourse webhook field names from webhook.site screenshots in `.harness/docs/getcourse-webhook.md`.
- Implemented `GET/POST /webhooks/getcourse`.
- Added async SQLAlchemy session dependency.
- Added GetCourse webhook ingestion service with lead/contact/external ID/email subscription/UTM/custom field/event persistence.
- Added integration tests for creation, persistence, update by GetCourse ID, deduplication by email, custom fields, and missing identity validation.

## Open Questions

- Email provider choice.
- Final funnel length and content.
- Confirm whether the production GetCourse webhook should send all eight consent checkbox fields or only the field relevant to the active form/offer.
- Production domain name.
- Need GetCourse custom field ID/name mapping if available, because XLSX exports can contain blank/headerless columns that are actually custom fields.

## Verification Log

- `ruff check .` passed via `.venv`.
- `mypy src` passed via `.venv`.
- `pytest -x` passed via `.venv`: 1 test passed.
- `docker --version` passed: Docker 29.4.3.
- `docker compose version` passed: Docker Compose v5.1.3.
- `docker compose config --quiet` passed.
- `docker compose up -d --build` passed.
- `GET http://localhost:8000/health` returned `{\"status\":\"ok\",\"service\":\"FunnelHub\"}`.
- Inspected GetCourse export sample: cp1251, tab-separated, 39 columns, header only. Details saved in `.harness/docs/getcourse-export.md`.
- Inspected XLSX export sample with one user row. Confirmed columns 14-21 have blank headers but contain custom field values such as `Да`; these likely include privacy policy / offer consent checkboxes. Updated `.harness/docs/getcourse-export.md`.
- `ruff check .` passed after core data model changes.
- `mypy src` passed after core data model changes.
- `pytest -x` passed after core data model changes: 2 tests passed.
- `docker compose up -d --build` passed after adding Alembic and models.
- `docker compose exec -T app alembic upgrade head` passed.
- Verified local PostgreSQL tables: 14 domain tables plus `alembic_version`.
- `docker compose exec -T app pytest -x` passed: 2 tests passed.
- Recorded side conversation about discovering GetCourse webhook payload via webhook.site in `.harness/docs/getcourse-webhook.md`.
- Recorded captured webhook.site query payload from screenshots in `.harness/docs/getcourse-webhook.md`: GET request, no body/form values, profile fields, UTM fields, and custom field IDs.
- Recorded GetCourse account fields API screenshot findings in `.harness/docs/getcourse-webhook.md`: visible checkbox custom field IDs, UTM field IDs, context types, and need for raw JSON to decode descriptions.
- Recorded raw GetCourse account fields JSON mapping in `.harness/docs/getcourse-webhook.md`, including consent checkbox IDs and offer URLs.
- `ruff check .` passed after `getcourse-webhook`.
- `mypy src` passed after `getcourse-webhook`.
- `pytest -x` passed after `getcourse-webhook`: 7 tests passed.
- `docker compose up -d --build` passed after adding `python-multipart` and webhook code.
- `docker compose exec -T app ruff check .` passed after `getcourse-webhook`.
- `docker compose exec -T app mypy src` passed after `getcourse-webhook`.
- `docker compose exec -T app pytest -x` passed after `getcourse-webhook`: 7 tests passed.
- Smoke-tested `GET http://localhost:8000/webhooks/getcourse?...` twice: first returned `created:true`, second returned the same `lead_id` with `created:false`.
