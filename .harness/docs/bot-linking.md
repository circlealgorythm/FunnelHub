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
8. For Telegram/VK links, FunnelHub starts the default funnel from `DEFAULT_FUNNEL_PATH`.

## Implemented Endpoints

- `GET /join/{token}`: local channel choice page.
- `GET /join/getcourse`: direct GetCourse form redirect endpoint. It accepts lead fields in query params, saves/updates the lead, generates/reuses a bot link token, and renders the same Telegram/VK join page. This is useful when the form handler can redirect but a separate GetCourse process should be avoided.
- `POST /api/messenger/link`: links a messenger user to the lead behind the token.

`/join/getcourse` uses the same GetCourse ingestion protection as `/webhooks/getcourse`:
`GETCOURSE_WEBHOOK_SECRET`, `GETCOURSE_WEBHOOK_SECRET_REQUIRED`, and
`GETCOURSE_WEBHOOK_RATE_LIMIT_PER_MINUTE`. Secret query fields are accepted for redirect
compatibility but stripped before the lead payload is saved.

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
- Real user starts can override that link when the user explicitly enters through Telegram `/start <token>`, VK Callback token start, or VK ID OAuth. This supports repeat applications and repeated test leads from the same messenger account. The generic `/api/messenger/link` endpoint still rejects cross-lead conflicts by default.

## Telegram Token Handling

Telegram bot tokens must not be committed to the repository or Harness docs.

The Telegram adapter reads its token from `TELEGRAM_BOT_TOKEN`.

The local join page can show a Telegram deep link when `TELEGRAM_BOT_USERNAME` is set. The token itself is not needed for that page.
The same page can show a VK deep link when `VK_GROUP_SCREEN_NAME` is set.

For local development, create a gitignored `.env` file from `.env.example` and fill:

```text
TELEGRAM_BOT_USERNAME=<bot username without @>
TELEGRAM_BOT_TOKEN=<bot token from BotFather>
VK_GROUP_SCREEN_NAME=<VK community screen name without @>
VK_GROUP_ACCESS_TOKEN=<VK community access token>
VK_CALLBACK_SECRET=<VK Callback API secret>
VK_CONFIRMATION_CODE=<VK Callback API confirmation string>
VK_API_VERSION=5.199
```

Run the FastAPI app as usual, then run the Telegram polling adapter in a second terminal:

```powershell
.\.venv\Scripts\python.exe -m funnelhub.telegram_bot
```

The bot handles `/start <token>` and calls the same internal linking service as `POST /api/messenger/link`.

After a successful Telegram link, the default funnel is started for the lead. This creates or reuses one `funnel_states` row for the funnel key from the YAML definition. Repeated `/start <token>` calls do not create duplicate funnel states.
After a successful VK link, the same default funnel is started. Repeated VK starts reuse the existing state.

Incoming Telegram/VK text after linking is also passed to the active default funnel questionnaire. This is how the two initial answers are stored and how the personalized response is sent when both answers are known.

Implemented Telegram commands:

- `/start <token>`: link Telegram user to the saved lead.
- `/status`: show whether Telegram is linked and subscribed.
- `/stop`: mark the Telegram identity as unsubscribed.

Implemented outbound sending service:

- `send_telegram_text_message(...)` sends a text message to a subscribed Telegram identity.
- `send_vk_text_message(...)` sends a text message to a subscribed VK identity through `messages.send`.
- URL buttons are supported through simple button descriptors.
- Each outbound send creates a `messages` row with the concrete channel, direction `outbound`, body, status, external platform message ID when available, and button metadata.
- If the lead has no subscribed identity in the target channel, sending is rejected.

## VK Callback API

Implemented endpoint:

- `POST /webhooks/vk`

Production endpoint:

- `https://bot.aisukam.ru/webhooks/vk`

Supported VK events:

- `confirmation`: returns `VK_CONFIRMATION_CODE`.
- `message_allow`: extracts a bot-link token from `object.key`, `object.ref`, `object.start`, or payload, links the VK user to the lead, starts the default funnel, and sends the first due funnel step immediately when outbound VK credentials are configured.
- `message_new`: extracts a bot-link token from `message.ref`, JSON `message.payload`, or text like `/start <token>`, links the VK user to the lead, and starts the default funnel.
- `message_new` with `/stop`, `stop`, `стоп`, or `отписаться`: marks the VK identity unsubscribed.

VK outbound delivery uses the community access token from `VK_GROUP_ACCESS_TOKEN`.

## VK OAuth Compatibility

VK `message_allow` is not reliable enough as the only autostart path for users who have already allowed messages before. The production code therefore still supports the VK OAuth callback flow for compatibility with already issued links.

New thank-you page, Inbox bot links, and email CTA links intentionally use FunnelHub's `GET /join/{token}/vk` launch endpoint instead of VK ID OAuth. The launch endpoint first tries to restart VK delivery server-side when the lead already has a subscribed VK identity or a stored GetCourse `VK-ID`, then redirects the browser to the plain `https://vk.me/...` deep link. This avoids VK ID authorization while still handling old/known VK users when FunnelHub already knows their VK user id. OAuth settings may remain configured for old links, but they are no longer preferred by public subscription buttons.

As of 2026-06-06, `/join/getcourse` can enrich a just-submitted lead from the
GetCourse API by email before rendering the thank-you page. This covers existing
GetCourse users when the site only sends `name/email/phone` but GetCourse already
stores a VK-ID. The follow-up VK button then uses the same `/join/{token}/vk`
launch path and can send the first VK message server-side.

Repeated real bot starts reset the messenger funnel to the first step. Telegram
`/start <token>` and VK `message_allow`/`message_new` with a token relink the identity
to the current lead, clear old questionnaire answers/pending-question metadata, set
the messenger channel, and send from the beginning again. The `/join/{token}/vk`
launch endpoint keeps its 10-minute duplicate guard to avoid double sends from repeated
button taps.

The thank-you page keeps the per-lead Telegram/VK token inside the button URL, but the visible user experience stays simple: the buttons read `Открыть Telegram` and `Открыть VK`. This preserves attribution in FunnelHub while avoiding instructions that ask the lead to copy or provide a personal link.

OAuth callback support uses these settings:

```text
VK_GROUP_ID=<numeric VK community id>
VK_OAUTH_CLIENT_ID=<VK app client id>
VK_OAUTH_CLIENT_SECRET=<VK app secure key>
VK_OAUTH_STATE_SECRET=<random signing secret; can reuse callback secret only as a fallback>
```

The VK app redirect URL must be:

```text
https://bot.aisukam.ru/oauth/vk/callback
```

OAuth callback behavior:

- validates the signed lead token state;
- exchanges the VK ID OAuth code for a VK user id;
- links the VK user to the saved lead;
- starts the default funnel and sends the first due step immediately.

New public VK buttons require `VK_GROUP_SCREEN_NAME`; if it is missing, the button is disabled instead of sending the lead through VK ID OAuth.

For unknown VK users who have already allowed messages to the community, VK may open an existing empty dialog without sending a new `message_allow` event. FunnelHub cannot infer the VK user id from that browser transition alone without OAuth or a user-sent message. The `/join/{token}/vk` launch endpoint therefore covers the cases FunnelHub can know without auth:

- already linked VK identities;
- imported/stored GetCourse `VK-ID` external ids.

Admins can add or correct a lead's stored `VK-ID` from Inbox `База` lead detail. The field is saved into `lead_external_ids` as `provider=getcourse_vk_id` and mirrored into the `vk_id` custom field so exports and detail views remain consistent. The API rejects non-numeric IDs and IDs already linked to another lead.

Production notes:

- The VK ID confirmation screen with the `Разрешить` button is controlled by VK and cannot be removed by FunnelHub.
- After a successful callback, FunnelHub auto-redirects the browser to the VK community dialog; the visible success page is only a fallback.
- Outbound VK messages require a valid community access token in `VK_GROUP_ACCESS_TOKEN`. A VK ID app service key is not enough.
- Telegram questionnaire answer buttons are inline callback buttons. Manual text answers remain as a fallback.
- VK questionnaire answer buttons are inline buttons with `primary` color. URL buttons remain link buttons.

## Next Work

- Test the Telegram adapter end-to-end against the new test bot.
- Replace the placeholder funnel YAML with the real customer scenario.
- Monitor whether the restored `vk.me` flow receives `message_allow` / `message_new` callback events reliably for new leads.
