# Bot Linking

## Goal

Connect a lead saved by GetCourse webhook to a messenger identity without making Telegram or VK the source of the lead.

Lead creation still happens at `GET/POST /webhooks/getcourse`. Messenger linking is a second step.

## Current MVP Flow

1. GetCourse calls `/webhooks/getcourse`.
2. FunnelHub creates or updates the lead.
3. FunnelHub creates or reuses an active `bot_link_token`.
4. Webhook response includes:
   - `bot_link_token`
   - `join_url`, for example `http://localhost:8000/join/<token>`
5. User opens `/join/<token>`.
6. Telegram/VK adapter later calls `POST /api/messenger/link` with:
   - `token`
   - `channel`
   - `external_user_id`
   - optional username/display name/raw profile
7. FunnelHub creates or updates `messenger_identities`.

## Implemented Endpoints

- `GET /join/{token}`: local channel choice page.
- `POST /api/messenger/link`: links a messenger user to the lead behind the token.

Request example:

```json
{
  "token": "<bot_link_token>",
  "channel": "telegram",
  "external_user_id": "123456789",
  "username": "example_user",
  "display_name": "Example User",
  "raw_profile": {
    "language_code": "ru"
  }
}
```

Response example:

```json
{
  "status": "ok",
  "lead_id": "<uuid>",
  "identity_id": "<uuid>",
  "created": true
}
```

## Token Rules

- Tokens live in `bot_link_tokens`.
- Tokens are unique.
- Current TTL: 30 days.
- An active non-expired token is reused for repeat webhooks for the same lead.
- `used_at` is set on first successful messenger link, but the token remains active for now so repeated `/start` calls can still repair/update the same link.
- The same `channel + external_user_id` cannot be linked to a second lead.

## Telegram Token Handling

Telegram bot tokens must not be committed to the repository or Harness docs.

The Telegram adapter reads its token from `TELEGRAM_BOT_TOKEN`.

The local join page can show a Telegram deep link when `TELEGRAM_BOT_USERNAME` is set. The token itself is not needed for that page.

For local development, create a gitignored `.env` file from `.env.example` and fill:

```text
TELEGRAM_BOT_USERNAME=<bot username without @>
TELEGRAM_BOT_TOKEN=<bot token from BotFather>
```

Run the FastAPI app as usual, then run the Telegram polling adapter in a second terminal:

```powershell
.\.venv\Scripts\python.exe -m funnelhub.telegram_bot
```

The bot handles `/start <token>` and calls the same internal linking service as `POST /api/messenger/link`.

Implemented Telegram commands:

- `/start <token>`: link Telegram user to the saved lead.
- `/status`: show whether Telegram is linked and subscribed.
- `/stop`: mark the Telegram identity as unsubscribed.

Implemented outbound sending service:

- `send_telegram_text_message(...)` sends a text message to a subscribed Telegram identity.
- URL buttons are supported through simple button descriptors.
- Each outbound send creates a `messages` row with channel `telegram`, direction `outbound`, body, status, external Telegram message ID when available, and button metadata.
- If the lead has no subscribed Telegram identity, sending is rejected.

## Next Work

- Test the Telegram adapter end-to-end against the new test bot.
- Add first funnel scenario after successful Telegram linking.
- Add VK adapter later after community credentials are available.
