# Funnel Engine

## Purpose

The funnel engine is the scheduling layer between saved leads and channel adapters.

It is intentionally separate from scenario copy. The current implementation can run with a placeholder scenario while the real bot script is being prepared by the customer.

## Current Scope

Implemented now:

- scenario definition format in YAML/JSON;
- loader and Pydantic validation;
- `funnel_states` based scheduling;
- dry-run sender for tests;
- due-step execution and state advancement;
- completion after the last step.
- Telegram runner pass that picks due states for one funnel definition;
- Telegram sender adapter that dispatches funnel steps through `send_telegram_text_message(...)`;
- VK sender adapter that dispatches funnel steps through `send_vk_text_message(...)`;
- shared `messenger` funnel channel that routes a step to the lead's subscribed Telegram/VK identity;
- email funnel steps through the provider-agnostic email sender when an email client is configured;
- non-blocking questionnaire steps with text buttons;
- late answer handling for Telegram/VK incoming messages;
- personalized response after the two questionnaire answers are collected;
- pending-question reminders stored in `funnel_states.metadata`;
- Docker Compose `worker` profile for running `python -m funnelhub.funnel_worker`.
- automatic default funnel start after successful Telegram/VK linking.

Not implemented yet:

- concrete external email provider adapter;
- arbitrary branching beyond the current two-question personalization;
- video asset replacement workflow.

## Scenario Format

Example file:

`content/funnels/aisu_consultation.yml`

```yaml
key: aisu_consultation
version: 1
title: Aisu consultation messenger funnel
questionnaire:
  questions:
    topic:
      text: "Что для вас актуальнее всего сейчас?"
      options:
        - key: money
          text: "Деньги"
steps:
  - key: welcome
    delay: 0m
    channel: messenger
    text: "Ваша заявка на консультацию принята! ..."
  - key: question_topic
    delay: 1m
    channel: messenger
    kind: question
    question_key: topic
    text: "Что для вас актуальнее всего сейчас?"
    buttons:
      - text: "Деньги"
```

Delay format:

- `0m`, `15m`
- `1h`, `12h`
- `1d`, `3d`

Supported channels for now:

- `messenger`
- `telegram`
- `vk`
- `email`

## State Rules

- A lead can have one `funnel_states` row per `funnel_key`.
- Starting an already existing funnel returns the existing state.
- `current_step_key` points to the next step to send.
- `next_run_at` is normally calculated from the step `delay`.
- After sending a due step, the engine advances to the next step.
- After the final step, state becomes `completed`.
- A `question` step sends text buttons and delays the next content step by the question's `reminder_delay`.
- Questionnaire answers are stored under `metadata.answers`.
- If the first answer is received, the second question is sent immediately.
- If the first answer is received before the content timeout, the next content step waits for the second question's `reminder_delay`.
- If the second answer is received before the timeout, the personalized response is sent immediately and the waiting content step becomes due immediately.
- If no answer arrives before the timeout, the scheduled chain continues while pending-question metadata remains available for later answers.
- If a question is pending, the runner can repeat it after the configured `reminder_delay`.

## Next Work

- Replace the three lesson video/page links when final video assets are ready.

## Runner

Service function:

`funnelhub.services.funnel_runner.run_due_funnel_once(...)`

It:

- loads active due states for the selected `funnel_key`;
- sends Telegram steps through the Telegram outbound service;
- records outbound messages in `messages`;
- commits successful state advancement;
- rolls back failed states so they remain due for a later retry.
- can send `channel: email` steps when an email provider client is configured.

CLI entrypoint:

```powershell
python -m funnelhub.funnel_worker
```

Docker profile:

```powershell
docker compose --profile worker up funnel-worker
```

Production:

- `docker-compose.prod.yml` runs `app`, `telegram-bot`, `funnel-worker`, `postgres`, and `redis`.
- Host Caddy on the VPS terminates HTTPS for `bot.aisukam.ru` and reverse-proxies to the app on `127.0.0.1:8000`.

Environment:

- `DEFAULT_FUNNEL_PATH` defaults to `content/funnels/example.yml`;
- `FUNNEL_RUNNER_INTERVAL_SECONDS` defaults to `60`;
- `FUNNEL_RUNNER_BATCH_SIZE` defaults to `100`;
- `TELEGRAM_BOT_TOKEN` is required for Telegram sends.
- `VK_GROUP_ACCESS_TOKEN` is required for VK sends.
- `EMAIL_PROVIDER=debug` enables dry-run email sends without external credentials.
- At least one Telegram, VK, or email provider configuration is required for the worker.
