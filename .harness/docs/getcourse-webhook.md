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

## Custom Fields / Consent Checkboxes

The GetCourse export showed that some blank/headerless columns are actually custom fields. Screenshots showed these fields can represent checkbox consent values for privacy policy / offer agreement.

For webhook discovery:

- Try to find exact variable names or IDs for the custom fields in GetCourse.
- If direct variables are available, include them in the test callback.
- If only labels are available, record the exact label.
- If GetCourse cannot send these fields cleanly via webhook, keep importing/mapping them from CSV/XLSX through `lead_custom_fields` and `lead_consents`.

Do not assume headerless export columns are irrelevant; preserve them during import.

## Expected Implementation Impact

The future `getcourse-webhook` feature should:

- accept both query/form style data and JSON if needed;
- validate and normalize email/phone/UTM fields;
- deduplicate by GetCourse user ID, email, and phone;
- store raw payload JSON for traceability;
- create/update `lead_custom_fields` and `lead_consents` only when field mapping is known;
- create an `events` row with a dedupe key if GetCourse can provide a stable event/request identifier.

## Open Questions

- Exact syntax for GetCourse variables in the user's account/process.
- Whether GetCourse will send custom fields directly in callback.
- Whether GetCourse can send a stable webhook/request ID for deduplication.
- Whether final production webhook should use GET, form-encoded POST, or JSON POST.
