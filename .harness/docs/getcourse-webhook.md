# GetCourse Webhook Payload Discovery

This note captures the side conversation about how to obtain a real GetCourse webhook payload before implementing `getcourse-webhook`.

## Goal

Before building the production webhook endpoint, collect an example request from GetCourse to understand:

- exact variable names available in GetCourse processes;
- whether data arrives as query params, form data, or JSON body;
- headers sent by GetCourse;
- date/phone/email formats;
- how UTM fields appear;
- whether custom fields / consent checkboxes can be sent directly.

## Recommended Test Method

Use a temporary request collector such as `https://webhook.site/`.

Steps:

1. Open `https://webhook.site/`.
2. Copy the generated unique URL.
3. In GetCourse, create or open a test process for users.
4. Add the operation/action `Вызвать URL`.
5. Use a test user only; do not send real customer data to a third-party collector.
6. Start with `GET` or `POST`; `POST` is closer to the final integration, but `GET` is enough for first discovery.
7. Send basic fields as query parameters first.

Example first-pass URL:

```text
https://webhook.site/<uuid>?gc_user_id={object.id}&email={object.email}&phone={object.phone}&name={object.name}&first_name={object.first_name}&last_name={object.last_name}&city={object.city}
```

After running the process, inspect the request in webhook.site and save:

- query params;
- request body;
- headers;
- method;
- exact values/format, with personal data anonymized.

## Test User

Use a synthetic user such as:

```text
Name: Тест
Email: test@example.com
Phone: 79990000000
```

## Minimum Payload Fields To Discover

Start with:

- GetCourse user ID;
- email;
- phone;
- name / first name / last name;
- city;
- registration date if available;
- last activity date if available;
- `utm_source`;
- `utm_medium`;
- `utm_campaign`;
- `utm_term`;
- `utm_content`;
- `utm_group`;
- source / "Откуда пришел";
- VK ID if available.

## Captured Test Payload

Captured from webhook.site screenshots on 2026-05-22.

Transport:

- Method: `GET`.
- Request content/body: none.
- Form values: none.
- Headers shown:
  - `accept: */*`
  - `host: webhook.site`
- Source IPs varied across requests.

Confirmed query parameters from GetCourse test process:

```text
gc_user_id=423379541
email=<email>
phone=<phone>
name=<full name>
first_name=<first name>
last_name=<last name>
city=(empty)
country=Россия
utm_source=localhost
utm_medium=referral
utm_campaign=(empty)
utm_term=(empty)
utm_content=(empty)
```

Confirmed custom field query parameters from a separate/earlier request:

```text
custom_10558670=(empty)
custom_10575005=(empty)
custom_10616540=(empty)
custom_10661024=(empty)
```

Notes:

- GetCourse successfully sends selected fields as query parameters.
- Empty values arrive as empty query values.
- The first screenshot showed custom field IDs as `custom_<id>` query params.
- The second screenshot showed basic profile + UTM fields.
- The test did not include request body or form-encoded values.
- The production endpoint must support this GET/query mode at minimum.

## Custom Fields / Consent Checkboxes

The GetCourse export showed that some blank/headerless columns are actually custom fields. Screenshots showed these fields can represent checkbox consent values for privacy policy / offer agreement.

For webhook discovery:

- Exact custom field query parameter format observed: `custom_<field_id>`.
- GetCourse account fields API can discover user custom field IDs:
  `https://<account>.getcourse.ru/pl/api/account/fields?action=get&key=<secret_key>`.
- If direct variables are available, include them in the test callback.
- If only labels are available, record the exact label.
- If GetCourse cannot send these fields cleanly via webhook, keep importing/mapping them from CSV/XLSX through `lead_custom_fields` and `lead_consents`.

Do not assume headerless export columns are irrelevant; preserve them during import.

## Captured Account Fields API Output

Captured from a screenshot of GetCourse `/pl/api/account/fields?action=get`.

Response shape observed:

```json
{
  "success": true,
  "info": [
    {
      "id": 10558670,
      "type": "checkbox",
      "title": "",
      "required": 0,
      "field_order_pos": 0,
      "context_type": "user"
    }
  ],
  "error_message": "",
  "error": false
}
```

Visible user checkbox custom fields from screenshot:

```text
10558670 checkbox field_order_pos=0 context_type=user
10575005 checkbox field_order_pos=1 context_type=user
10616540 checkbox field_order_pos=2 context_type=user
10661024 checkbox field_order_pos=3 context_type=user
10682753 checkbox field_order_pos=4 context_type=user
10682754 checkbox field_order_pos=5 context_type=user
10663365 checkbox field_order_pos=6 context_type=user
11344349 checkbox field_order_pos=7 context_type=user
```

Raw JSON correction:

- The screenshot read was corrected by raw JSON.
- Correct IDs are `10683365` and `11344348`, not `10663365` and `11344349`.
- Raw JSON is the source of truth.

Visible user/system UTM fields:

```text
12146321 title=gc_system_user_utm_source context_type=user
12146322 title=gc_system_user_utm_medium context_type=user
12146323 title=gc_system_user_utm_campaign context_type=user
12146324 title=gc_system_user_utm_term context_type=user
12146325 title=gc_system_user_utm_content context_type=user
```

Visible deal/system UTM fields:

```text
12146326 title=gc_system_deal_utm_source context_type=deal
12146327 title=gc_system_deal_utm_medium context_type=deal
12146328 title=gc_system_deal_utm_campaign context_type=deal
12146329 title=gc_system_deal_utm_term context_type=deal
12146330 title=gc_system_deal_utm_content context_type=deal
```

Raw JSON custom field mapping:

| Field ID | Order | Type | Context | Meaning |
|---:|---:|---|---|---|
| `10558670` | 0 | checkbox | user | Personal data processing consent with `shamanaisu.getcourse.ru/politica` and `shamanaisu.getcourse.ru/oferta`. |
| `10575005` | 1 | checkbox | user | Personal data processing consent with `shamanaisu.getcourse.ru/politica` and `school.aisukam.ru/oferta_old`. |
| `10616540` | 2 | checkbox | user | Personal data processing consent with `shamanaisu.getcourse.ru/politica` only. |
| `10661024` | 3 | checkbox | user | Personal data processing consent with `shamanaisu.getcourse.ru/politica` and `school.aisukam.ru/oferta_marafon_meditation`. |
| `10682753` | 4 | checkbox | user | Personal data processing consent with `shamanaisu.getcourse.ru/politica` and `school.aisukam.ru/oferta_orakuly`. |
| `10682754` | 5 | checkbox | user | Personal data processing consent with `shamanaisu.getcourse.ru/politica` and `school.aisukam.ru/oferta_skoraya_pomoshch`. |
| `10683365` | 6 | checkbox | user | Personal data processing consent with `shamanaisu.getcourse.ru/politica` and `school.aisukam.ru/oferta_individualnoe_nastavnichestvo`. |
| `11344348` | 7 | checkbox | user | Personal data processing consent with `shamanaisu.getcourse.ru/politica` and `school.aisukam.ru/oferta_shamanputesh`. |

Semantic consent normalization:

- All eight checkbox fields imply `personal_data=true` when checked.
- All eight checkbox fields imply `privacy_policy=true` when checked.
- All fields except `10616540` also imply `offer_agreement=true` with a product/offer-specific URL.
- `10616540` should not create `offer_agreement=true` unless another source confirms an offer link.
- Keep the original `custom_<id>` value in `lead_custom_fields` even when deriving `lead_consents`.

Important:

- The API confirms field IDs and ordering for checkbox custom fields.
- Checkbox `title` values are blank; descriptions carry the legal meaning.
- Raw JSON is now available and should be treated as the source of truth for these IDs.

## Expected Implementation Impact

The future `getcourse-webhook` feature should:

- accept GET/query params at minimum, and also support form/JSON if needed later;
- validate and normalize email/phone/UTM fields;
- deduplicate by GetCourse user ID, email, and phone;
- store raw payload JSON for traceability;
- parse `custom_<field_id>` parameters into `lead_custom_fields`;
- create/update `lead_consents` only when custom field mapping to consent semantics is known;
- create an `events` row with a dedupe key if GetCourse can provide a stable event/request identifier.

## Captured Payload - 2026-05-22

GetCourse was observed calling `webhook.site` with a `GET` request and query string fields. Request body and form values were empty.

Observed base fields:

- `gc_user_id`: numeric GetCourse user ID, for example `423379541`.
- `email`: user email.
- `phone`: phone in Russian `+7...` format.
- `name`: full display name.
- `first_name`: first name.
- `last_name`: last name.
- `city`: can be empty.
- `country`: for example `Россия`.
- `utm_source`: for example `localhost`.
- `utm_medium`: for example `referral`.
- `utm_campaign`: can be empty.
- `utm_term`: can be empty.
- `utm_content`: can be empty.

Observed custom fields:

- `custom_10558670`
- `custom_10575005`
- `custom_10616540`
- `custom_10661024`

In the captured request these custom field values were empty. They must still be preserved by key when present because GetCourse custom fields can represent consent checkboxes or other domain-specific fields.

Current implementation target:

- Accept `GET /webhooks/getcourse` query params matching the captured payload.
- Also allow `POST` JSON/form data for compatibility.
- Treat `(empty)`, empty string, `none`, and `null` as absent values.
- Require at least one identity: `gc_user_id`, `email`, or `phone`.
- Deduplicate by GetCourse user ID first, then normalized email, then normalized phone.
- Store all `custom_*` fields in `lead_custom_fields`.
- Derive `lead_consents` only from the raw-JSON-backed custom field mapping above.
- For mapped checkbox fields with value `Да`, create/update `personal_data` and `privacy_policy`.
- For mapped checkbox fields with value `Да`, create/update `offer_agreement` when the field has an offer URL; `10616540` is policy-only and must not create `offer_agreement`.

## Open Questions

- Whether all needed custom consent fields can be sent as `custom_<field_id>` in the live process.
- Whether GetCourse can send a stable webhook/request ID for deduplication.
- Whether final production webhook should remain GET/query or switch to form-encoded/JSON POST.
- Confirm whether the production GetCourse webhook should send all eight consent checkbox fields or only the fields relevant to the active form/offer.
