# Session Handoff: FunnelHub & Infrastructure Security

## Currently Verified
- Окружение FunnelHub рабочее: Python 3.12 / 3.13, управление через `uv`.
- Базовые тесты проходят (`uv run pytest tests/test_metadata.py`).
- Установлен и инициализирован шаблон Harness Engineering.

## Changes This Session
- Завершен `SEC-001` (Устранение критических утечек секретов и логов PII).
- Завершен `SEC-002` (Харденинг базы данных PostgreSQL и Redis в Docker):
  - Устранен жесткий хардкод кредов БД во всех сервисах `docker-compose.prod.yml`, добавлена параметризация через `.env` с безопасным fallback.
  - Внедрена поддержка аутентификации Redis через `--requirepass`.
  - Порты 5432 и 6379 в dev-компоузе изолированы на `127.0.0.1`.
  - В prod-компоузе подтверждено полное отсутствие внешних портов БД и Redis.
- Завершен `SEC-003` (Защита API: Rate Limiting на авторизацию и обязательный секрет вебхуков):
  - Внедрен Rate Limiter на `/api/auth/login` (отсечка брутфорса и защита CPU до вызова PBKDF2).
  - Покрыто unit-тестами в `test_auth.py` (HTTP 429 Too Many Requests).
  - Задокументированы параметры лимита и вебхуков в `.env.example`.
- Зафиксированы правила Harness в `AGENTS.md` (включая Zero-Regression Protocol и обязательный атомарный Git-коммит).
- Завершен `SEC-004` (Харденинг Reverse Proxy Caddy и заголовки безопасности):
  - `Caddyfile` усилен защитой от DoS (`request_body max_size 15MB`), включено удаление сигнатуры `-Server` и добавлены заголовки `HSTS`, `X-Content-Type-Options`, `X-Frame-Options SAMEORIGIN`, `Referrer-Policy`, `Permissions-Policy`.
  - Покрыт тестами в `tests/test_caddyfile.py`.

## Still Broken or Unverified
- Задачи безопасности `SEC-005` и `SEC-006` в статусе `not-started`.

## Next Best Action
- Взять в работу задачу `SEC-005` (Автоматизированное шифрованное резервное копирование БД).
- Не трогать другие компоненты до завершения и верификации `SEC-005`.

## Commands
- **Windows Verify**: `powershell -ExecutionPolicy Bypass -File .\init.ps1`
- **Linux Verify**: `./init.sh`
- **Run Tests**: `uv run pytest`
- **Run Lint**: `uv run ruff check`
