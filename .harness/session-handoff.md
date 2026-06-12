# Session Handoff

## Current Status

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
  - `AUTOPOST_FOLLOWUP_MARKER` default is `#followup`;
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

- `.venv\Scripts\pytest.exe tests\test_vk_messaging.py tests\test_funnel_runner.py -q` passed:
  18 passed.
- `.venv\Scripts\pytest.exe -x` passed: 141 passed, 5 skipped.
- `.venv\Scripts\ruff.exe check .` passed.
- `.venv\Scripts\mypy.exe src` passed.
- `git diff --check` passed.
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

- Follow-up marker routing is deployed. The marker is `#followup` by default and is configurable
  through `AUTOPOST_FOLLOWUP_MARKER`.
- Current follow-up recipient materialization happens at creation time. Leads who complete the
  18-day funnel after a follow-up post is created will not be backfilled into that existing post;
  that behavior can be changed later if product requirements need rolling delivery.

- User confirmed that both Autoposting MVP and email-provider are already deployed.
- `.harness/feature-list.json` was synchronized:
  - `current_feature` is now `null`;
  - `email-provider` is `completed`;
  - existing `autoposting` is treated as completed public Autoposting MVP;
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
  - public platform publishing: Telegram channel, VK group wall, Odnoklassniki, Zen, and
    YouTube community posts if feasible;
  - internal follow-up posts: private Telegram/VK bot messages sent only to leads who completed
    the 18-day `aisu_consultation` messenger funnel.
- VK Video and YouTube video upload are out of scope for the public text/post publishing flow.
  Odnoklassniki, Zen, and YouTube community posts require separate API feasibility checks before
  implementation.
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
