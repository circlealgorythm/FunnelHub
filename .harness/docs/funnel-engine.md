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
- Docker Compose `worker` profile for running `python -m funnelhub.funnel_worker`.
- automatic default funnel start after successful Telegram linking.

Not implemented yet:

- email channel execution;
- branching conditions;
- real customer scenario content.

## Scenario Format

Example file:

`content/funnels/example.yml`

```yaml
key: example_onboarding
version: 1
title: Example onboarding funnel
steps:
  - key: welcome
    delay: 0m
    channel: telegram
    text: "Тестовое приветствие. Реальный сценарий будет добавлен позже."
  - key: follow_up
    delay: 1d
    channel: telegram
    text: "Тестовое продолжение через день."
    buttons:
      - text: "Открыть сайт"
        url: "https://example.com"
```

Delay format:

- `0m`, `15m`
- `1h`, `12h`
- `1d`, `3d`

Supported channels for now:

- `telegram`
- `email`

## State Rules

- A lead can have one `funnel_states` row per `funnel_key`.
- Starting an already existing funnel returns the existing state.
- `current_step_key` points to the next step to send.
- `next_run_at` is calculated from the step `delay`.
- After sending a due step, the engine advances to the next step.
- After the final step, state becomes `completed`.

## Next Work

- Replace `content/funnels/example.yml` with the real customer scenario when available.

## Runner

Service function:

`funnelhub.services.funnel_runner.run_due_funnel_once(...)`

It:

- loads active due states for the selected `funnel_key`;
- sends Telegram steps through the Telegram outbound service;
- records outbound messages in `messages`;
- commits successful state advancement;
- rolls back failed states so they remain due for a later retry.

CLI entrypoint:

```powershell
python -m funnelhub.funnel_worker
```

Docker profile:

```powershell
docker compose --profile worker up funnel-worker
```

Environment:

- `DEFAULT_FUNNEL_PATH` defaults to `content/funnels/example.yml`;
- `FUNNEL_RUNNER_INTERVAL_SECONDS` defaults to `60`;
- `FUNNEL_RUNNER_BATCH_SIZE` defaults to `100`;
- `TELEGRAM_BOT_TOKEN` is required for the worker.
