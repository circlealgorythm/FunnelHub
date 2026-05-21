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
- GetCourse webhook payload discovery should first be done through a temporary collector such as `webhook.site` using a synthetic test user, before implementing the production endpoint.
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

## Open Questions

- Exact first feature to implement.
- Email provider choice.
- Final funnel length and content.
- GetCourse webhook payload shape in the live account.
- Need a captured/anonymized webhook.site request from GetCourse with query params/body/headers.
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
