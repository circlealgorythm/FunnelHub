# Session Progress Log: FunnelHub & Infrastructure Security

## Current Verified State

- **Repository root directory**: `C:\Users\circlealgorythm\Documents\Бот воронка`
- **Standard startup path**: `uv run uvicorn funnelhub.main:app --port 8000`
- **Standard verification path**: `powershell -ExecutionPolicy Bypass -File .\init.ps1` (или `uv run pytest`)
- **Active Feature**: Нет (SEC-003 завершена, готов к SEC-004)
- **Current blocker**: Нет
- **Highest priority unfinished feature**: `SEC-004` (Харденинг Reverse Proxy Caddy и заголовки безопасности)

---

## Status

### What's Done
- [x] Развернут каркас Harness Engineering (`AGENTS.md`, `feature_list.json`, `progress.md`, `session-handoff.md`, `init.ps1`, `init.sh`).
- [x] Сформирован реестр задач безопасности (`SEC-001` - `SEC-006`) с приоритетами, критериями верификации и зависимостями.
- [x] **`SEC-001` (Устранение критических утечек секретов и логов PII)** (passing):
  - Пароль SMTP Яндекса удален из открытого кода `send-question.php` и перенесен в изолированный `lead-config.php` с поддержкой `getenv`.
  - Все версии `lead-config.php` добавлены в `.gitignore` репозитория сайта.
  - Из `public/submit-lead.php` и `dist/submit-lead.php` удалена прямая запись логов с персональными данными (PII) в публичный web-root (`lead-debug.log`). Добавлено автоудаление старого файла и маскирование телефонов при явном указании защищенного `LEAD_DEBUG_LOG_PATH`.
  - Верификация: `Select-String` подтвердил отсутствие паролей в коде; прогон `init.ps1` завершился кодом 0.
- [x] **`SEC-002` (Харденинг базы данных PostgreSQL и Redis в Docker)** (passing):
  - В `docker-compose.prod.yml` устранен жестко зашитый пароль `funnelhub:funnelhub`. Креды `DATABASE_URL` и Postgres параметризованы через `${POSTGRES_PASSWORD}` и `${DATABASE_URL}` с сохранением fallback для предотвращения сбоя существующей базы (Zero-Regression).
  - Для Redis внедрен защищенный режим запуска с `--requirepass` при передаче `REDIS_PASSWORD`.
  - В dev-компоузе `docker-compose.yml` порты 5432 и 6379 привязаны строго к `127.0.0.1` (защита от сканирования извне при случайном запуске).
  - В `docker-compose.prod.yml` подтверждена полная изоляция: порты БД и Redis не экспонируются наружу.
  - В `.env.example` задокументированы переменные `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `REDIS_PASSWORD`.
  - Верификация: Python-скрипт валидации YAML и портов пройден успешно; `init.ps1` пройден (код 0).
- [x] **`SEC-003` (Защита API: Rate Limiting на авторизацию и обязательный секрет вебхуков)** (passing):
  - В `config.py` добавлена настройка `inbox_login_rate_limit_per_minute` (по умолчанию 5 запросов в минуту).
  - В `ingestion_guard.py` реализован `auth_login_rate_limiter` и `enforce_login_rate_limit`. Лимиты проверяются до запуска ресурсоемкого вычисления PBKDF2 (390k итераций), что защищает сервер от 100% загрузки CPU при DoS/брутфорсе.
  - Эндпоинт `/api/auth/login` защищен проверкой лимита.
  - Написан unit-тест `test_login_rate_limiting` в `tests/test_auth.py`, проверяющий блокировку 429 Too Many Requests при превышении лимита. Все 6 тестов auth пройдены успешно.
  - В `.env.example` задокументирован параметр лимита и рекомендация по включению `GETCOURSE_WEBHOOK_SECRET_REQUIRED=true` на проде.
  - Верификация: `ruff check` и `init.ps1` завершились успешно (код 0).

### What's In Progress
- [ ] Ожидание команды пользователя на старт `SEC-004`.

### What's Next
1. Взять фичу `SEC-004`: харденинг Reverse Proxy Caddy и добавление security headers (HSTS, CSP, X-Frame-Options, лимит тела запроса 15MB).
2. Проверить синтаксис Caddyfile.
3. Дождаться подтверждения пользователя перед переходом к `SEC-005`.

---

## Blockers / Risks
- **Risk**: Пароль приложения Яндекса был в репозитории; необходимо подтверждение пользователя о смене пароля в Яндекс ID.

---

## Decisions Made
- **2026-10-12**: Внедрена методология Harness Engineering. Все задачи выполняются строго по одной фиче за раз, с обязательным прогоном тестов, фиксацией доказательств и подтверждением перехода пользователем.
- **2026-10-12**: Добавлено строгое правило №7 в `AGENTS.md`: обязательный атомарный Git-коммит сразу после верификации каждой фичи в соответствующем репозитории до отчета пользователю.
