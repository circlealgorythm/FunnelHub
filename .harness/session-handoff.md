# Session Handoff

## Current Status

- VK personal wall autoposting has been removed from the active product/code path after the user
  decided not to operate proxy-bound VK user tokens. Current public Autoposting supports only
  Telegram channel and VK group wall.
- Removed active code/UI/config for `vk_personal`: backend supported channels are now
  `telegram,vk`, the worker only creates the group VK client, `AUTOPOST_VK_PERSONAL_*` fields were
  removed from code and `.env.example`, and Inbox no longer renders "VK личная".
- Production cleanup completed: `/opt/funnelhub/.env` has zero `AUTOPOST_VK_PERSONAL_*` keys,
  services were restarted, and active `vk_personal` publication rows were cancelled. Legacy
  published/cancelled `vk_personal` history rows remain in the DB for audit/history only.
- Current media behavior remains unchanged: one attached image is used for VK group wall posts;
  Telegram channel autoposting remains text-only.
- Latest verification for this removal: local focused `ruff` passed, `mypy src` passed,
  `npm run build` passed, `tests/test_autopost_external_urls.py -q` passed, channel-normalization
  smoke rejects `vk_personal`,
  `tests/test_autoposts.py::test_autopost_rejects_personal_vk_channel -q` passed, production
  `/health` returned OK, in-container smoke shows
  `personal_env_count=0`, `has_personal_setting=False`, `supported_channels=telegram,vk`,
  `vk_personal_rejected=true`, the deployed JS contains no `VK личная`/`vk_personal`, and DB smoke
  shows `active_vk_personal_publications=0`. Fresh `funnel-worker` logs after restart showed only
  normal `Funnel runner pass completed` entries.
- Durable post-submit tasks for GetCourse lead ingestion are implemented locally but not deployed.
- `/join/getcourse` and `/webhooks/getcourse` now save/update the lead, create/reuse the bot-link
  token, start the email funnel state, enqueue post-submit tasks, commit, and return without
  waiting for GetCourse Export API or Unisender Go admin notification sends.
- New DB model/table: `lead_post_submit_tasks`, migration
  `20260616_01_add_lead_post_submit_tasks.py`.
- New worker service: `src/funnelhub/services/lead_post_submit_tasks.py`.
  `funnel-worker` now runs `run_due_lead_post_submit_tasks_once(...)` each loop.
- Queued task behavior:
  - `getcourse_profile_enrichment` is queued only when GetCourse API settings are configured,
    deduped by lead id, and retried on `api_failed` / `profile_not_found`.
  - `lead_application_notification` is queued only when `LEAD_NOTIFICATION_EMAIL_TO` is set; the
    existing notification cooldown/event guard still prevents duplicate admin emails.
- UI close-button prevention for the public form was implemented in sibling repo
  `C:\Users\circlealgorythm\Documents\VibeCoding\AisuKam_site`:
  - `src/main.tsx` now computes `isSubmitting = submitted && !submissionComplete`;
  - close via X, backdrop click, and Escape is ignored while `isSubmitting`;
  - the close button is disabled and gets a submission-specific accessible label while blocked;
  - closing works again after success or failure.
- Verification for this local slice after Docker/PostgreSQL was started:
  - focused new GetCourse tests passed: 3 passed;
  - full `tests/test_getcourse_webhook.py` passed: 35 passed;
  - full `.venv\Scripts\pytest.exe -x` passed: 149 passed, 5 skipped;
  - `ruff check .`, focused ruff for changed files, `mypy src`, Python compile for changed
    modules, `alembic heads`, and `git diff --check` passed;
  - clean temporary-DB Alembic upgrade from empty DB to `20260616_01 (head)` passed;
  - direct `alembic upgrade head` against the existing local DB was not meaningful because that
    DB already had later tables created by tests while `alembic_version` was behind;
  - public site `npm run build` passed with only the existing Vite large-chunk warning.
- Autoposting VK personal wall and VK image attachments are implemented and deployed.
- Public Autoposting UI now offers `Telegram`, `VK группа`, and `VK личная`.
- `VK личная` publishes to owner id `258149228` using the production-only
  `AUTOPOST_VK_PERSONAL_ACCESS_TOKEN`; the token came from local `.secrets/vk-personal.env`, was
  written to `/opt/funnelhub/.env`, and must not be printed or committed.
- Autoposting image upload accepts one JPEG/PNG/WebP file. The file is stored temporarily in the
  shared `autopost_uploads` Docker volume at `/app/uploads/autoposts`, used for VK wall photo
  upload, then deleted after all selected publication rows are published or when the post is
  cancelled.
- Product decision: Telegram does not receive the image, because the user does not want separate
  photo/text messages. Telegram remains text-only; VK group and VK personal receive text+image.
- `deploy_files.py` now uploads root deployment files (`Dockerfile`, `docker-compose.prod.yml`,
  `pyproject.toml`, `alembic.ini`) in addition to source/tests/dist, because compose changes such
  as shared volumes must reach production.
- Latest production verification for this slice: public `/health` OK; services running;
  config smoke showed personal VK owner configured and token present; container
  `pytest tests/test_autoposts.py -q` passed with 9 tests; bundle smoke found `VK личная` and the
  VK-only image hint; worker logs show normal passes. No real publication smoke was sent.
- `autoposting-public-platforms` is now completed/deployed under the narrowed scope:
  FunnelHub directly publishes public posts only to Telegram and VK. Odnoklassniki, YouTube, and
  Zen are excluded.
- Production `.env` was backed up and updated from the user-provided file. Do not print or commit
  the VK token. Config smoke in the container confirms Telegram chat id normalizes to
  `-1001649567909`, VK group id is `211582267`, VK owner id resolves to `-211582267`, the VK token
  is present, and `AUTOPOST_FOLLOWUP_MARKER` should be `#aisukam`.
- Inbox Autoposting UI shows only `Telegram` and `VK` public targets. The backend rejects `zen`
  as an unsupported autopost channel.
- Autoposting create modal has a scrollable body and sticky footer so buttons remain reachable on
  small screens.
- Production `funnel_runner` permanent delivery errors were diagnosed, fixed, deployed, and
  verified. Old noisy causes were VK button labels over 40 chars, VK users without message
  permission, Unisender Go "No valid recipients", and due email states without a subscribed email
  subscription.
- The fix preserves funnel logic: successful sends still advance as before; transient failures
  still fail/retry as before; only recognized permanent delivery errors pause the same
  `FunnelState` with `next_run_at=None`, `paused_reason=permanent_delivery_error`, and the same
  `current_step_key`.
- VK labels are truncated only in the VK keyboard payload. The original button text remains in
  message metadata.
- Production deploy completed through `deploy_files.py`. `/health` is OK, services are running,
  and a fresh worker log window after accumulated pauses showed only clean
  `Funnel runner pass completed` entries.
- `autoposting-followup` and `autoposting-followup-hashtag-routing` are implemented,
  verified, and deployed to production.
- Production is at Alembic `20260612_01 (head)`.
- Public `/health` is OK, `/inbox` serves the bundle containing "Фоллоу-ап", and production
  services `app`, `funnel-worker`, `telegram-bot`, `postgres`, and `redis` are running.
- Follow-up production smoke:
  - temporary completed lead created;
  - scheduled follow-up post created with pending delivery;
  - smoke data cleaned up successfully.
- Marker-routing production smoke:
  - `AUTOPOST_FOLLOWUP_MARKER` default is now `#aisukam`;
  - `AUTOPOST_FOLLOWUP_STRIP_MARKER` default is `true`;
  - marked public autopost created exactly one `FunnelFollowupPost`;
  - private follow-up body had the marker stripped;
  - Telegram/VK delivery rows were created;
  - smoke data cleaned up successfully.
- Worker log tail still shows unrelated pre-existing `funnel_runner` errors for VK permissions,
  long VK button labels, and invalid/no email recipients. No follow-up/marker-routing traceback was
  observed in smoke.
- `current_feature` is now `null`; WIP is empty.
- Remaining Autoposting feature-list item is `autoposting-public-platforms`.

## Latest Verification

- `.venv\Scripts\pytest.exe tests\test_autoposts.py -q` passed: 7 passed.
- `npm run build` passed in `inbox-app/`.
- `.venv\Scripts\pytest.exe tests\test_vk_messaging.py tests\test_funnel_runner.py -q` passed:
  18 passed.
- `.venv\Scripts\pytest.exe -x` passed: 144 passed, 5 skipped.
- `.venv\Scripts\ruff.exe check .` passed.
- `.venv\Scripts\mypy.exe src` passed.
- `git diff --check` passed.
- Production config/UI/backend smoke passed after `autoposting-public-platforms` deploy:
  marker is `#aisukam`, supported public channels are `telegram,vk`, no `ZEN_*` env keys are
  present, the frontend image has one current JS asset with no `Дзен`/`Telegram + Дзен` strings,
  backend rejects `zen`, a rollback-only TG/VK `#aisukam` autopost creates as `scheduled`, and no
  real public test post was sent.
- `deploy_files.py` now clears remote `inbox-app/dist` before uploading a fresh frontend build, so
  old JS chunks do not remain in production images.
- Production health/log smoke passed after `funnel_runner` deploy.
- Previous Autoposting verification remains below:
- `.venv\Scripts\pytest.exe -x` passed: 137 passed, 5 skipped.
- `.venv\Scripts\pytest.exe tests/test_autoposts.py tests/test_followup_posts.py -q` passed:
  7 passed.
- `npm run build` passed in `inbox-app/`.
- `git diff --check` passed.
- `docker compose -f docker-compose.prod.yml config --quiet` passed with existing local
  unset-variable warnings.
- Both production deploy commands completed successfully through `deploy_files.py`.

- `autoposting-followup` is locally implemented and verified.
- Added backend schema and migration `20260612_01_add_followup_posts.py`:
  - `followup_posts`;
  - `followup_deliveries`;
  - unique delivery guard on `followup_post_id + lead_id + channel`.
- Added `/api/inbox/followup-posts` admin API:
  - list;
  - create;
  - detail;
  - cancel;
  - recipient preview.
- Added follow-up worker pass in `funnel_worker.py`.
- Added Inbox tab "Фоллоу-ап" with create modal, recipient preview, list, detail/history modal,
  and cancel action.
- Recipient rule implemented for this slice:
  - materialize recipients at post creation time;
  - require completed `funnel_states` for `aisu_consultation`;
  - require `funnel_states.status = completed` and `completed_at is not null`, so active or
    incomplete scenario states are excluded even when the lead is subscribed;
  - require active subscribed Telegram/VK `messenger_identities`;
  - if a lead has both subscribed channels and both are selected, create two delivery rows;
  - if identity unsubscribes before sending, worker marks that delivery `skipped_unsubscribed`.
- Marker routing is already complete. Next Autoposting work should start from
  `autoposting-public-platforms` or from a new feature if follow-up delivery rules need to change.

## Verification

- `.venv\Scripts\ruff.exe check .` passed.
- `.venv\Scripts\mypy.exe src` passed.
- `.venv\Scripts\pytest.exe tests/test_followup_posts.py -q` passed: 3 passed.
- Follow-up tests explicitly cover that a subscribed lead with active/incomplete
  `aisu_consultation` is not selected.
- `.venv\Scripts\pytest.exe -x` passed: 136 passed, 5 skipped.
- `npm run build` passed in `inbox-app/`.
- `git diff --check` passed.
- `docker compose -f docker-compose.prod.yml config --quiet` passed with existing local
  unset-variable warnings.

## Notes / Next Steps

- Follow-up marker routing is deployed. The marker is `#aisukam` by default and is configurable
  through `AUTOPOST_FOLLOWUP_MARKER`.
- Current follow-up recipient materialization happens at creation time. Leads who complete the
  18-day funnel after a follow-up post is created will not be backfilled into that existing post;
  that behavior can be changed later if product requirements need rolling delivery.

- User confirmed that both Autoposting MVP and email-provider are already deployed.
- `.harness/feature-list.json` was synchronized:
  - `current_feature` is now `null`;
  - `email-provider` is `completed`;
  - existing `autoposting` is treated as completed public Autoposting MVP;
## Current Autoposting Handoff

- Implemented and deployed the requested public Autoposting additions:
  - `vk_personal` publication target using `AUTOPOST_VK_PERSONAL_ACCESS_TOKEN` and
    `AUTOPOST_VK_PERSONAL_OWNER_ID=258149228`;
  - VK-only image upload support for Autoposting posts, stored in the shared
    `/app/uploads/autoposts` volume and removed after all publication rows finish or the post is
    cancelled;
  - visible UI state for attached images in the create modal, Autoposting list, and detail modal;
  - explicit "Сразу" / "По времени" schedule mode; "Сразу" submits without `scheduled_at` and is
    picked up by the next worker pass.
- Telegram images were intentionally not added: user decided Telegram should remain text-only if
  the image cannot be posted together with the text in the desired format.
- Production deploy completed through `deploy_files.py`; `app`, `funnel-worker`, and
  `telegram-bot` were rebuilt/recreated and are running.
- Diagnosed the current live `vk_personal` error:
  - the first token value included redirect fragment data such as `&expires_in=...`; it was
    locally and remotely normalized to the raw access token without printing the secret;
  - after normalization, VK `users.get` from the production worker returns
    `User authorization failed: access_token was given to another ip address`;
  - this means the token was bound to the browser/client IP used during OAuth and cannot be used
    from the VPS. A replacement VK user token usable from the production server IP is required.
- Latest checked failed post: `6f0f299e-d7b2-4d41-89c1-46cce326f8a3`, title `21 июня будет
  Летнее Солнцестояние`, channel `vk_personal`, later became `published` after VK returned
  `{"post_id": 777}` from `wall.post`.
- Follow-up investigation for that row:
  - production DB has `status=published`, `external_post_id=777`, and no publication error;
  - the full VK URL is `https://vk.com/wall258149228_777`;
  - the same personal token currently cannot perform server-side `users.get`, `wall.getById`, or
    `wall.get` because VK returns `access_token was given to another ip address`;
  - public unauthenticated `wall.getById` requires a token for this wall, and the group token
    cannot call wall read methods for a personal wall;
  - therefore FunnelHub can prove VK accepted `wall.post`, but cannot currently prove whether the
    item is visible/deleted/hidden on VK without a valid server-usable user token.
- Important implementation decision after inspecting VK privacy settings: `vk_personal` publishing
  now calls `wall.post` without `owner_id`, so VK uses the current user from the access token. This
  avoids making the API request look like an explicit post "to a profile wall" and should not
  require opening "Кто может публиковать посты в моём профиле" to anyone else. Keep
  `AUTOPOST_VK_PERSONAL_OWNER_ID=258149228` only for link construction.
- VK personal autoposting now supports `AUTOPOST_VK_PERSONAL_PROXY_URL`. The proxy is passed only
  to the personal VK HTTP client used by the autopost worker; VK group/bot traffic remains direct.
  Use a paid dedicated static HTTP(S)/ISP proxy and store the full proxy URL only in deployment
  secrets, for example `http://user:password@host:port`. Do not use random/free proxies for VK
  because the user token and OAuth browser session depend on that IP path.
- The current failed row `e9d99318-9c1c-4311-995f-3ee69bb76d82` was restored to `failed` after an
  attempted production `tests/test_autoposts.py` run picked it up as real due work. Do not run the
  full autopost runner tests against the live production DB while real due/failed autoposts exist.
- Deployed an admin/API visibility improvement: `AutopostPublicationResponse` now includes
  `external_post_url`, and the Autoposting detail modal renders VK external IDs as clickable links.
  Existing rows derive the link from configured owner ids. For `vk_personal`, the link now uses
  VK's profile-modal format, so the current row shows
  `https://vk.com/id258149228?w=wall258149228_777` instead of direct `wall258149228_777`.

## Current Verification

- `.venv\Scripts\ruff.exe check deploy_files.py src/funnelhub/services/autopost_runner.py
  src/funnelhub/services/autopost_media.py src/funnelhub/services/vk_messaging.py
  src/funnelhub/api/autoposts.py src/funnelhub/funnel_worker.py tests/test_autoposts.py` passed.
- `.venv\Scripts\mypy.exe src` passed.
- `npm run build` passed in `inbox-app/`.
- `git diff --check` passed, with only existing LF/CRLF working-copy warnings.
- Production smoke passed:
  - `app`, `funnel-worker`, and `telegram-bot` are running;
  - in-container `/health` returned `200 {"status":"ok","service":"FunnelHub"}`;
  - deployed Inbox JS contains "Отправить сразу", "Прикреплено:", and "VK изображение";
  - current `vk_personal` publication serializes
    `external_post_url=https://vk.com/id258149228?w=wall258149228_777`;
  - code smoke confirms personal publishing uses `owner_id=None` and `require_owner_id=False`;
  - in-container `pytest tests/test_autopost_external_urls.py tests/test_autoposts.py -q`
    passed: 10 passed.
- Latest proxy-support verification: focused local `ruff` passed for changed files, `mypy src`
  passed, local settings smoke passed for blank and non-blank
  `AUTOPOST_VK_PERSONAL_PROXY_URL`, production `/health` returned OK, and an in-container settings
  smoke returned `proxy_setting_ok`.

## Current Notes / Next Steps

- Do not print or commit `.secrets/vk-personal.env`; `.secrets/` is ignored.
- To fix `vk_personal`, generate a VK user token that VK accepts from the VPS IP, then update
  `AUTOPOST_VK_PERSONAL_ACCESS_TOKEN` in `/opt/funnelhub/.env` and restart `funnel-worker`.
- No real publication smoke was sent during this slice.

## Previous Context

  - new pending Autoposting feature slices were added for follow-up posts, hashtag routing, and
    additional public platforms.
- User confirmed the product rule for Autoposting:
  - public Autoposting and private follow-up after the main funnel remain separate flows;
  - if a public autopost contains the configured follow-up hashtag/marker, FunnelHub should
    create/reuse a separate follow-up post for private bot delivery;
  - public publication rows and private follow-up delivery rows must stay separate, with separate
    statuses, retries, histories, and dedupe rules.
- Work should continue one feature at a time, with focused tests and Harness progress/handoff
  updates after each feature.

- User asked whether Harness should be expanded now that the project grew. After checking the
  Harness templates resource, the project was extended with targeted operational docs rather than
  a full advanced pack:
  - `.harness/docs/quality.md`;
  - `.harness/docs/security.md`;
  - `.harness/docs/reliability.md`;
  - `.harness/clean-state-checklist.md`.
- `.harness/init.md` now points future sessions to those files only when relevant: production
  behavior, security-sensitive work, workers/queues/webhooks, or non-trivial closeout.

- User clarified the next Autoposting target model. Created
  `.harness/docs/autoposting.md` as the source-of-truth roadmap.
- The documented plan splits Autoposting into two separate entities/flows:
  - public platform publishing: Telegram channel and VK group wall;
  - internal follow-up posts: private Telegram/VK bot messages sent only to leads who completed
    the 18-day `aisu_consultation` messenger funnel.
- VK Video and YouTube video upload are out of scope for the public text/post publishing flow.
  Odnoklassniki, Zen, and YouTube community posts are out of the current scope.
- Internal follow-up posts should use completed `funnel_states` plus subscribed
  `messenger_identities`, with per-lead/per-channel delivery history and duplicate protection.

- User then asked to verify the recently implemented Unisender Go delivery/open/click/bounce/
  complaint/unsubscribe webhooks and fix defects if any.
- Existing Unisender Go webhook implementation was present and covered the configured
  `events_by_user` format with `event_data.status`, auth hash validation, idempotent `events`,
  message delivery/read/failure updates, and subscription stop behavior.
- Hardened the parser to avoid silent skips for provider naming variants:
  - accepts `Events` as well as `events`;
  - accepts `email_status` and `Status` as status fields;
  - accepts event-name-only forms such as `unsubscribe` and `ok_link_visited`;
  - maps aliases like `ok_delivered`, `ok_read`, `ok_link_visited`, `err_will_retry`.
- Deployed the webhook hardening to production. `/health` and
  `/webhooks/email/unisender-go` are OK, services are running, and in-container smoke confirms
  aliases normalize to `opened`, `clicked`, and `unsubscribed`.

- Previous Autoposting status remains deployed:
  app/inbox bundle has "Автопостинг", Alembic is at `20260611_01 (head)`, and services are
  running.

## Verification

- 2026-06-16 durable lead post-submit deployment:
  - production deploy completed through `deploy_files.py`;
  - Alembic current is `20260616_01 (head)`;
  - `app`, `funnel-worker`, `telegram-bot`, `postgres`, and `redis` are running;
  - public `https://bot.aisukam.ru/health` returned `{"status":"ok","service":"FunnelHub"}`;
  - phone-only `/webhooks/getcourse` smoke created lead
    `09481997-eea2-40ec-b066-0075cd06edd6` immediately;
  - production DB showed the saved phone contact and a queued/processed
    `getcourse_profile_enrichment` task; the task failed only because the fake smoke phone has no
    GetCourse profile, which is expected retry behavior;
  - the smoke lead, queued task, and related event were cleaned up by exact lead id;
  - recent app/worker/bot logs showed no lead-submission traceback. An unrelated `vk_personal`
    autopost warning about an invalid VK token remains.
- Public site UI patch:
  - `AisuKam_site` build passed earlier;
  - archive ready at
    `C:\Users\circlealgorythm\Documents\VibeCoding\AisuKam_site\aisukam-submit-close-lock-patch-20260616.zip`;
  - `aisukam.ru` resolves to a different hosting IP than `bot.aisukam.ru`; no site files were
    changed on hosting, per user instruction. User will upload the archive manually.

- `.venv\Scripts\ruff.exe check .` passed.
- `.venv\Scripts\mypy.exe src` passed.
- `pytest tests\test_email_provider_webhooks.py -q` passed: 5 passed.
- `pytest -x` passed: 133 passed, 5 skipped.
- `docker compose -f docker-compose.prod.yml config --quiet` passed with existing local unset
  variable warnings.
- Production smoke:
  - `https://bot.aisukam.ru/health` returned OK;
  - `https://bot.aisukam.ru/webhooks/email/unisender-go` returned OK;
  - production service state is running for app, worker, bot, postgres, redis;
  - in-container alias smoke returned `opened`, `clicked`, `unsubscribed`.

## Notes / Next Steps

- The live Unisender Go configuration is documented as `event_format=json_post` with
  `email_status=delivered/opened/clicked/unsubscribed/subscribed/soft_bounced/hard_bounced/spam`.
  The hardening keeps that primary path intact and only broadens accepted variants.
- Production worker logs may still show unrelated email funnel send errors for invalid or
  unsubscribed recipients; webhook handling itself is healthy.

## Previous Autoposting Handoff

- User asked to implement and deploy the remaining Autoposting feature together with the
  previous GetCourse import and manual broadcast fixes.
- Implemented Autoposting MVP:
  - database models and Alembic migration for `autoposts` and `autopost_publications`;
  - admin API at `/api/inbox/autoposts` for create/list/detail/cancel;
  - worker queue that publishes due posts, records per-channel history, retries failed rows,
    and does not resend already published rows;
  - Telegram publication through `send_message` to `AUTOPOST_TELEGRAM_CHAT_ID`;
  - VK publication through `wall.post` to `AUTOPOST_VK_OWNER_ID` or fallback `-VK_GROUP_ID`;
  - Inbox React tab "Автопостинг" with list, create modal, detail/history modal, and cancel.
- Added duplicate protection through `Autopost.dedupe_key` and unique
  `(autopost_id, channel)` publication rows.
- Extended `deploy_files.py` to upload `inbox-app/dist`, build first, apply Alembic, then
  recreate production services. It now also prints remote output safely on Windows and raises
  on non-zero remote exit status.
- Deployed to production. Public `/health` is OK, `/inbox` serves the new bundle containing
  "Автопостинг", Alembic reports `20260611_01 (head)`, and `app`, `funnel-worker`,
  `telegram-bot`, `postgres`, and `redis` are running.

## Previous Autoposting Verification

- `.venv\Scripts\ruff.exe check .` passed.
- `.venv\Scripts\mypy.exe src` passed.
- `pytest tests\test_autoposts.py -q` passed: 3 passed.
- `pytest -x` passed: 132 passed, 5 skipped.
- `npm run build` passed in `inbox-app/`.
- `git diff --check` passed.
- `docker compose -f docker-compose.prod.yml config --quiet` passed with existing local unset
  variable warnings.
- Production smoke passed:
  - `https://bot.aisukam.ru/health` returned `{"status":"ok","service":"FunnelHub"}`;
  - `/inbox` referenced `assets/index-CRPySZqQ.js`, and the asset contains "Автопостинг";
  - remote `alembic current` returned `20260611_01 (head)`;
  - production service state is running for app, worker, bot, postgres, redis.

## Previous Autoposting Notes / Next Steps

- For Telegram channel autoposting to actually publish, production must have
  `AUTOPOST_TELEGRAM_CHAT_ID` set to the target channel/chat id and the bot must have
  permission to post there.
- VK autoposting can use existing `VK_GROUP_ID` fallback; set `AUTOPOST_VK_OWNER_ID` only if
  a different wall owner is needed.
- Production worker log tail still contains existing email funnel errors for invalid or
  unsubscribed recipients, unrelated to Autoposting. No Autoposting traceback was observed.
- Rotate the SSH password because earlier tracked helper/archive files had contained real SSH
  credentials before this cleanup.
