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
- `email_subscriptions`: email subscription state independent of GetCourse.
- `funnel_states`: current scheduled funnel state per lead and funnel.
- `conversations`: inbox conversation state per lead/channel.
- `messages`: inbound/outbound bot and email message history.
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

## Notes For Import Implementation

- XLSX imports must preserve blank/headerless columns.
- CSV imports must support `cp1251` and tab delimiter.
- Import mapping should let the operator map headerless custom fields to consent types.
- Unknown fields should remain in raw JSONB even if not mapped to first-class columns.
