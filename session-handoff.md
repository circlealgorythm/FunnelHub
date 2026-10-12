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

- Завершен `SEC-009` (Харденинг Prod CORS и безопасная обработка сбоев VK / Fail-closed):
  - В `config.py` внедрен параметр `CORS_ALLOWED_ORIGINS` с гибким парсингом списков через запятую и JSON-массивов, задокументирован в `.env.example`.
  - В `main.py` захардкоженные allow_origins заменены на `settings.cors_allowed_origins`.
  - В `vk_messaging.py` создана иерархия исключений: `VkApiError`, `VkPermissionRevokedError` (ошибки 901, 902, 18), `VkTokenInvalidError` (ошибка 5).
  - В `funnel_runner.py` реализована fail-closed логика: автоматическая отписка пользователя при отзыве разрешений/приватности и пауза воронки при недействительном токене сообщества без сбоя процесса воркера.
  - Покрыто unit-тестами в `tests/test_cors_and_vk_failclosed.py` (5 тестов).

- Завершен `UI-001` (Нормализация токенов, анимационных кривых и скроллбаров):
  - Сформирован и зафиксирован реестр задач `UI-001` - `UI-007` в `ROADMAP_UI_POLISH.md` и `feature_list.json`.
  - В `:root` внедрены кривые `--ease-out: cubic-bezier(0.23, 1, 0.32, 1)`, `--ease-spring`, семантический z-index (`--z-modal`, `--z-toast`) и шкала длительностей.
  - Настроены кастомные скроллбары (`scrollbar-width: thin`, `scrollbar-color: var(--line) transparent`) в теплой бумажной гамме без серых полос Windows.
  - Устранены все `transition: all` из глобальных стилей в пользу конкретных композитных свойств.
  - Проверено: `npm run build` в `inbox-app` (2.40s), `init.ps1` (код 0).

- Завершен `UI-002` (Тактильный отклик интерактивных элементов: :active & Focus):
  - Добавлен мгновенный отклик `:active { transform: scale(0.97) }` для кнопок, табов, фильтров.
  - Добавлен мягкий отклик `:active scale(0.99)` для списка диалогов и `scale(0.98)` для таргетов ответа.
  - Настроена доступная фокус-система: подавление очертания при клике мышью (`:focus:not(:focus-visible)`) и четкий фокус-ринг `outline: 2px solid var(--plum)` при навигации с клавиатуры.
  - Настроен подсвет полей поиска (`.search-field:focus-within`, `.database-search:focus-within`).
  - Проверено: `npm run build` в `inbox-app` (2.18s, 0 ошибок), `init.ps1` (код 0).

- Завершен `UI-003` (Унификация и кинематика модальных окон):
  - Устранены дублирующиеся блоки `.modal-overlay`, `.modal-dialog`, `.modal-header`, `.modal-body`, `.modal-footer` и `.workspace.is-list-only` в `inbox-app/src/styles.css`.
  - Внедрены ключевые кадры анимаций `modal-overlay-fade-in` (120ms) и `modal-card-in` (180ms, масштаб с 0.96 со сдвигом 6px, кривая `--ease-out`).
  - Заменен хардкод `z-index: 9999` на семантический токен `var(--z-modal)`.
  - Оверлей переведен на `inset: 0`, `backdrop-filter: blur(8px)`, изоляцию прокрутки `overscroll-behavior: contain`.
  - Диалоги и модалки подтверждения стандартизированы с фоном `var(--surface-strong)`, границей `1px solid var(--line)`, радиусом `16px`, `max-height: calc(100dvh - 32px)` и внутренним скроллом тела.
  - Добавлена поддержка доступности `@media (prefers-reduced-motion: reduce)`.
  - Проверено: `npm run build` в `inbox-app` (2.29s, 0 ошибок), `init.ps1` (33 теста, код 0).

- Завершен `UI-004` (Таблицы, выравнивание данных и устранение CSS-конфликтов):
  - Удален дублирующийся блок `.lead-table-wrap`, `.lead-table th`, `.lead-table td` в конце `styles.css`.
  - Для `.lead-table` настроено `border-collapse: separate; border-spacing: 0;` для устранения мерцания sticky-заголовков.
  - Внедрен `font-variant-numeric: tabular-nums` для таблиц, дат, счетчиков, номеров телефонов и ID.
  - Разделены состояния hover (`rgba(36, 72, 60, 0.04)`) и selected (`var(--green-soft)`).
  - Проверено: `npm run build` в `inbox-app` (2.08s, 0 ошибок), `init.ps1` (33 теста, код 0).

- Завершен `UI-005` (Плавность ленты сообщений и уведомлений):
  - Реализовано органичное микродвижение появления реплик в чате `@keyframes bubble-enter` (180ms, translateY(5px) -> 0, `--ease-out`) для `.message-bubble`.
  - Улучшена пространственная анатомия бабблов (скругление 14px, скошенные уголки 4px со стороны отправителя, тональные легкие тени, поддержка `.is-inbound/.inbound` и `.is-outbound/.outbound`).
  - Для контейнера ленты `.message-stream` задано `scroll-behavior: smooth` и `overscroll-behavior-y: contain`.
  - Реализован плавный вход тостов `@keyframes toast-slide-up` (240ms, translateY(12px) -> 0), подключен `z-index: var(--z-toast)` и скругление 12px.
  - Добавлена поддержка доступности `@media (prefers-reduced-motion: reduce)`.
  - Проверено: `npm run build` в `inbox-app` (2.38s, 0 ошибок), `init.ps1` (33 теста, код 0).

## Still Broken or Unverified
- Задачи SEC-001 - SEC-009 и UI-001 - UI-005 успешно выполнены и верифицированы. Ожидает старта: UI-006.

## Next Best Action
- По команде пользователя запустить UI-006 (Состояния форм, плавная валидация и аккордеоны).

## Commands
- **Windows Verify**: `powershell -ExecutionPolicy Bypass -File .\init.ps1`
- **Linux Verify**: `./init.sh`
- **Frontend Build**: `npm run build` (в каталоге `inbox-app`)
- **Run Tests**: `uv run pytest`
- **Run Lint**: `uv run ruff check`
