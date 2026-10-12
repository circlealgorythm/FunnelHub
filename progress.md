# Session Progress Log: FunnelHub & Infrastructure Security

## Current Verified State

- **Repository root directory**: `C:\Users\circlealgorythm\Documents\Бот воронка`
- **Standard startup path**: `uv run uvicorn funnelhub.main:app --port 8000`
- **Standard verification path**: `powershell -ExecutionPolicy Bypass -File .\init.ps1` (или `uv run pytest`)
- **Active Feature**: `UI-002` (Тактильный отклик интерактивных элементов: :active & Focus)
- **Current blocker**: Нет
- **Highest priority unfinished feature**: `UI-002`
- **Roadmap Artifact**: `C:\Users\circlealgorythm\.gemini\antigravity\brain\8c8ef25d-722d-42a5-a397-ea5a9c3c4356\ROADMAP_UI_POLISH.md`

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
- [x] **`SEC-004` (Харденинг Reverse Proxy Caddy и заголовки безопасности)** (passing):
  - В `Caddyfile` добавлен лимит размера тела запроса `request_body { max_size 15MB }` (защита от DoS и переполнения памяти без ущерба для заявок клиентов и картинок автопостинга).
  - Настроены строгие security headers: `Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"`, `X-Content-Type-Options "nosniff"`, `X-Frame-Options "SAMEORIGIN"`, `Referrer-Policy "strict-origin-when-cross-origin"`, `Permissions-Policy`.
  - Включено удаление заголовка `-Server` для сокрытия идентификатора Caddy/uvicorn.
  - Добавлено сжатие ответов `encode zstd gzip`.
  - Написан unit-тест `tests/test_caddyfile.py`, проверяющий баланс скобок и наличие всех защитных директив.
  - Верификация: `tests/test_caddyfile.py` пройден, `ruff check` пройден, `init.ps1` пройден (код 0).
- [x] **`SEC-005` (Автоматизированное шифрованное резервное копирование БД)** (passing):
  - Разработан скрипт `scripts/backup-db.sh`: создание транзакционно-целостного дампа PostgreSQL через `docker compose exec pg_dump` без остановки БД, сжатие `gzip -9`, опциональное симметричное шифрование GPG AES-256 (`BACKUP_ENCRYPTION_PASSPHRASE`), строгие права доступа (0600) и авторотация бэкапов старше 14 дней.
  - Разработан скрипт быстрого аварийного восстановления `scripts/restore-db.sh` с поддержкой зашифрованных (`.gpg`), сжатых (`.gz`) и чистых (`.sql`) файлов.
  - Подготовлен шаблон cron-задачи `scripts/backup-cron.example` для ежедневного ночного запуска (03:00).
  - Каталог `backups/` и файлы дампов надежно скрыты в `.gitignore`.
  - Настройки резервного копирования задокументированы в `.env.example`.
  - Написан комплект тестов `tests/test_backup_scripts.py` (4 unit-теста).
  - Верификация: `pytest` (11 тестов пройдено), `ruff check` пройден, `init.ps1` пройден (код 0).
- [x] **`SEC-006` (Бастионирование хоста VPS: SSH, UFW, Fail2ban)** (passing):
  - Разработан скрипт `scripts/harden-host.sh`: принудительный протокол безопасности Zero-Lockout (проверка наличия загруженных SSH-ключей перед запретом паролей), настройка фаервола UFW (открыты только 22, 80, 443; все остальные входящие порты заблокированы), развертывание Fail2ban (бан на 24ч при 3 ошибках входа SSH), безопасный reload SSH через предварительный `sshd -t`.
  - Подготовлено детальное руководство `scripts/HOST_SECURITY.md` с командами проверки, мониторинга и разблокировки IP.
  - Разработан комплект тестов `tests/test_host_security.py` (2 unit-теста).
  - Верификация: `pytest` (13 тестов пройдено), `ruff check` пройден, `init.ps1` пройден (код 0).

- [x] **`SEC-007` (Защита от дублей сообщений: Worker claiming & идемпотентная отправка)** (passing):
  - В `get_due_funnel_states` добавлен worker claiming через `SELECT ... FOR UPDATE SKIP LOCKED` для PostgreSQL (graceful fallback для SQLite).
  - В `run_due_funnel_step` внедрен двухуровневый предохранитель:
    1. Идемпотентная проверка `last_sent_step_key` (исключение повторной отправки уже доставленного шага).
    2. Внутритранзакционный захват `in_flight_send_attempts` с TTL 300с (предотвращение гонок между параллельными воркерами).
  - В `broadcast_runner` и `followup_runner` добавлено claiming с `SKIP LOCKED` для исключения дублирования таргетов и постов.
  - Разработан комплект тестов `tests/test_worker_claiming.py` (4 unit-теста).
  - Верификация: `pytest` (17 тестов пройдено), `ruff check` пройден, `init.ps1` пройден (код 0).

- [x] **`SEC-008` (Лимиты на импорт контактов / Import Caps)** (passing):
  - Введены лимиты `MAX_IMPORT_FILE_SIZE_BYTES = 10MB` и `MAX_IMPORT_ROWS = 5000` в `inbox_database.py`.
  - Реализована безопасная потоковая отсечка в `read_import_file_rows` для XLSX и CSV до накопления избыточных строк в памяти с игнорированием пустых хвостовых строк (защита сервера от OOM и DoS).
  - В `api/inbox.py` реализован возврат HTTP 413 Payload Too Large при превышении размера файла и HTTP 422 при превышении лимита строк с информативным описанием.
  - Разработан комплект тестов `tests/test_import_caps.py` (10 unit-тестов).
  - Верификация: `pytest` (28 тестов пройдено), `ruff check` пройден, `init.ps1` пройден (код 0).

- [x] **`UI-001` (Нормализация токенов, анимационных кривых и скроллбаров)** (passing):
  - В `:root` объявлены физические кривые Безье `--ease-out: cubic-bezier(0.23, 1, 0.32, 1)`, `--ease-spring`, `--ease-in-out`, токены длительности и семантическая шкала слоев (`--z-sticky`, `--z-dropdown`, `--z-modal`, `--z-toast`).
  - Стилизованы системные скроллбары (`scrollbar-width: thin`, `scrollbar-color: var(--line) transparent`, `::-webkit-scrollbar`) в теплой бумажной гамме без серых полос Windows.
  - Устранены все `transition: all` из глобальных стилей в пользу конкретных композитных свойств.
  - Верификация: `npm run build` в `inbox-app` пройден (2.40s, 0 ошибок), `init.ps1` пройден (код 0).

### What's In Progress
- [ ] Ожидание команды пользователя на старт `SEC-009` (Харденинг Prod CORS и fail-closed обработка VK).

### What's Next
1. Взять фичу `SEC-009`: Вынос разрешенных origin CORS в настройки окружения и реализация fail-closed обработки ошибок при сбоях отправки в ВКонтакте.
2. Верифицировать через `pytest` и `init.ps1`.
3. Сделать атомарный git-коммит `security(SEC-009): ...`.

---

## Blockers / Risks
- **Risk**: Пароль приложения Яндекса был в репозитории; необходимо подтверждение пользователя о смене пароля в Яндекс ID.

---

## Decisions Made
- **2026-10-12**: Внедрена методология Harness Engineering. Все задачи выполняются строго по одной фиче за раз, с обязательным прогоном тестов, фиксацией доказательств и подтверждением перехода пользователем.
- **2026-10-12**: Добавлено строгое правило №7 в `AGENTS.md`: обязательный атомарный Git-коммит сразу после верификации каждой фичи в соответствующем репозитории до отчета пользователю.
