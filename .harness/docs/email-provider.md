# Email Provider

## Purpose

Email is an owned FunnelHub communication channel. GetCourse remains outside the sending loop.

The implementation is provider-agnostic: FunnelHub owns the internal sending contract, subscription checks, message history, unsubscribe handling, and funnel-runner integration. Real sends use the selected provider adapter.

## Current Scope

Implemented now:

- `EmailProviderClient` protocol;
- `DebugEmailProviderClient` for local/test sends without external credentials;
- `UnisenderGoEmailProviderClient` for real Unisender Go API sends;
- `send_email_text_message(...)` service;
- `email_subscriptions.status` and `unsubscribed_at` checks before sending;
- lazy generation of `email_subscriptions.unsubscribe_token`;
- unsubscribe footer with a FunnelHub-owned unsubscribe URL;
- HTML body rendering with CTA buttons and the Aisu Kam signature block;
- outbound email persistence in `messages` with `channel=email`;
- `GET /email/unsubscribe/{token}` public unsubscribe endpoint;
- `email.unsubscribed` event logging;
- `channel: email` funnel steps in `run_due_funnel_once(...)`;
- retry behavior through the existing funnel runner rollback path when provider sending fails.
- lead application notification emails to configured admin recipients after `/join/getcourse`
  submissions, with a short cooldown so the site's background webhook and redirect do not create
  duplicate notifications.

Not implemented yet:

- admin UI for manual email broadcasts.

## Provider Contract

Provider adapters implement:

```python
async def send_email(
    *,
    to_email: str,
    subject: str,
    text: str,
    html: str | None = None,
    from_email: str | None = None,
    from_name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> EmailProviderSendResult:
    ...
```

The adapter returns an optional external provider message id and raw provider response metadata.

## Environment

- `EMAIL_PROVIDER=disabled` by default.
- `EMAIL_PROVIDER=debug` enables dry-run provider behavior without external network sends.
- `EMAIL_PROVIDER=unisender_go` enables real Unisender Go API sends.
- `EMAIL_FROM_EMAIL` configures the sender email for real providers.
- `EMAIL_FROM_NAME` configures the sender name.
- `EMAIL_REPLY_TO_EMAIL` configures the reply-to email; for Unisender Go it falls back to `EMAIL_FROM_EMAIL`.
- `EMAIL_REPLY_TO_NAME` configures the reply-to display name; for Unisender Go it falls back to `EMAIL_FROM_NAME`.
- `EMAIL_DEFAULT_SUBJECT` is used when an email funnel step does not define `subject`.
- `DEFAULT_EMAIL_FUNNEL_PATH` points to the separate email funnel definition. The worker processes this funnel only when an email provider is enabled.
- `EMAIL_SIGNATURE_IMAGE_URL` optionally renders a round portrait image in the email signature.
- `EMAIL_UNISENDER_GO_API_KEY` stores the Unisender Go API key.
- `EMAIL_UNISENDER_GO_API_URL` defaults to `https://goapi.unisender.ru/ru/transactional/api/v1/email/send.json`.
- `PUBLIC_BASE_URL` is used to build unsubscribe links.
- `LEAD_NOTIFICATION_EMAIL_TO` configures one or more comma/semicolon-separated admin recipients
  for application notifications.
- `LEAD_NOTIFICATION_COOLDOWN_SECONDS` prevents duplicate admin notifications for the same lead
  within the configured window.

## Unisender Go

Unisender Go sends are made with `POST` JSON requests to the transactional email endpoint. The API key is sent in the `X-API-KEY` header and must never be committed.

The adapter sends:

- `recipients`;
- `subject`;
- `from_email` / `from_name`;
- `reply_to` / `reply_to_name`;
- plaintext body;
- HTML body when FunnelHub renders one;
- `idempotence_key` from FunnelHub `messages.id`;
- FunnelHub unsubscribe URL in `options.unsubscribe_url`;
- scalar FunnelHub metadata in `global_metadata`.

## Provider Webhooks

Unisender Go provider callbacks are accepted at:

```text
GET/POST https://bot.aisukam.ru/webhooks/email/unisender-go
```

`GET` returns `{"status":"ok"}` so Unisender Go can validate the webhook URL before saving it.

`POST` expects Unisender Go `events_by_user` JSON with `event_data.status`, `job_id`, `email`, `metadata`, and `event_time`. The handler validates the Unisender `auth` MD5 hash against `EMAIL_UNISENDER_GO_API_KEY`, then records idempotent `events` and updates existing message/subscription rows without a migration.

Tracked provider statuses:

- `delivered` -> `email.delivered`, message `delivered_at`, status `delivered`;
- `opened` -> `email.opened`, message `read_at`, status `read`;
- `clicked` -> `email.clicked`, message `read_at`, status `read`, clicked URL in message metadata;
- `soft_bounced` -> `email.soft_bounced`, message status `failed`, subscription remains active;
- `hard_bounced` -> `email.hard_bounced`, message status `failed`, subscription status `bounced`;
- `spam` / complaint -> `email.complained`, message status `failed`, subscription status `complained`;
- `unsubscribed` -> `email.unsubscribed`, message status `failed`, subscription status `unsubscribed`;
- `subscribed` -> `email.subscribed`.

Production Unisender Go webhook is registered as active with:

- `url=https://bot.aisukam.ru/webhooks/email/unisender-go`;
- `event_format=json_post`;
- `delivery_info=1`;
- `single_event=0`;
- `max_parallel=10`;
- `events.email_status=delivered,opened,clicked,unsubscribed,subscribed,soft_bounced,hard_bounced,spam`;
- `events.spam_block=*`.

## Funnel Usage

Email steps can be defined in a funnel:

```yaml
steps:
  - key: email_welcome
    delay: 0m
    channel: email
    subject: "Ваш первый материал"
    text: "Здравствуйте..."
```

If the email client is not configured, or the provider raises an error, the runner records the state as failed for that pass and rolls back the state advancement so the step remains due for retry.

The production Aisu Kam email sequence is stored separately from the Telegram/VK scenario in `content/funnels/aisu_email.yml`. Version 3 starts with three first-day emails: immediately due at `0m`, then `2m`, then `90m`; after that, day 2 through day 18 send one email step per local calendar day at 09:00 MSK through the existing day-delay scheduler.

Email funnel buttons can use internal bot-link URLs:

- `funnelhub://bot/telegram`
- `funnelhub://bot/vk`

The funnel runner resolves them at send time through the lead's active bot link token, using the same Telegram/VK link builders as the thank-you page. VK email buttons use FunnelHub's `/join/{token}/vk` launch endpoint, which can restart VK delivery for already known VK identities or stored GetCourse `VK-ID` values, then redirects to the plain `vk.me` deep link without VK ID authorization.
