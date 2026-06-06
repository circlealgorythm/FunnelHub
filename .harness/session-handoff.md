# session-handoff.md

## Summary

FunnelHub is being set up as a Harness-engineering project. GetCourse keeps courses/payments/access. FunnelHub owns bots, email, inbox, lead database, imports, broadcasts, and analytics.

## Latest Session - 2026-06-06 Simultaneous Funnel Execution per Channel

- Diagnosis: A single lead could not run the same funnel simultaneously in both Telegram and VK because the unique constraint `(lead_id, funnel_key)` on `funnel_states` would cause a collision. When restarting in a new channel, the old state was deleted.
- Implemented: `FunnelState` decoupled by channel. Added `channel` column to `funnel_states` table. The unique constraint is now `(lead_id, funnel_key, channel)`.
- Updated: `funnel_engine.py`, `funnel_autostart.py`, `funnel_answers.py`, and `funnel_runner.py` modified to strictly query, start, and advance funnel states based on the specific channel instead of generic `messenger_channel` metadata.
- Implemented: Alembic migration `0004_funnelstate_channel` generated to apply the schema change, set default channels for existing states, and replace the unique constraint.
- Verification: Deployed code to the VPS, applied migration `alembic upgrade head`, rebuilt and restarted `app`, `telegram-bot`, and `funnel-worker` containers.

## Previous Session - 2026-06-06 Old GetCourse Users / VK / Admin Email
- Implemented: `src/funnelhub/services/getcourse_api.py` adds optional GetCourse Export Users
  enrichment. `/join/getcourse` saves the lead, calls GetCourse API by email, polls the export,
  maps `info.fields`/`info.items`, then reuses normal ingestion to fill `gc_user_id`,
  normalized `VK-ID` values, and `lead_external_ids(provider=getcourse_vk_id)` before rendering
  the thank-you page. `/webhooks/getcourse` site beacon payloads with `form_type` intentionally
  do not call the API to avoid doubling Export API quota use.
- Implemented: `src/funnelhub/services/lead_notifications.py` sends application notification
  email to `LEAD_NOTIFICATION_EMAIL_TO` through the configured email provider. A 300-second
  per-lead cooldown prevents duplicate notification emails from the site's background webhook
  plus redirect.
- Implemented: `restart_default_funnel_for_lead(...)` resets the messenger funnel on real bot
  starts. Telegram `/start <token>` and VK `message_allow`/`message_new` with a token now relink
  the identity to the current lead, clear old questionnaire answers/pending metadata, pin the
  channel, and send from the beginning.
- Production `.env` now has `GETCOURSE_API_BASE_URL`, `GETCOURSE_API_KEY`,
  `GETCOURSE_API_POLL_ATTEMPTS=10`, `GETCOURSE_API_POLL_INTERVAL_SECONDS=1`,
  `LEAD_NOTIFICATION_EMAIL_TO=aisukam-info@yandex.ru`, and
  `LEAD_NOTIFICATION_COOLDOWN_SECONDS=300`. The key value must not be written to docs; it was
  supplied in chat and should be rotated in GetCourse after the fix is stable.
- Verification: local `ruff check .`, `mypy src`, focused GetCourse/API/reset tests, full
  `pytest -x` with 133 tests, and production `/health` passed. Production rollback smoke
  confirmed API enrichment gets `gc_id` and `VK-ID` for Olga, test admin notification sends
  through Unisender without persisting smoke DB rows, and reset clears old answers back to
  `welcome`. Production app, telegram-bot, and funnel-worker were rebuilt/recreated; services
  are running.
- Repair: real latest Olga lead `f4654a22-e6e3-4203-8eea-445c30018eaf` was enriched in
  production, now has `gc_id`, `getcourse_vk_id`, subscribed VK identity, and one sent VK outbound
  message.

## Latest Technical Audit

- 2026-06-04 pre-development technical audit completed without changing production code.
- Highest-priority finding `src/funnelhub/main.py` `/inbox/{path:path}` encoded path traversal was fixed locally on 2026-06-04 by resolving requested files under `inbox-app/dist` and refusing paths outside that directory. Local reproduction of `/inbox/%2e%2e/%2e%2e/pyproject.toml` now returns the Inbox `index.html` instead of file contents.
- Production deploy for this fix completed on 2026-06-04. The archive was uploaded to `/opt/funnelhub`, production `.env` was preserved, only the `app` service was rebuilt/recreated, and public smoke checks passed: `/health` HTTP 200, `/inbox` HTTP 200 with assets, and `curl --path-as-is /inbox/%2e%2e/%2e%2e/pyproject.toml` returned Inbox `index.html` instead of `pyproject.toml`.
- GetCourse webhook authentication/rate limiting was implemented on branch `codex/getcourse-webhook-auth`, fast-forward merged into `main`, and deployed to production on 2026-06-05 in compatibility mode. It adds `GETCOURSE_WEBHOOK_SECRET`, `GETCOURSE_WEBHOOK_SECRET_REQUIRED`, and `GETCOURSE_WEBHOOK_RATE_LIMIT_PER_MINUTE`; protects both `/webhooks/getcourse` and `/join/getcourse`; accepts `X-FunnelHub-Webhook-Secret` plus compatible query/form secret fields; strips those secret fields before raw GetCourse payload persistence; and keeps current production behavior compatible while `GETCOURSE_WEBHOOK_SECRET_REQUIRED=false`.
- Production `.env` now has a generated `GETCOURSE_WEBHOOK_SECRET`, `GETCOURSE_WEBHOOK_SECRET_REQUIRED=false`, and `GETCOURSE_WEBHOOK_RATE_LIMIT_PER_MINUTE=120`. Do not print the secret. A production `.env` backup was created during deploy.
- Production smoke passed after deploy: public `/health` HTTP 200; `/webhooks/getcourse` accepted no-secret compatibility flow; `/webhooks/getcourse` accepted a valid header secret; invalid query secret returned HTTP 403 without lead creation; `/join/getcourse` accepted the old no-secret flow; `/join/getcourse` rejected invalid query secret with HTTP 403; smoke leads were cleaned up; Telegram polling and funnel-worker logs were healthy.
- Production app access-log was disabled on 2026-06-05 with `uvicorn --no-access-log`, so query strings such as `/join/getcourse?...&fh_secret=...` no longer appear in the app container stdout. A smoke request with `fh_secret=visible-log-marker-do-not-use` returned HTTP 403 and the marker did not appear in recent app logs. Business/application logs remain enabled.
- Public site `AisuKam_site` was updated and deployed by the user on 2026-06-05. Source commit: `f72a914 Add FunnelHub redirect secret env`. Live `aisukam.ru` now adds the generated FunnelHub `fh_secret` to the background `/webhooks/getcourse` sync and the `/join/getcourse` redirect.
- Real live application smoke passed on 2026-06-05: the user submitted the production `aisukam.ru` form, the Telegram/VK choice page opened, the lead was found in FunnelHub, `fh_secret` was not persisted in `raw_getcourse_data`, `form_type` and `custom_10616540` arrived, `personal_data` and `privacy_policy` consents were created, the email funnel state is active, and recent app logs contained no `fh_secret`, email, or `/join/getcourse?`.
- Production cleanup completed on 2026-06-05 after the user asked to remove test leads and cancel their subscriptions. A pg_dump backup was saved at `/opt/funnelhub/backups/funnelhub_before_test_leads_cleanup_20260605_005946.dump`; 2 test leads were deleted along with lead-owned contacts, email subscriptions, bot link tokens, funnel states, conversations, messages, consents, custom fields, events tied to those leads, and messenger identities. Post-cleanup counts for lead/subscription/funnel/message tables were 0; public `/health` returned OK; worker logs showed clean passes after restart.
- Thank-you page mobile CTA fix was deployed to production on 2026-06-05. `src/funnelhub/api/messenger.py` now renders Telegram/VK directly below the title, before gifts and the "Что дальше" card; the mobile card `order: -1` was removed. Local verification: `ruff check src/funnelhub/api/messenger.py tests/test_getcourse_webhook.py`, `.venv\Scripts\python.exe -m mypy src`, pure `render_join_page` HTML-order check, in-app Browser preview at 390x844 confirmed Telegram top=129px and VK bottom=261px, and `.venv\Scripts\python.exe -m pytest tests/test_getcourse_webhook.py -q` passed with 29 tests after local Docker/PostgreSQL was started. Production deploy updated `/opt/funnelhub/src/funnelhub/api/messenger.py`, rebuilt/recreated only `app`, public `/health` returned OK, and in-container render smoke confirmed the CTA block is before gifts/visual.
- Inbox `База` per-lead bot links were deployed to production on 2026-06-05. Lead detail API now creates or reuses an active bot link token and returns Telegram/VK URLs; the React lead card shows a default-open "Ссылки на ботов" section with copy/open controls. Local verification passed: focused `ruff`, `mypy src`, `npm run build` in `inbox-app`, and `tests/test_inbox_database.py` with 10 tests. Production deploy uploaded `src/funnelhub/api/inbox.py`, `inbox-app/src/App.tsx`, `inbox-app/src/styles.css`, and fresh `inbox-app/dist`, rebuilt/recreated only `app`; public `/health`, `/inbox` asset smoke, and in-container rollback bot-link smoke passed.
- First-day email sequence fix was deployed to production on 2026-06-05. `content/funnels/aisu_email.yml` is version 3 and starts with three emails from `Первый день в мейл-рассылке.docx`: `day_01_intro` due immediately (`0m`) with Telegram/VK bot buttons, `day_01_video_steps` after 2 minutes, and `day_01_meditation` after 90 minutes. `src/funnelhub/services/funnel_runner.py` resolves `funnelhub://bot/telegram` and `funnelhub://bot/vk` at send time through the same bot-link builders as the thank-you page; `src/funnelhub/funnel_worker.py` passes settings into the runner. Local verification passed: focused pytest for email definition and runner reported 10 passed, `ruff check .`, `mypy src`, full `pytest -x` with 119 tests, and `docker compose -f docker-compose.prod.yml config --quiet` with existing local env warnings. Production deploy stopped `funnel-worker` during replacement, rebuilt/recreated `app`, `telegram-bot`, and `funnel-worker`; public `/health` returned OK after startup, in-container definition smoke confirmed version 3 with 20 steps and delays `0m/2m/90m`, rollback smoke confirmed Telegram/VK links render in email plaintext and HTML without real delivery, services were running, and worker logs showed clean passes.
- Current production leads were backfilled into the new first-day email sequence on 2026-06-05. Before mutation, 9 subscribed email leads had `aisu_email_sequence` active at `day_02` and 0 email-sequence messages sent. Backup: `/opt/funnelhub/backups/funnelhub_before_email_day1_reset_20260605_142056.dump`. `funnel-worker` was stopped, all 9 email states were reset to `day_01_intro` due immediately, then worker was restarted. Verification: `day_01_intro` sent to 9, `day_01_video_steps` sent to 9, 0 email failures, and all 9 states are now at `day_01_meditation`, scheduled for 2026-06-05 15:53 UTC. Public `/health` returned OK and services were running.
- Inbox database detail human-readable labels were deployed to production on 2026-06-05. The React lead detail now renders funnel states as cards with `Email-рассылка` / `Бот-воронка`, human step names such as `День 1: медитация`, and status `Активна`; contacts, external IDs, email subscription statuses, and recent message directions also use human labels. Local verification: `npm run build` in `inbox-app`, focused `ruff`, `mypy src`, and `pytest tests/test_inbox_database.py -q` with 10 tests. Production deploy uploaded `inbox-app/src/App.tsx`, `inbox-app/src/styles.css`, and fresh `inbox-app/dist`, rebuilt/recreated only `app`; public `/health` and `/inbox` returned OK, and in-container bundle smoke confirmed the new labels/CSS are present.
- Unisender Go delivery/open/click/bounce/complaint/unsubscribe webhooks were implemented, configured in Unisender Go, and deployed on 2026-06-05. Endpoint: `GET/POST /webhooks/email/unisender-go`; `GET` is for Unisender URL validation and `POST` validates provider `auth`, processes Unisender `events_by_user` with fields under `event_data`, writes idempotent `events`, updates existing message delivery/read/failure fields without changing DB schema, and stops future email sends on hard bounce, spam/complaint, and provider unsubscribe. Local `ruff check .` and `mypy src` passed; local DB pytest could not run because Docker Desktop/PostgreSQL was unavailable. Production deploy rebuilt/recreated only `app`; public `/health` returned OK; in-container HTTP smoke processed 6 signed provider-format events and verified expected DB state; invalid auth returned HTTP 403; cleanup confirmed no temporary smoke data remained. Unisender Go confirmed active webhook id `419937`, `event_format=json_post`, `delivery_info=1`, all required `email_status` events, and `spam_block=*`.
- VK subscription simplification was implemented and deployed on 2026-06-06. New thank-you page VK buttons and email `funnelhub://bot/vk` links now resolve to `https://vk.me/<screen_name>?ref=<token>` even when VK OAuth settings are present, so leads are not sent through VK ID authorization. OAuth callback code remains available for old links. Local verification passed: focused `ruff`, `mypy src`, and `pytest tests/test_join_page.py -q`; DB-dependent pytest could not run because local Docker/PostgreSQL was unavailable. Production deploy uploaded only `src/funnelhub/api/messenger.py` and `src/funnelhub/services/funnel_runner.py`, rebuilt/recreated `app` and `funnel-worker`, then verified public `/health` OK, container render `vk_me=True` and `id_vk=False`, and `runner_uses_oauth=False`.
- Telegram/VK entry UX simplification was implemented and deployed on 2026-06-06. The thank-you page now shows `Открыть Telegram` and `Открыть VK`; the personal bot-link token stays hidden in the button URL for attribution. Telegram `/start` without a token and `/status` fallback copy now directs the lead back to the Telegram button on the post-application page, without asking for a personal link. Local verification passed: focused `ruff`, `mypy src`, and `pytest tests/test_telegram_bot.py tests/test_join_page.py -q`. Production deploy uploaded `src/funnelhub/api/messenger.py` and `src/funnelhub/telegram_bot.py`, rebuilt/recreated `app` and `telegram-bot`, then verified public `/health`, service status, page render (`open_telegram=True`, `open_vk=True`, `has_personal_link_copy=False`, `tg_deep=True`, `vk_deep=True`), and Telegram status text.
- One-off bot-link correction email was sent on production on 2026-06-06 after the user cancelled the planned email funnel restart. The `funnel-worker` was brought back up, no `funnel_states` were reset, and current email sequencing continued. The correction email used `broadcast_key=bot_links_fix_20260606`, subject `Новые ссылки на Telegram и VK бот`, and simple per-lead buttons `Открыть Telegram` / `Открыть VK`; the user-requested text did not include an extra sentence about not needing to enter anything. Verification showed 11 correction messages delivered, 0 duplicates, 0 failed correction messages, 0 target leads missing the correction, and `current_email_funnel_steps=day_02:11`.
- VK launch workaround was implemented and deployed on 2026-06-06. Public VK buttons now point to FunnelHub `GET /join/{token}/vk` rather than directly to `vk.me`; that endpoint tries a server-side restart when the lead already has a subscribed VK identity or a stored GetCourse `VK-ID`, then redirects to plain `vk.me`. This keeps OAuth out of the main flow and covers imported/known VK users, but cannot identify an unknown already-allowed VK user from a browser-only `vk.me` transition because VK does not send a new callback in that case. The endpoint resets the messenger funnel to the first VK step with a 10-minute duplicate guard. Local verification passed: focused `ruff`, `mypy src`, and targeted tests for join page/email buttons/Inbox links/VK-ID relaunch. Production deploy rebuilt/recreated `app` and `funnel-worker`; smoke verified `/health`, launch links, no `id.vk.ru`, and fake rollback VK send/identity/message creation for a stored `VK-ID`.
- Manual `VK-ID` editing was implemented and deployed in Inbox `База` on 2026-06-06. Lead detail has a `VK-ID` input in the `Ссылки на ботов` section; `PUT /api/inbox/database/leads/{lead_id}/vk-id` validates numeric IDs, rejects conflicts with another lead, saves `lead_external_ids(provider=getcourse_vk_id)`, mirrors the value into `LeadCustomField(field_key=vk_id)`, and returns refreshed detail. Local verification passed: focused `ruff`, `mypy src`, `pytest tests/test_inbox_database.py -q` with 11 tests, and `npm run build`. Production deploy rebuilt/recreated `app`; smoke verified valid/invalid API behavior, response/DB persistence, `/join/.../vk` bot links, UI bundle markers, and cleanup of temporary smoke data.
- VK relaunch questionnaire-state fix was implemented and deployed on 2026-06-06. Root cause for test lead `Ксения`: repeated `/join/{token}/vk` reset the VK funnel but preserved old questionnaire metadata, so new question buttons were ignored because `answers` already contained both answers. `src/funnelhub/api/messenger.py` now clears `answers`, pending question keys, questionnaire waiting key, and questionnaire timestamps before restarting the VK funnel. Local verification passed with focused `ruff`, `mypy src`, and 12 targeted tests. Production `app` was rebuilt/recreated; `/health` passed; rollback smoke with a fake VK client confirmed stale metadata is cleared and state returns to `question_topic`. The production `Ксения` state was repaired without sending another message, so the already visible topic buttons should now produce the second question when clicked.
- Audit item 2 is closed in safe compatibility mode. `GETCOURSE_WEBHOOK_SECRET_REQUIRED=true` is intentionally not enabled because strict mode could drop FunnelHub ingestion for old cached site bundles or alternate form paths that omit the secret. Current production setting remains `GETCOURSE_WEBHOOK_SECRET_REQUIRED=false`.
- Local verification for the GetCourse hardening passed: `pytest tests/test_getcourse_webhook.py -q` with 29 tests, `ruff check .`, `mypy src`, full `pytest -x` with 118 tests, and `docker compose -f docker-compose.prod.yml config --quiet`. Compose emitted only existing local env interpolation warnings.
- Other important findings to carry forward: GetCourse ingestion remains compatibility-open in production until GetCourse/site secret transport and log hygiene are finalized and `GETCOURSE_WEBHOOK_SECRET_REQUIRED=true` is enabled, worker/manual-send paths can duplicate external sends after rollback or concurrent workers, production CORS still allows credentialed localhost origins, Inbox import accepts only CSV and has no upload size/row cap, and docs still describe some completed/pending areas inconsistently.
- Local verification during the audit passed: `ruff check .`, `mypy src`, `pytest -x` with 109 tests, `npm run build` in `inbox-app/`, and `docker compose -f docker-compose.prod.yml config --quiet`. Compose emitted only existing local env interpolation warnings.
- Local verification after the path traversal fix passed: `pytest tests/test_main.py -q` with 2 tests, `ruff check .`, `mypy src`, full `pytest -x` with 111 tests, and `docker compose -f docker-compose.prod.yml config --quiet`. Compose emitted only existing local env interpolation warnings.

## Current Feature

`email-provider` is deployed with Unisender Go enabled on production. The Aisu Kam messenger sequence is version 2 through day 18; the email sequence is production version 3 with the new first-day three-email start plus days 2-18. Delivery/bounce/open/click/complaint/unsubscribe provider webhooks are deployed. Manual email broadcasts remain future work.

## Latest Inbox State

- Manual replies from Inbox can target one or more channels: Telegram, VK, and Email.
- Conversation detail now returns `reply_channels`, derived from subscribed messenger identities and subscribed email subscriptions.
- The React reply composer renders compact checkboxes under `Куда отправить`; the current conversation channel is selected by default, and the send button shows the selected channel count when more than one target is selected.
- Manual reply messages for all selected channels are linked to the selected inbox conversation, while each message keeps its actual `channel` for traceability in the chat history.
- Local verification for this change passed on 2026-06-04: `ruff check .`, `mypy src`, `pytest -x` with 104 tests, `npm run build` in `inbox-app/`, `docker compose -f docker-compose.prod.yml config --quiet`, and desktop/mobile in-app browser checks. Docker Compose only emitted the existing local unset-variable warnings.
- Production deploy for this change completed on 2026-06-04. Public `/health` and `/inbox` returned HTTP 200, the deployed `/inbox` JS contains the new reply-target UI, `app`, `telegram-bot`, `funnel-worker`, `postgres`, and `redis` are running, and an in-container rollback smoke verified `reply_channels=telegram,vk,email` plus fake `sent_channels=telegram,email` without persisting data.
- Inbox `База` messenger display was fixed on 2026-06-04: VK identities without usernames now count through `external_user_id`, and the list table shows only channel labels (`TG`, `VK`) rather than handles or `нет` lines. Production smoke confirmed `Buben Burshnakivechkin` has `vk=199271782`, so the UI renders `VK`.
- Consent labels in Inbox `База` were investigated on 2026-06-04. Production leads currently receive only `email,name,phone` in `raw_getcourse_data`, so no `custom_*` consent checkbox values arrive and no `lead_custom_fields`/`lead_consents` rows can be shown for existing leads. The code path is covered: known GetCourse checkbox fields now have readable policy/offer labels, tariff forms with `custom_10558670=Да` expose privacy policy + offer agreement, and consultation forms with `custom_10616540=Да` expose privacy policy only. Remaining action is to configure the GetCourse/site redirect/webhook to pass the relevant `custom_<field_id>=Да` parameter for each form.
- Inbox/GetCourse field ingestion now treats regular `utm_*` values as the only operational UTM source for Inbox, including Yandex Direct attribution. GetCourse-owned `gc_system_user_utm_*` fields are ignored for `lead_utm` display/export and remain only in raw payload/import row data.
- Inbox CSV import now supports comma/tab/semicolon input positionally, so GetCourse `.csv` exports with tab delimiters and blank custom-field headers preserve columns 14-21 as the eight known consent checkbox `custom_<field_id>` fields.
- Production deploy for this change completed on 2026-06-04. Public `/health` and `/inbox` returned HTTP 200, services are running, worker logs are clean, and rollback smoke confirmed regular `utm_*` displays as `source_kind=form` while `gc_system_user_utm_*` is ignored for `lead_utm`.
- Live `aisukam.ru` currently posts the consultation form to GetCourse and then redirects to `/join/getcourse` with only `name`, `phone`, and `email`; it does not append `custom_10616540` or regular `utm_*`. FunnelHub now has a consultation-only fallback for this redirect and derives `custom_10616540=Да` when no known consent field arrives. UTM still requires changing the site bundle/source to append `utm_source`, `utm_medium`, `utm_campaign`, `utm_term`, `utm_content`, and `utm_group` from `window.location.search`.
- Production deploy for the `/join/getcourse` consent fallback completed on 2026-06-04. Rollback smoke confirmed the current live-site consultation redirect pattern creates `custom_10616540=Да` plus `personal_data` and `privacy_policy`, without `offer_agreement`.
- The later user-provided GetCourse XLSX export at `C:\Users\circlealgorythm\Pictures\Ксюша\Проекты\user_export_with_group_id_date_2026-05-21_11-39-17.xlsx` has 27 columns, not the earlier 39-column shape. It includes separate `Имя`/`Фамилия`, headerless consent custom columns 12-19, `Откуда пришел`, regular Yandex `utm_*`, and `VK-ID`.
- GetCourse ingestion/import now handles both export shapes: `Имя` maps to first name, `Фамилия` to last name, full name is assembled if no explicit `name/full_name/ФИО` exists, and headerless custom fields are mapped by blank-column order to the eight known consent checkbox IDs.
- Production deploy for the XLSX/export-shape ingestion changes completed on 2026-06-04. Public `/health` and `/inbox` returned HTTP 200, services are running, worker logs are clean, and rollback smoke confirmed `Сергей тест Gurbin`, `source=mamba.ru`, regular Yandex `utm_*` as `source_kind=form`, `VK-ID` as `getcourse_vk_id`, and derived `personal_data`/`privacy_policy`/`offer_agreement` consents without persisting the smoke lead.

## Latest Scenario State

- `content/funnels/aisu_consultation.yml` is version 2. It starts with welcome, first questionnaire question, first video step, video/gift/review intro content, then daily CTA content from `day_02` through `day_18`.
- `content/funnels/aisu_email.yml` is production version 3 with 20 email steps: `day_01_intro` at `0m`, `day_01_video_steps` at `2m`, `day_01_meditation` at `90m`, then `day_02` through `day_18`.
- Day 1 intro email uses bot buttons with internal URLs `funnelhub://bot/telegram` and `funnelhub://bot/vk`; the runner resolves them into the same per-lead Telegram/VK links as the thank-you page, with VK using the plain `vk.me` deep link. Visible public CTA copy should stay simple and not mention personal links.
- All day CTA buttons point to `https://aisukam.ru/courses`.
- There are no CTA steps after `day_18`; future autoposting should not inherit these buttons.
- Long messenger day 7 is split into `day_07_part_1` and `day_07_part_2`; only `day_07_part_2` has the CTA button.
- Questionnaire behavior: after the first question, the first video waits 5 minutes if answers are incomplete. If both answers are completed before the first video, the personalized response is sent immediately and the first video is scheduled 1 minute later. If questions remain unanswered, the pending question repeats after each subsequent messenger funnel message, not by an independent timer.
- On production deploy, 2 active old `aisu_consultation` states at `step_08` were migrated to new `day_02`.
- 2026-06-04 urgent questionnaire-button fix is deployed. Previously `question_topic` had text plus `question_key: topic` but no explicit `buttons`, and the first send path used only `step.buttons`, so the initial question could arrive without answer buttons. `run_due_funnel_step` now attaches buttons from `questionnaire.questions[question_key].options` before sending any `kind: question` step without explicit buttons. Production smoke confirmed `question_topic` sends `Деньги|Отношения|Духовное целительство|Все вместе|Раскрытие способностей|Затрудняюсь ответить`, `/health` is OK, and worker logs are clean.

## Production Access

Production SSH access is already in the local git-ignored `.env` file:

- `SSH_HOST`
- `SSH_USER`
- `SSH_PASSWORD`

Do not ask the user for the VPS access again unless these variables are missing or invalid. Do not print or commit their values. For deploy automation from this Windows workspace, use `paramiko` with these variables; OpenSSH key login may fail because the production access currently relies on the password variables in `.env`.

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
- Added `GET /join/getcourse` as a direct GetCourse form redirect endpoint. It ingests query params, saves/updates the lead through the existing GetCourse ingestion service, generates/reuses the bot link token, and renders the Telegram/VK bonus page.
- Updated `/join/{token}` to render the same thank-you/bonus page instead of the old minimal "choose channel" page.
- The redirect endpoint ignores unresolved GetCourse placeholders like `{name}`, `{phone}`, and `{email}`; if no real identity remains, it returns a friendly 400 thank-you-page error.
- Deployment of `/join/getcourse` is complete. On 2026-06-02 the provider-side availability issue was resolved, the update was uploaded to `/opt/funnelhub`, production Docker images were rebuilt, migrations passed, and production smoke checks passed.
- Fixed Telegram funnel start behavior: `/start <token>` no longer sends the temporary "Telegram linked" message.
- Fixed questionnaire scheduling: after a question step is sent, the next content step waits for that question's `reminder_delay` (`5m` in the current scenario). If the user completes both questionnaire answers before the timeout, the next content step becomes due immediately. If the user does not answer, the content chain continues after the timeout while pending-question metadata remains available for later answers.
- Fixed Telegram `/start <token>` to send the first due default-funnel step immediately after linking, without waiting for the background worker interval.
- After deploying the immediate-start fix, the test Telegram lead `4acaaf04-59d0-4f0d-9f3f-5427bd82bd28` was reset again by deleting its current `funnel_states` and `messages`; lead, token, and Telegram identity remain intact.
- Added VK `message_allow` autostart support. When VK sends `message_allow` with the deep-link token in `object.key`/`object.ref`/`object.start`, FunnelHub links the VK user, starts the default funnel, and sends the first due step immediately. This requires enabling the `message_allow` event type in VK Callback API settings.
- Added VK `access_key` token extraction and safe diagnostic logging for VK callback events. Logs include event type, object/message keys, and token source names, but not token values or callback secrets.
- Added VK OAuth join support. The thank-you page now switches the VK button from `vk.me` to OAuth when `VK_GROUP_ID`, `VK_OAUTH_CLIENT_ID`, and `VK_OAUTH_CLIENT_SECRET` are configured. Callback URL is `https://bot.aisukam.ru/oauth/vk/callback`.
- OAuth callback validates signed state, exchanges the code, calls `messages.allowMessagesFromGroup`, links the VK identity, starts the default funnel, and sends the first due step immediately.
- Redeployed production with the corrected archive that includes untracked files. The earlier missing-module issue is resolved; `src/funnelhub/services/vk_oauth.py` is present on the VPS and production health checks pass.
- Production VK OAuth env values were added from the VK ID application, `VK_OAUTH_STATE_SECRET` was generated, and the production stack was restarted. The live thank-you page now renders `oauth.vk.com` for VK and no longer falls back to `vk.me`.
- VK ID autostart was debugged and fixed end-to-end on production. The final working flow uses `id.vk.ru/authorize`, PKCE, single-block signed state, VK ID code exchange, VK user id extraction from token response/id token, and outbound delivery through a valid community `VK_GROUP_ACCESS_TOKEN`.
- User confirmed VK opens the bot and the first funnel message arrives.
- The VK ID `Разрешить` screen is controlled by VK and cannot be skipped. FunnelHub now auto-redirects after successful callback to the VK community dialog, so its own white success page is only a fallback.
- Telegram questionnaire answer buttons now use inline callback buttons under the message. Manual text answers still work as fallback.
- VK questionnaire answer buttons now use inline `primary` colored text buttons; URL buttons remain link buttons.
- The last repeated VK test failure was `Messenger identity is already linked to another lead.` It happened because the same VK account was reused across multiple synthetic test leads. `allow_relink` now lets real bot-start/OAuth flows move the existing Telegram/VK identity to the current lead. This is enabled for Telegram `/start`, VK Callback token starts, and VK ID callback. The public `/api/messenger/link` endpoint still rejects cross-lead identity conflicts by default.
- Confirmed production `/join/getcourse` still ingests leads: repeated requests with the same synthetic email/phone returned HTTP 200, rendered Telegram/VK buttons, and reused the same bot-link token.
- Restyled the GetCourse redirect thank-you page in `src/funnelhub/api/messenger.py` to match the live Aisu Kam landing direction: cream/gold palette, serif typography, gift cards, and a decorative lamp/mandala visual. User asked to skip visual checks and review the page manually after deploy.
- Diagnosed the latest Telegram test issue: the first message went to Telegram from the `/start` handler, but the background worker continued the same lead's shared `messenger` funnel through VK because the lead had both Telegram and VK identities and VK was the latest supported identity.
- Fixed shared messenger routing by adding `messenger_channel` to `funnel_states.metadata` on Telegram/VK starts and making the worker prefer that channel for `channel: messenger` steps. Old states without this metadata keep the previous fallback behavior.
- Deployed the fix to production by updating runtime files on `/opt/funnelhub` and rebuilding/recreating `app`, `telegram-bot`, and `funnel-worker`.
- Reset the current production Telegram/VK test lead `a60d5472-0fd3-4211-b963-5e06e34c8b48`: deleted its funnel state and outbound messages while keeping Telegram identity `634471826` and VK identity `199271782` subscribed.
- Cleaned the old orphaned VK test funnel state `9348a8c0-1454-4fde-b4e9-0e321ef21075`, which had no subscribed identity and would have caused future worker failures.
- Converted `content/funnels/aisu_consultation.yml` scenario copy from quoted/folded YAML strings to literal block scalars (`|-`) so blank lines visible in the file become real paragraph gaps in Telegram/VK messages.
- Deployed the scenario formatting change to production by updating `content/funnels/aisu_consultation.yml` on `/opt/funnelhub` and rebuilding/recreating `app`, `telegram-bot`, and `funnel-worker`.
- Production parse check inside the app container confirmed the first `welcome` message now has 11 double-newline paragraph gaps.
- Deleted the two requested production test leads `Sergei Gurbin` and `Sergei Burshnabuven`. Cascade cleanup removed their funnel states, messages, messenger identities, bot link tokens, and contacts.
- Final production cleanup check confirmed no remaining matches for those names, no active funnel states, and no messenger identities.
- Before inbox implementation, a read-only production DB check confirmed the former test leads had lead rows, identities, outbound messages, and active funnel states. It also confirmed `conversations` were empty and inbound questionnaire answers were only stored in `funnel_states.metadata.answers`.
- Implemented local inbox backend/API:
  - `src/funnelhub/services/inbox.py` records inbound messages, creates conversations, links existing outbound history, lists/details conversations, sends manual replies, and adjusts auto-handled statuses.
  - `src/funnelhub/api/inbox.py` exposes conversation list/detail, reply, and status update routes under `/api/inbox`.
- `src/funnelhub/main.py` includes inbox routes and local Vite CORS.
- Telegram text/callback and VK `message_new` events now record inbound messages before questionnaire handling.
- Telegram/VK outbound sends attach to the latest conversation for the same lead/channel when one exists.
- Added migration `0003_inbox_statuses` for `needs_reply`, `replied`, and inbound `received` message status.
- Created separate React app in `inbox-app/` with Vite, TypeScript, React, lucide icons, responsive inbox layout, filters, search, chat view, lead panel, reply composer, and status actions.
- Added `inbox-app/README.md` with local run instructions and ignored `node_modules`/`dist`.
- `.harness/feature-list.json` marks `simple-inbox` as `in_progress`, because local MVP is ready but production deployment and access control are not done.
- Reviewed the full `content/funnels/aisu_consultation.yml` scenario and added semantic paragraph gaps to long messages that were still single-block text.
- Deployed the scenario paragraph cleanup to production. Production parse check confirms 0 long single-paragraph scenario/personalized messages; the largest remaining paragraph is 429 characters.
- Fixed production `funnel-worker` restart-loop causes: async SQLAlchemy `pool_pre_ping` was removed, and `run_due_funnel_once` now stores due state IDs and re-loads each state so a rollback from one failed step cannot expire the next ORM object and raise `MissingGreenlet`.
- Added regression tests for failed messenger steps with no identity and for continuing after rollback. Local focused pytest reports 16 passed; focused ruff and `mypy src` passed.
- Re-deleted production test leads `Sergei Gurbin` and `Sergei Burshnabuven` after a new test run recreated them. Final production verification showed 0 matching test leads, 0 due funnel states, and clean worker passes with no errors.
- Per user request, production was reset to a clean lead slate for a fresh TG/VK experiment. All checked lead/message/state/identity/token/event tables are now 0.
- Diagnosed the remaining TG/VK mixing: regular scheduled `messenger` steps used `funnel_states.metadata.messenger_channel`, but questionnaire reminders still selected the latest subscribed TG/VK identity. This could make unanswered question buttons repeat in VK after a Telegram start.
- Fixed questionnaire reminders in `src/funnelhub/services/funnel_answers.py` so `send_pending_question_reminder` prefers `metadata.messenger_channel` through `get_subscribed_identity(...)`.
- Added regression coverage in `tests/test_funnel_answers.py` for a lead with both Telegram and VK identities where a pending question reminder must stay in Telegram.
- Local `ruff check src/funnelhub/services/funnel_answers.py tests/test_funnel_answers.py` and `mypy src` passed. Local DB-backed pytest could not run because Docker Desktop/PostgreSQL was not running locally.
- Production deploy completed for the reminder-channel fix. Production rollback smoke verified `smoke_channel telegram` without persisting the temporary test data; final checked production counts remain 0, `due_states=0`, health is 200, and the worker logged a clean pass.
- Implemented single-admin inbox auth for Aisu:
  - `src/funnelhub/services/auth.py` hashes passwords with PBKDF2-SHA256 and verifies signed HttpOnly session cookies.
  - `src/funnelhub/api/auth.py` exposes `/api/auth/login`, `/api/auth/me`, and `/api/auth/logout`.
  - `/api/inbox/*` now requires a valid admin session.
  - `src/funnelhub/main.py` enables credentialed CORS for local Vite dev.
  - `inbox-app/src/App.tsx` shows a styled login screen, checks `/api/auth/me`, sends authenticated fetches with cookies, and has logout.
  - Required env keys are `INBOX_ADMIN_USERNAME`, `INBOX_ADMIN_PASSWORD_HASH`, and `INBOX_SESSION_SECRET`.
- Implemented local Telegram admin notifications for Inbox:
  - `src/funnelhub/services/inbox_notifications.py` builds and sends Telegram admin notifications via an env-configured notification bot.
  - Notifications are sent for inbound Telegram/VK messages that need manual reply; auto-handled questionnaire answers are recorded but do not notify.
  - Notification failures are logged and do not break customer bot handlers.
  - `INBOX_APP_URL`, `INBOX_NOTIFY_TELEGRAM_BOT_TOKEN`, and `INBOX_NOTIFY_TELEGRAM_CHAT_ID` are documented in `.env.example`.
  - `inbox-app/src/App.tsx` can open the linked conversation from `?conversation=<conversation_id>`.
- Local `.env` is configured for the notification bot and ignored by git. A direct Telegram test message to the admin chat returned `ok=true`; do not copy the token into repository files or Harness docs.
- Implemented local Inbox `База` section:
  - `src/funnelhub/services/inbox_database.py` lists/searches lead summaries, returns lead detail, exports CSV, and imports CSV through the existing GetCourse ingestion/deduplication path.
  - `/api/inbox/database/leads` routes are protected by the same single-admin Inbox auth.
  - `inbox-app/src/App.tsx` has a second `База` view with lead search/table, detail panel, CSV export, and CSV upload.
  - `inbox-app/src/styles.css` includes desktop/mobile layout for the database table and detail panel.
  - `tests/test_inbox_database.py` covers list/search, CSV export, CSV import, and authenticated API access.
- Deployed Inbox to `https://bot.aisukam.ru/inbox`:
  - React build is served by FastAPI from `inbox-app/dist` at `/inbox`.
  - Vite build uses `base: /inbox/`; frontend API calls are same-origin `/api/...`.
  - Production `.env` has Inbox admin auth, session secret, notification bot settings, and `INBOX_APP_URL=https://bot.aisukam.ru/inbox`.
  - Migration `0003_inbox_statuses` has been applied on production.
  - `app`, `telegram-bot`, and `funnel-worker` were rebuilt/recreated.

## Next Recommended Step

Recommended next step: run a real lead/inbound-message smoke through Telegram/VK, verify the conversation appears in production Inbox, verify the admin notification arrives, and send one manual reply from Inbox. The generated production admin credentials were given to the user in the deploy completion response.

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
- 2026-06-02 local `ruff check .`, `mypy src`, `pytest -x`, `docker compose config --quiet`, and `docker compose -f docker-compose.prod.yml config --quiet` passed after adding `/join/getcourse`; pytest reported 51 tests passed.
- 2026-06-02 production deploy attempt for `/join/getcourse` was blocked because VPS `31.129.110.56` did not accept TCP connections on 22, 80, or 443.
- 2026-06-02 production deploy completed after provider-side availability issue was resolved.
- 2026-06-02 production `https://bot.aisukam.ru/health` returned `{"status":"ok","service":"FunnelHub"}`.
- 2026-06-02 production `/join/getcourse` smoke returned HTTP 200 and rendered the thank-you page with Telegram/VK deep links.
- 2026-06-02 production VK confirmation POST returned `dbcd0b9d`; running services: `app`, `funnel-worker`, `postgres`, `redis`, `telegram-bot`.
- 2026-06-02 local `ruff check .`, `mypy src`, `pytest -x`, `docker compose config --quiet`, and `docker compose -f docker-compose.prod.yml config --quiet` passed after questionnaire wait/start-message fix; pytest reported 52 tests passed.
- 2026-06-02 production deploy completed for questionnaire wait/start-message fix; health returned OK, VK confirmation returned `dbcd0b9d`, and services were running.
- 2026-06-02 local `ruff check .`, `mypy src`, `pytest -x`, and `docker compose -f docker-compose.prod.yml config --quiet` passed after immediate Telegram `/start` first-step send; pytest reported 52 tests passed.
- 2026-06-02 production deploy completed for immediate Telegram `/start` first-step send; health returned OK and services were running.
- 2026-06-02 test Telegram lead reset after immediate-start deploy: deleted 1 `funnel_states` row and 2 `messages` rows.
- 2026-06-02 local `ruff check .`, `mypy src`, `pytest -x`, and `docker compose -f docker-compose.prod.yml config --quiet` passed after VK `message_allow` autostart support; pytest reported 53 tests passed.
- 2026-06-02 production deploy completed for VK `message_allow` autostart support; health returned OK, VK confirmation returned `dbcd0b9d`, and services were running.
- 2026-06-02 local `ruff check .`, `mypy src`, and focused VK/GetCourse webhook tests passed after VK `access_key` support and diagnostic logging; focused pytest reported 26 tests passed.
- 2026-06-02 production deploy completed for VK `access_key` support and diagnostic logging; services were running and server-side health returned OK.
- 2026-06-02 local `pytest tests/test_vk_oauth.py -q` passed after VK OAuth support; pytest reported 4 tests passed.
- 2026-06-02 production redeploy completed with `vk_oauth.py` included; `http://127.0.0.1:8000/health` and `https://bot.aisukam.ru/health` returned `{"status":"ok","service":"FunnelHub"}`.
- 2026-06-02 production VK OAuth env values added and stack restarted; health returned OK and production `/join/getcourse` smoke rendered `oauth.vk.com=True`, `vk.me=False`.
- 2026-06-02 production VK ID flow fixed end-to-end. User confirmed VK opened the bot and the first message arrived after replacing `VK_GROUP_ACCESS_TOKEN` with a valid community access key.
- 2026-06-02 production VK callback success page auto-redirects to the VK community dialog; health returned OK after deploy.
- 2026-06-02 local `ruff check`, `mypy src`, and Telegram/VK messaging tests passed after inline button updates; focused pytest reported 10 tests passed.
- 2026-06-02 production deploy completed for Telegram inline callback buttons and VK primary text buttons; health returned OK.
- 2026-06-02 production `/join/getcourse` lead-ingestion smoke passed with a synthetic email/phone: HTTP 200 twice, Telegram/VK buttons rendered, and the same bot-link token was reused.
- 2026-06-02 local `ruff check src/funnelhub/api/messenger.py` passed after the thank-you page restyle.
- 2026-06-02 local `pytest tests/test_getcourse_webhook.py -q` passed after the thank-you page restyle: 19 tests passed. Pytest emitted a `.pytest_cache` permission warning.
- 2026-06-02 production deploy completed for the thank-you page restyle by updating `src/funnelhub/api/messenger.py` on the VPS and rebuilding/recreating the `app` container.
- 2026-06-02 production `http://127.0.0.1:8000/health` and public `https://bot.aisukam.ru/health` returned `{"status":"ok","service":"FunnelHub"}` after the restyle deploy.
- 2026-06-02 production `/join/getcourse` smoke after deploy confirmed the page contains the new restyled blocks (`portrait-card`, `gift-list`) and Telegram/VK buttons.
- 2026-06-02 local follow-up replaced the unclear decorative right-side lamp/mandala block with a functional `Что дальше` card. `ruff check src/funnelhub/api/messenger.py` passed and `pytest tests/test_getcourse_webhook.py -q` passed with 19 tests. Production deploy was blocked by the Codex escalated-command usage limit until Jun 3rd, 2026 1:16 AM.
- 2026-06-03 local `ruff check src/funnelhub/api/messenger.py` passed before deploying the right-side `Что дальше` card.
- 2026-06-03 local `pytest tests/test_getcourse_webhook.py -q` passed before deploying the right-side `Что дальше` card: 20 tests passed. Pytest emitted a `.pytest_cache` permission warning.
- 2026-06-03 production deploy completed for the right-side `Что дальше` card by updating `src/funnelhub/api/messenger.py` on the VPS and rebuilding/recreating the `app` container.
- 2026-06-03 production `https://bot.aisukam.ru/health` returned `{"status":"ok","service":"FunnelHub"}` after deploy.
- 2026-06-03 production `/join/getcourse` public smoke confirmed the new `next-card` / `Что дальше` block renders, Telegram/VK buttons are present, and old `lamp` / `mandala` / `portrait-card` markup is absent.
- 2026-06-03 updated thank-you page copy for the meditation, three video steps, and `Что дальше` card wording.
- 2026-06-03 local `ruff check src/funnelhub/api/messenger.py` passed after thank-you page copy updates.
- 2026-06-03 local `pytest tests/test_getcourse_webhook.py -q` passed after thank-you page copy updates: 20 tests passed. Pytest emitted a `.pytest_cache` permission warning.
- 2026-06-03 production deploy completed for thank-you page copy updates. Public `https://bot.aisukam.ru/health` returned `{"status":"ok","service":"FunnelHub"}` and `/join/getcourse` smoke confirmed the new copy while old mini-course wording was absent.
- 2026-06-03 local `pytest tests/test_getcourse_webhook.py tests/test_vk_oauth.py -q`, focused `ruff check`, and `mypy src` passed after messenger `allow_relink`; pytest reported 26 tests passed.
- 2026-06-03 production deploy completed for messenger `allow_relink`; running services were `app`, `funnel-worker`, `postgres`, `redis`, and `telegram-bot`; `http://127.0.0.1:8000/health` returned `{"status":"ok","service":"FunnelHub"}`.
- 2026-06-03 production `/join/getcourse` smoke for `vk-relink-20260603@example.com` returned HTTP 200 and rendered `id.vk.ru=True`, `vk.me=False`.
- 2026-06-03 local `pytest tests/test_funnel_runner.py tests/test_getcourse_webhook.py -q` passed after messenger channel pinning: 23 tests passed. Pytest emitted a `.pytest_cache` permission warning.
- 2026-06-03 local focused `ruff check` passed after messenger channel pinning.
- 2026-06-03 local `mypy src` passed after messenger channel pinning.
- 2026-06-03 `docker compose -f docker-compose.prod.yml config --quiet` passed after messenger channel pinning.
- 2026-06-03 production deploy completed for messenger channel pinning; `app`, `telegram-bot`, and `funnel-worker` were rebuilt/recreated.
- 2026-06-03 production app health check returned HTTP 200 with `{"status":"ok","service":"FunnelHub"}` after deploy.
- 2026-06-03 production reset check confirmed `funnel_states` count is 0; Telegram identity `634471826` and VK identity `199271782` remain subscribed.
- 2026-06-03 local scenario parse check confirmed the `welcome` text now contains 11 double-newline paragraph gaps instead of 0.
- 2026-06-03 local `pytest tests/test_funnel_engine.py tests/test_funnel_runner.py tests/test_funnel_answers.py -q` passed after scenario literal-block conversion: 14 tests passed. Pytest emitted a `.pytest_cache` permission warning.
- 2026-06-03 local `ruff check src/funnelhub tests/test_funnel_engine.py tests/test_funnel_runner.py tests/test_funnel_answers.py` passed after scenario literal-block conversion.
- 2026-06-03 local `mypy src` passed after scenario literal-block conversion.
- 2026-06-03 `docker compose -f docker-compose.prod.yml config --quiet` passed after scenario literal-block conversion.
- 2026-06-03 production deploy completed for scenario literal-block conversion; `app`, `telegram-bot`, and `funnel-worker` were rebuilt/recreated.
- 2026-06-03 production parse check inside the app container confirmed `welcome_double_newlines=11` and production health returned HTTP 200 with `{"status":"ok","service":"FunnelHub"}`.
- 2026-06-03 production cleanup deleted exactly two requested test leads: `Sergei Gurbin` and `Sergei Burshnabuven`, removing 2 funnel states, 13 messages, 2 messenger identities, 2 bot link tokens, and 4 contacts through cascade.
- 2026-06-03 production cleanup verification confirmed 0 remaining matches for those names, 0 `funnel_states`, 0 `messenger_identities`, health HTTP 200, and worker logs without errors.
- 2026-06-03 local `python -m alembic upgrade head` applied `0003_inbox_statuses`.
- 2026-06-03 local focused `ruff check` passed for inbox backend/API, bot wiring, messaging services, migration, and inbox tests.
- 2026-06-03 local `mypy src` passed after inbox work: no issues in 25 source files.
- 2026-06-03 local `pytest tests/test_inbox.py -q` passed: 5 tests passed.
- 2026-06-03 local affected tests passed: `pytest tests/test_telegram_messaging.py tests/test_vk_messaging.py tests/test_getcourse_webhook.py tests/test_vk_bot.py tests/test_telegram_bot.py -q` reported 41 tests passed.
- 2026-06-03 local full `pytest -x` passed after inbox work: 68 tests passed.
- 2026-06-03 `docker compose config --quiet` and `docker compose -f docker-compose.prod.yml config --quiet` passed.
- 2026-06-03 `npm run build` passed in `inbox-app/`.
- 2026-06-03 local FastAPI `/api/inbox/conversations` returned `[]`; React dev server responded HTTP 200 at `http://127.0.0.1:5173`.
- In-app Browser visual verification was not completed because the Browser plugin did not expose the required Node `js` execution tool in this session.
- 2026-06-03 `npm run build` passed after inbox filter buttons were changed from horizontal scroll to wrapping layout and mobile two-column controls.
- 2026-06-03 local focused auth/inbox tests passed: `pytest tests/test_auth.py tests/test_inbox.py -q` reported 10 tests passed.
- 2026-06-03 local full `pytest -x` passed after single-admin inbox auth: 76 tests passed.
- 2026-06-03 local `ruff check .` passed after single-admin inbox auth.
- 2026-06-03 local `mypy src` passed after single-admin inbox auth: no issues in 27 source files.
- 2026-06-03 `npm run build` passed in `inbox-app/` after login/logout UI and authenticated fetches.
- 2026-06-03 local focused `ruff check` passed for inbox notification service, Telegram/VK bot wiring, config, and notification tests.
- 2026-06-03 local `mypy src` passed after inbox Telegram notifications: no issues in 28 source files.
- 2026-06-03 local focused pytest passed after inbox Telegram notifications: `tests/test_inbox_notifications.py tests/test_inbox.py tests/test_telegram_bot.py tests/test_vk_bot.py -q` reported 20 tests passed.
- 2026-06-03 local full `ruff check .` passed after inbox Telegram notifications.
- 2026-06-03 local full `pytest -x` passed after inbox Telegram notifications: 80 tests passed.
- 2026-06-03 `npm run build` passed in `inbox-app/` after direct conversation links from notifications.
- 2026-06-03 local inbox notification bot setup completed: Telegram `getUpdates` returned a private admin chat, `.env` was updated with notification settings, `.env` is git-ignored, and a direct test `sendMessage` returned `ok=true`.
- 2026-06-03 local focused `ruff check` passed for Inbox database backend/API/tests.
- 2026-06-03 local `mypy src` passed after Inbox database section: no issues in 29 source files.
- 2026-06-03 local focused pytest passed after Inbox database section: `tests/test_inbox_database.py tests/test_inbox.py -q` reported 9 tests passed.
- 2026-06-03 local full `ruff check .` passed after Inbox database section.
- 2026-06-03 local full `pytest -x` passed after Inbox database section: 84 tests passed.
- 2026-06-03 `npm run build` passed in `inbox-app/` after adding the `База` section.
- 2026-06-03 browser verification passed locally for Inbox `База`: login, desktop database view, and mobile database layout rendered correctly. Local dev servers on ports 8000/5173 were stopped after verification.
- 2026-06-03 local `npm run build` passed after configuring the React app for `/inbox` production serving.
- 2026-06-03 local FastAPI static serving smoke passed: `GET http://127.0.0.1:8000/inbox` returned HTTP 200 and referenced `/inbox/assets/...`.
- 2026-06-03 local `ruff check .`, `mypy src`, `pytest -x`, `npm run build`, and `docker compose -f docker-compose.prod.yml config --quiet` passed before production deploy; pytest reported 84 tests passed.
- 2026-06-03 production deploy completed for Inbox/auth/notifications/database and `/inbox` static serving. Archive included untracked Inbox files and `inbox-app/dist`, was extracted to `/opt/funnelhub`, Docker images were rebuilt, migration `0003_inbox_statuses` applied, and `app`, `telegram-bot`, and `funnel-worker` were recreated.
- 2026-06-03 production `.env` was configured with Inbox admin auth, session secret, notification bot settings, and `INBOX_APP_URL=https://bot.aisukam.ru/inbox`.
- 2026-06-03 production smoke passed: public `https://bot.aisukam.ru/inbox` returned HTTP 200 with `/inbox/assets/...`, `POST /api/auth/login` returned HTTP 200 using generated admin credentials, and authenticated `GET /api/inbox/database/leads?limit=5` returned HTTP 200 with an `items` field.
- 2026-06-03 production service check passed after deploy: `app`, `telegram-bot`, `funnel-worker`, `postgres`, and `redis` were running; latest logs showed app startup, Telegram polling, and a clean funnel-worker pass.
- Started `email-provider` as a provider-agnostic MVP.
- Added `src/funnelhub/services/email_messaging.py` with `EmailProviderClient`, `DebugEmailProviderClient`, `send_email_text_message(...)`, lazy unsubscribe token generation, unsubscribe footer injection, outbound `messages` persistence, and provider failure marking.
- Added public `GET /email/unsubscribe/{token}` in `src/funnelhub/api/email.py`; it updates `email_subscriptions`, logs `email.unsubscribed`, and is idempotent.
- Extended funnel steps with optional `subject` and wired `channel: email` into `run_due_funnel_once(...)` via optional `email_client`.
- Added `EMAIL_PROVIDER`, `EMAIL_FROM_EMAIL`, `EMAIL_FROM_NAME`, and `EMAIL_DEFAULT_SUBJECT` settings/env example.
- Added `.harness/docs/email-provider.md` and updated `.harness/docs/funnel-engine.md`.
- Verification passed locally after the email layer: focused email pytest reported 11 tests passed; full `ruff check .`, `mypy src`, and `pytest -x` passed with 90 tests; `docker compose -f docker-compose.prod.yml config --quiet` exited successfully with local unset-variable warnings.
- Extended Inbox `База` lead detail for the GetCourse-style fields from the screenshots:
  - `src/funnelhub/services/getcourse_webhook.py` now accepts registration type, GetCourse created/last-activity timestamps, regular advertising `utm_*`, `VK-ID`, GetCourse group IDs, partner/manager fields, birthday/age/gender/note, and mailing categories.
  - These values are stored without a migration via existing `leads`, `lead_utm`, `lead_custom_fields`, `lead_external_ids`, and raw payload JSONB.
  - `src/funnelhub/services/inbox_database.py` and `src/funnelhub/api/inbox.py` now expose structured detail sections: profile fields, contacts, messenger identities, external IDs, UTM snapshots, custom fields, consents, email subscriptions, funnel states, recent messages, and raw GetCourse JSON.
  - `inbox-app/src/App.tsx` renders these sections as accordions and the database export button now downloads XLSX.
  - Added `/api/inbox/database/leads/export.xlsx` with human-readable Russian column headers while keeping the old CSV endpoint.
- Verification passed after Inbox extended fields/XLSX work:
  - `ruff check .` passed.
  - `mypy src` passed.
  - `pytest tests/test_getcourse_webhook.py tests/test_inbox_database.py -q` passed: 27 tests.
  - `pytest -x` passed: 93 tests.
  - `npm run build` passed in `inbox-app/`.
  - `docker compose -f docker-compose.prod.yml config --quiet` passed with local unset-variable warnings.
- Production deploy completed for the combined email-layer plus Inbox extended fields/XLSX release:
  - Uploaded archive with untracked email files and `inbox-app/dist` to `/opt/funnelhub`.
  - Preserved production `.env` but forced `EMAIL_PROVIDER=disabled`; real email provider remains unconnected.
  - Rebuilt and recreated `app`, `telegram-bot`, and `funnel-worker`.
  - Production Alembic current is `0003_inbox_statuses (head)`.
  - Public `https://bot.aisukam.ru/health` returned HTTP 200 with `{"status":"ok","service":"FunnelHub"}`.
  - Public `https://bot.aisukam.ru/inbox` returned HTTP 200 and referenced `/inbox/assets/...`.
  - Unauthenticated `https://bot.aisukam.ru/api/inbox/database/leads/export.xlsx` returned HTTP 401, confirming the new XLSX route exists behind auth.
  - Logs showed Telegram polling started and funnel-worker completed a clean pass.
  - Production rollback smoke called `ingest_getcourse_webhook(...)` with extended GetCourse fields, verified `getcourse_groups`/`vk_id`, regular `form` UTM snapshots, and non-empty XLSX bytes, then rolled back without persisting the smoke lead.
- Changed Telegram/VK funnel day scheduling in `src/funnelhub/services/funnel_engine.py`: `delay: Nd` now schedules for 09:00 MSK (fixed UTC+3) on the target local calendar day instead of `now + 24h`; `0m`, minute/hour delays, and questionnaire `reminder_delay: 5m` remain relative.
- Added day-scheduling regression coverage in `tests/test_funnel_engine.py`.
- Local verification after the scheduling fix passed:
  - `ruff check .`
  - `mypy src`
  - `pytest tests/test_funnel_engine.py tests/test_funnel_runner.py tests/test_funnel_answers.py -q` with 22 tests.
  - `pytest -x` with 96 tests.
  - `docker compose -f docker-compose.prod.yml config --quiet` with only existing local unset-variable warnings.
- Production deploy completed for the scheduling fix:
  - Uploaded project archive to `/opt/funnelhub`.
  - Rebuilt and recreated `app`, `telegram-bot`, and `funnel-worker`.
  - Preserved `EMAIL_PROVIDER=disabled`.
  - Alembic remained `0003_inbox_statuses (head)`.
  - Public `https://bot.aisukam.ru/health` returned HTTP 200 with `{"status":"ok","service":"FunnelHub"}`.
  - Container smoke confirmed `schedule_after_delay(2026-06-04T14:30Z, "1d")` returns `2026-06-05T06:00:00Z`, i.e. 09:00 MSK.
  - Two already-active daily pending production funnel states were adjusted from the old `+24h` schedule to 09:00 MSK on their existing target local date.
  - Latest logs showed Telegram polling running and `funnel-worker` completing a clean pass.
- Implemented and deployed a concrete Unisender Go email provider adapter:
  - `src/funnelhub/services/email_messaging.py` now includes `UnisenderGoEmailProviderClient`.
  - `src/funnelhub/config.py` has `EMAIL_REPLY_TO_EMAIL`, `EMAIL_REPLY_TO_NAME`, `EMAIL_UNISENDER_GO_API_KEY`, and `EMAIL_UNISENDER_GO_API_URL`.
  - `.env.example` and `.harness/docs/email-provider.md` document `EMAIL_PROVIDER=unisender_go`.
  - Adapter sends JSON to `https://goapi.unisender.ru/ru/transactional/api/v1/email/send.json` with `X-API-KEY`, from/reply-to fields, plaintext body, idempotence key, FunnelHub unsubscribe URL, and scalar metadata.
- Local verification after Unisender Go adapter:
  - `ruff check src/funnelhub/services/email_messaging.py src/funnelhub/config.py tests/test_email_messaging.py` passed.
  - `pytest tests/test_email_messaging.py tests/test_funnel_runner.py -q` passed: 15 tests.
  - `mypy src` passed.
  - `ruff check .` passed.
  - `pytest -x` passed: 100 tests.
  - `docker compose -f docker-compose.prod.yml config --quiet` passed with existing local unset-variable warnings.
- Production deploy for the adapter completed: code was uploaded to `/opt/funnelhub`, images were rebuilt, and `app`, `telegram-bot`, and `funnel-worker` were recreated.
- Production `.env` was temporarily set to `EMAIL_PROVIDER=unisender_go` with `EMAIL_FROM_EMAIL=info@aisukam.ru`, `EMAIL_FROM_NAME=Айсу Кам`, `EMAIL_REPLY_TO_EMAIL=info@aisukam.ru`, and the supplied Unisender Go API key.
- Production smoke result: app health was OK and settings loaded provider/from/reply-to/key presence correctly, but the real Unisender test send to `aisukam-info@yandex.ru` failed with HTTP 401, code `114`, message `user not found`.
- Interpretation: DNS/domain/DKIM are not the problem; Unisender Go does not recognize the supplied API key for that API/account. User must provide a fresh API key from the Unisender Go `API-ключ` page, ideally after rotating the previously pasted key.
- After the failed auth smoke, production `EMAIL_PROVIDER` was restored to `disabled` so no automatic email attempts fail while waiting for a valid key. The Unisender env fields remain present in production `.env`; public `/health` returned OK after the rollback.
- User then provided a second key from the Unisender Go `API-ключ` page. Production env was updated and the real send was retried, but Unisender returned the same HTTP 401 / code `114` / `user not found`. Provider was restored to `disabled` again and public `/health` returned OK.
- Likely next user-side action: ensure the `Доступ к API` toggle is on and press `Сохранить` in the Unisender Go API-key page, then ask Unisender support why both keys return code `114 user not found` from `https://goapi.unisender.ru/ru/transactional/api/v1/email/send.json` despite the domain being verified.
- User confirmed they had not pressed `Сохранить` after generating the second API key. After saving, production was updated with the same key again and the real Unisender smoke succeeded:
  - `EMAIL_PROVIDER=unisender_go`
  - from/reply-to `info@aisukam.ru`
  - recipient `aisukam-info@yandex.ru`
  - Unisender response `status=success`, `job_id=1wUxhG-000zTe-9m4z`, `emails=['aisukam-info@yandex.ru']`
  - `app`, `telegram-bot`, and `funnel-worker` were running after the smoke.
  - Production remains enabled with `EMAIL_PROVIDER=unisender_go`.
- Implemented and deployed the Aisu Kam email chain:
  - New funnel file: `content/funnels/aisu_email.yml`.
  - Funnel key: `aisu_email_sequence`.
  - 13 daily email steps copied from the Telegram/VK scenario starting at the second-day CTA content.
  - Every step has `delay: 1d`, so the existing scheduler sends at 09:00 MSK on the next local calendar day.
  - All CTA buttons point to `https://aisukam.ru/courses`.
  - GetCourse webhook and `/join/getcourse` now start this email funnel in parallel when the lead has a subscribed email; repeated webhooks reuse the same email funnel state.
  - Worker loads `DEFAULT_EMAIL_FUNNEL_PATH` only when `EMAIL_PROVIDER` creates an email client, avoiding failed email passes if provider is disabled later.
- Added HTML email rendering:
  - Plain text fallback still includes button URLs and unsubscribe URL.
  - HTML body renders paragraphs, green CTA buttons, unsubscribe link, and the signature text `С любовью, Айсу Кам. Школа искусства преображения жизни "Сатья-Юга"`.
  - `EMAIL_SIGNATURE_IMAGE_URL` controls the round portrait in the signature.
- Generated the requested mirrored round portrait from `C:/Users/circlealgorythm/Pictures/Ксюша/2E1Hr_0f5X7R6KjP_JNZ_xw2AMlj3j25oRCl7DTo6-9N0E_xAjgdEZoeCC7AcKCl3HCRpxBf3f4pS1y9PD7QxOgC.jpg`.
  - Local output: `public/assets/email/aisu-kam-signature.png`.
  - Production URL: `https://bot.aisukam.ru/assets/email/aisu-kam-signature.png`.
  - FastAPI now mounts `public/assets` at `/assets`, and Dockerfile copies `public/`.
- Production `.env` now includes:
  - `DEFAULT_EMAIL_FUNNEL_PATH=content/funnels/aisu_email.yml`
  - `EMAIL_SIGNATURE_IMAGE_URL=https://bot.aisukam.ru/assets/email/aisu-kam-signature.png`
  - `EMAIL_PROVIDER=unisender_go`
  - `EMAIL_FROM_EMAIL=info@aisukam.ru`
  - `EMAIL_FROM_NAME=Айсу Кам`
  - `EMAIL_REPLY_TO_EMAIL=info@aisukam.ru`
  - `EMAIL_REPLY_TO_NAME=Айсу Кам`
- Verification after email sequence/signature work:
  - Local `ruff check .` passed.
  - Local `mypy src` passed.
  - Targeted pytest for email messaging, funnel runner, GetCourse webhook, and email funnel definition passed: 37 tests.
  - Full local `pytest -x` passed: 101 tests.
  - `docker compose -f docker-compose.prod.yml config --quiet` passed with existing local unset-variable warnings.
  - Production `/health` returned HTTP 200.
  - Production signature PNG returned HTTP 200 and `image/png`.
  - Production app loaded `EMAIL_PROVIDER=unisender_go`, `EMAIL_SIGNATURE_IMAGE_URL`, and `aisu_email_sequence` with 13 steps.
  - Production rollback GetCourse ingest smoke created an unsaved `aisu_email_sequence` state at `day_02_step_08`, due `2026-06-05 06:00:00+00:00` (09:00 MSK), then rolled back without persisting the test lead.
  - Production `funnel-worker` logged repeated clean passes with no errors after deploy.
- User later asked to move the email signature portrait higher inside the circle. The local and production `public/assets/email/aisu-kam-signature.png` crop was adjusted so the mirrored hair crown sits at the top edge without cutting the face. Production `app` was rebuilt/recreated, public `/health` returned HTTP 200, and the PNG URL returned HTTP 200 with `image/png`.
- 2026-06-06 fixed VK bot treating raw text payload as a start token, which caused funnel restarts when clicking questionnaire buttons. Updated funnel_answers.py to strictly validate pending_question_key, preventing old or out-of-order Telegram buttons from advancing the funnel state and dropping the next scheduled step. Deployed fixes to production server and restarted docker containers.
- 2026-06-06 implemented lead deletion in Inbox UI. Added DELETE /api/inbox/database/leads/{lead_id} endpoint which performs a hard delete of the lead and all associated records. Added 'Удалить лида' button to Inbox React application.
- 2026-06-06 fixed background DB connection drops. Added pool_pre_ping=True to SQLAlchemy create_async_engine config in src/funnelhub/db/session.py to prevent InterfaceError from crashing background workers.
