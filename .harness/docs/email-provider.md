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

Not implemented yet:

- provider delivery/bounce/open/click webhooks;
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

The funnel runner resolves them at send time through the lead's active bot link token, using the same Telegram/VK link builders as the thank-you page. VK uses the configured VK OAuth join URL when available and falls back to the `vk.me` deep link.
