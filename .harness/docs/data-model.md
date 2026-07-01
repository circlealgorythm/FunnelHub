# Core Data Model

Initial PostgreSQL schema is managed by Alembic migration:

`migrations/versions/0001_core_data_model.py`

## Tables

- `leads`: main lead profile copied from GetCourse and later maintained by FunnelHub.
- `lead_contacts`: normalized email/phone records used for deduplication and communication.
- `lead_external_ids`: external identifiers such as GetCourse user ID variants or future provider IDs.
- `lead_utm`: UTM/source snapshots from GetCourse system fields, form fields, imports, or manual data.
- `lead_custom_fields`: GetCourse additional/custom fields, including headerless XLSX columns.
- `lead_consents`: semantic consent records derived from custom fields or future forms.
- `messenger_identities`: Telegram/VK/Max account bindings for a lead.
- `bot_link_tokens`: temporary join tokens that connect a saved lead to a future Telegram/VK identity.
- `email_subscriptions`: email subscription state independent of GetCourse.
- `funnel_states`: current scheduled funnel state per lead and funnel.
- `conversations`: inbox conversation state per lead/channel.
- `messages`: inbound/outbound bot and email message history.
- `autoposts`: public social post queue for Telegram channel/VK group wall publishing.
- `autopost_publications`: per-public-channel publication history for an autopost.
- `followup_posts`: private bot follow-up posts for leads who completed the main messenger funnel.
- `followup_deliveries`: per-lead/per-channel follow-up delivery queue and send history.
- `import_batches`: uploaded GetCourse import files and processing stats.
- `import_rows`: raw row-level import data and row-level errors.
- `events`: deduplicated business/technical event log.

## Design Decisions

- `leads.getcourse_user_id` is unique when present.
- Email and phone deduplication lives in `lead_contacts` through `contact_type + normalized_value`.
- Messenger identity deduplication lives in `messenger_identities` through `channel + external_user_id`.
- Headerless GetCourse export columns are preserved in `lead_custom_fields` by `field_position`.
- Consent checkboxes are normalized into `lead_consents` only after a custom-field mapping is known.
- Raw GetCourse/import data is kept as JSONB for traceability and future remapping.
- Message/inbox tables are channel-generic so Telegram, VK, Max, and email can share the same core model.
- Follow-up posts and public autoposts are separate runtime entities. A marked public autopost may
  create a private follow-up copy, but publication rows and follow-up delivery rows remain
  independent.
- Follow-up delivery idempotency is enforced by `followup_post_id + lead_id + channel`.
- Queued follow-up delivery timing is persisted in `followup_deliveries.available_at`; this
  survives worker/app restarts.

## Notes For Import Implementation

- XLSX imports must preserve blank/headerless columns.
- CSV imports must support `cp1251` and tab delimiter.
- Import mapping should let the operator map headerless custom fields to consent types.
- Unknown fields should remain in raw JSONB even if not mapped to first-class columns.
