# Reliability Notes

Use this file for workers, scheduled sends, provider webhooks, imports, broadcasts, autoposting,
and deployment changes.

## Durable Processing

- Queueable work must have durable database state, not only in-memory state.
- Keep statuses explicit: created, queued, scheduled, processing/publishing, sent/published,
  failed, partial_failed, cancelled, skipped.
- Retry only pending/failed work; never resend already sent/published rows.
- Store provider message/post IDs when available.

## Idempotency

Use a stable unique key for every external or repeatable action:

- provider webhook event key;
- GetCourse lead identity;
- broadcast target `(broadcast_id, lead_id)`;
- autopost publication `(autopost_id, channel)`;
- future follow-up delivery `(followup_post_id, lead_id, channel)`.

## Worker Concurrency

Current workers are mostly single-process friendly. Before running multiple workers for the same
queue, add a claiming/lease model:

- claimed_by;
- claimed_at;
- lease_until;
- attempt_id;
- deterministic send idempotency key;
- row selection with database locking where supported.

## External APIs

- Expect temporary provider failures, rate limits, duplicate callbacks, and partial success.
- Record raw provider responses only when useful and safe.
- Do not let one failed channel stop unrelated channels for the same post/broadcast.

## Deployment Safety

- Apply Alembic migrations before recreating workers that depend on the new schema.
- Rebuild frontend assets before uploading/deploying when `inbox-app/` changes.
- Preserve production `.env` during archive deploys.
- Smoke the changed route/service after deploy.

