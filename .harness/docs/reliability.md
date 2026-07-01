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
- follow-up delivery `(followup_post_id, lead_id, channel)`.

## Follow-Up Queue Reliability

- Follow-up delivery state is stored in PostgreSQL through `followup_posts` and
  `followup_deliveries`; Redis is not the source of truth for recipient queues.
- Queued follow-up posts are backfilled for leads when the main `aisu_consultation` funnel
  completes.
- For queued mode, accumulated posts are delivered starting the day after completion, one post per
  day per lead/channel, using the post's configured send time.
- Immediate mode is independent of the personal queued cadence and must not shift queued
  `available_at` values.
- The worker sends only due `pending`/`failed` delivery rows and updates per-row status, timestamps,
  message IDs, and errors.
- Do not edit or delete a follow-up post after any delivery has started sending. Pending-only edits
  rebuild pending delivery rows.

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
