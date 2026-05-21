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

## Next Recommended Step

Choose the next feature. Recommended next feature: `getcourse-webhook`.

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
