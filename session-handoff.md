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

- Завершен `SEC-005` (Автоматизированное шифрованное резервное копирование БД):
  - Разработаны `scripts/backup-db.sh`, `scripts/restore-db.sh`, `scripts/backup-cron.example`.
  - Добавлена поддержка GPG AES256 шифрования, `pg_dump` без остановки БД, авторотация 14 дней.
  - Настройки задокументированы в `.env.example`, дампы изолированы в `.gitignore`.
  - Написаны тесты в `tests/test_backup_scripts.py` (4 теста).

- Завершен `SEC-006` (Бастионирование хоста VPS: SSH, UFW, Fail2ban):
  - Разработан скрипт периметра `scripts/harden-host.sh` с протоколом Zero-Lockout.
  - Написано руководство оператора `scripts/HOST_SECURITY.md`.
  - Покрыто unit-тестами в `tests/test_host_security.py` (2 теста).

- Завершен `SEC-008` (Лимиты на импорт контактов / Import Caps):
  - Введены лимиты `MAX_IMPORT_FILE_SIZE_BYTES = 10MB` и `MAX_IMPORT_ROWS = 5000` в `inbox_database.py`.
  - Реализована потоковая отсечка в `read_import_file_rows` для XLSX и CSV до накопления строк в памяти (защита сервера от OOM и DoS).
  - В `api/inbox.py` внедрен возврат HTTP 413 Payload Too Large при превышении размера файла и HTTP 422 при превышении лимита строк с информативным описанием на русском языке.
  - Покрыто unit-тестами в `tests/test_import_caps.py` (10 тестов).

- Завершен `UI-001` (Нормализация токенов, анимационных кривых и скроллбаров):
  - Сформирован и зафиксирован реестр задач `UI-001` - `UI-007` в `ROADMAP_UI_POLISH.md` и `feature_list.json`.
  - В `:root` внедрены кривые `--ease-out: cubic-bezier(0.23, 1, 0.32, 1)`, `--ease-spring`, семантический z-index (`--z-modal`, `--z-toast`) и шкала длительностей.
  - Настроены кастомные скроллбары (`scrollbar-width: thin`, `scrollbar-color: var(--line) transparent`) в теплой бумажной гамме без серых полос Windows.
  - Устранены все `transition: all` из глобальных стилей в пользу конкретных композитных свойств.
  - Проверено: `npm run build` в `inbox-app` (2.40s), `init.ps1` (код 0).

## Still Broken or Unverified
- Задачи SEC-001 - SEC-008 и UI-001 успешно выполнены и верифицированы. Ожидает старта: SEC-009.

## Next Best Action
- Запуск SEC-009 (Харденинг Prod CORS и безопасная обработка сбоев VK / Fail-closed).

## Commands
- **Windows Verify**: `powershell -ExecutionPolicy Bypass -File .\init.ps1`
- **Linux Verify**: `./init.sh`
- **Run Tests**: `uv run pytest`
- **Run Lint**: `uv run ruff check`
