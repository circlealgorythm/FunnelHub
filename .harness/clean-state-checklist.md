# Clean State Checklist

Use this before closing a non-trivial session.

## Repo State

- `git status --short` reviewed.
- Own changes are understood.
- Unrelated user changes are not reverted.
- Generated archives, temporary scripts, database dumps, and credential files are not tracked.

## Harness State

- `.harness/progress.md` updated for completed decisions or deployed work.
- `.harness/session-handoff.md` updated with current status, verification, and next steps.
- Architectural decisions are recorded in `progress.md` Decisions.

## Verification State

- Applicable checks were run and exact results are known.
- Skipped checks have an explicit reason.
- Production deploys have a focused smoke result.

## Runtime State

- No required local dev server or long-running command is left unmanaged.
- Docker/service status was checked when the task touched runtime behavior.
- Temporary production smoke data was cleaned up or explicitly documented.

