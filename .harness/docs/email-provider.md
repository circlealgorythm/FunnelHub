# Email Provider

## Purpose

Email is an owned FunnelHub communication channel. GetCourse remains outside the sending loop.

The first implementation is provider-agnostic: FunnelHub now has the internal sending contract, subscription checks, message history, unsubscribe handling, and funnel-runner integration. A concrete external provider can be added later by implementing the email provider client.

## Current Scope

Implemented now:

- `EmailProviderClient` protocol;
- `DebugEmailProviderClient` for local/test sends without external credentials;
- `send_email_text_message(...)` service;
- `email_subscriptions.status` and `unsubscribed_at` checks before sending;
- lazy generation of `email_subscriptions.unsubscribe_token`;
- unsubscribe footer with a FunnelHub-owned unsubscribe URL;
- outbound email persistence in `messages` with `channel=email`;
- `GET /email/unsubscribe/{token}` public unsubscribe endpoint;
- `email.unsubscribed` event logging;
- `channel: email` funnel steps in `run_due_funnel_once(...)`;
- retry behavior through the existing funnel runner rollback path when provider sending fails.

Not implemented yet:

- concrete external provider adapter;
- provider delivery/bounce/open/click webhooks;
- HTML template rendering;
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
- `EMAIL_FROM_EMAIL` configures the sender email for future real providers.
- `EMAIL_FROM_NAME` configures the sender name.
- `EMAIL_DEFAULT_SUBJECT` is used when an email funnel step does not define `subject`.
- `PUBLIC_BASE_URL` is used to build unsubscribe links.

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
