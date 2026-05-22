# FunnelHub

Центр управления воронкой.

FunnelHub is a server-side communication system around GetCourse.

GetCourse remains responsible for courses, payments, installments, access, login/password
issuance, and the student cabinet. FunnelHub owns long-term communication: lead database,
Telegram/VK bots, future Max channel, email sequences, inbox, imports, broadcasts, funnel
state, and analytics.

## Local Development

```bash
docker compose up --build
```

Health check:

```bash
curl http://localhost:8000/health
```

## Verification

```bash
ruff check .
mypy src
pytest -x
```

Project methodology lives in `.harness/`.
