# Quality Gates

Use this file when planning, implementing, or verifying changes that affect production behavior.

## Default Verification

Run the smallest applicable set first, then broaden when the change touches shared behavior.

- Python lint: `ruff check .`
- Python types: `mypy src`
- Backend tests: `pytest -x`
- Frontend build: `npm run build` in `inbox-app/` when `inbox-app/` changes.
- Compose config: `docker compose -f docker-compose.prod.yml config --quiet` when deployment,
  settings, Docker, or service wiring changes.

## Risk-Based Test Scope

- Single pure helper: focused unit test is usually enough.
- API endpoint, webhook, bot handler, or worker: focused tests plus nearby integration tests.
- Database model or migration: migration review plus tests that create/read affected records.
- Funnel scheduling or message sending: focused funnel tests plus full `pytest -x`.
- Frontend workflow: `npm run build`; browser/screenshot check when layout or interaction changes.
- Deployment helper: dry-run or config check where possible, then explicit production smoke if deployed.

## Production Smoke Expectations

For production deploys, verify only the surfaces touched by the change:

- `/health` returns OK.
- Affected public endpoint returns expected status.
- Affected worker/service is running.
- Logs show no new traceback for the changed feature.
- For migrations, production Alembic head is confirmed.

## Reporting

Never write "done" without saying what was verified.

If a check is skipped, record why:

- not applicable to docs-only change;
- local dependency unavailable;
- production credential/API not available;
- browser check not relevant.

