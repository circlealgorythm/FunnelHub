# Session Progress Log: FunnelHub & Infrastructure Security

## Current Verified State

- **Repository root directory**: `C:\Users\circlealgorythm\Documents\Бот воронка`
- **Standard startup path**: `uv run uvicorn funnelhub.main:app --port 8000`
- **Standard verification path**: `powershell -ExecutionPolicy Bypass -File .\init.ps1` (или `uv run pytest`)
- **Active Feature**: None (all features in roadmap completed)
- **Current blocker**: Нет
- **Highest priority unfinished feature**: None (100% complete)
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
- [x] **`SEC-009` (Харденинг Prod CORS и безопасная обработка сбоев VK / Fail-closed)** (passing):
  - В `config.py` внедрен параметр `CORS_ALLOWED_ORIGINS` с гибким парсингом списков через запятую и JSON-массивов, задокументирован в `.env.example`.
  - В `main.py` захардкоженные allow_origins заменены на `settings.cors_allowed_origins`.
  - В `vk_messaging.py` создана иерархия исключений: `VkApiError`, `VkPermissionRevokedError` (ошибки 901, 902, 18), `VkTokenInvalidError` (ошибка 5).
  - В `funnel_runner.py` реализована fail-closed логика: автоматическая отписка пользователя при отзыве разрешений/приватности и пауза воронки при недействительном токене сообщества без сбоя процесса воркера.
  - Разработан комплект тестов `tests/test_cors_and_vk_failclosed.py` (5 unit-тестов).
  - Верификация: `pytest` (33 теста пройдено), `ruff check` пройден, `init.ps1` пройден (код 0).
- [x] **`UI-001` (Нормализация токенов, анимационных кривых и скроллбаров)** (passing):
  - В `:root` объявлены физические кривые Безье `--ease-out: cubic-bezier(0.23, 1, 0.32, 1)`, `--ease-spring`, `--ease-in-out`, токены длительности и семантическая шкала слоев (`--z-sticky`, `--z-dropdown`, `--z-modal`, `--z-toast`).
  - Стилизованы системные скроллбары (`scrollbar-width: thin`, `scrollbar-color: var(--line) transparent`, `::-webkit-scrollbar`) в теплой бумажной гамме без серых полос Windows.
  - Устранены все `transition: all` из глобальных стилей в пользу конкретных композитных свойств.
  - Верификация: `npm run build` в `inbox-app` пройден (2.40s, 0 ошибок), `init.ps1` пройден (код 0).
- [x] **`UI-002` (Тактильный отклик интерактивных элементов: :active & Focus)** (passing):
  - Внедрен физический отклик `:active { transform: scale(0.97) }` для всех кнопок (`.icon-button`, `.soft-button`, `.send-button`, `.login-button`, `.export-quick-btn`), табов (`.view-tab`), фильтров (`.filter-chip`).
  - Добавлен мягкий отклик `:active { transform: scale(0.99) }` для списка диалогов (`.conversation-item`) и `.reply-target` (`scale(0.98)`).
  - Настроена доступная фокус-система: подавление очертания при клике мышью (`:focus:not(:focus-visible)`) и четкий фокус-ринг `outline: 2px solid var(--plum); outline-offset: 2px` при навигации с клавиатуры.
  - Настроен подсвет полей поиска (`.search-field:focus-within`, `.database-search:focus-within`) и полей модальных окон через `var(--plum)`.
  - Верификация: `npm run build` в `inbox-app` пройден (2.18s, 0 ошибок), `init.ps1` пройден (28 тестов, код 0).
- [x] **`UI-003` (Унификация и кинематика модальных окон)** (passing):
  - Устранены дублирующиеся блоки `.modal-overlay`, `.modal-dialog`, `.modal-header`, `.modal-body`, `.modal-footer` и `.workspace.is-list-only` в `inbox-app/src/styles.css`.
  - Внедрены ключевые кадры анимаций `modal-overlay-fade-in` (120ms) и `modal-card-in` (180ms, масштаб с 0.96 со сдвигом 6px, кривая `--ease-out`).
  - Заменен хардкод `z-index: 9999` на семантический токен `var(--z-modal)`.
  - Оверлей переведен на `inset: 0`, `backdrop-filter: blur(8px)`, изоляцию прокрутки `overscroll-behavior: contain`.
  - Диалоги и модалки подтверждения стандартизированы с фоном `var(--surface-strong)`, границей `1px solid var(--line)`, радиусом `16px`, `max-height: calc(100dvh - 32px)` и внутренним скроллом тела.
  - Добавлена поддержка доступности `@media (prefers-reduced-motion: reduce)`.
  - Верификация: `npm run build` в `inbox-app` пройден (2.29s, 0 ошибок), `init.ps1` пройден (33 теста, код 0).
- [x] **`UI-004` (Таблицы, выравнивание данных и устранение CSS-конфликтов)** (passing):
  - Удален дублирующийся блок `.lead-table-wrap`, `.lead-table th`, `.lead-table td` в конце `styles.css`.
  - Для `.lead-table` настроено `border-collapse: separate; border-spacing: 0;` для устранения мерцания sticky-заголовков в браузерах.
  - Внедрен `font-variant-numeric: tabular-nums` для таблиц, дат, счетчиков, номеров телефонов и ID.
  - Разделены состояния hover (`rgba(36, 72, 60, 0.04)`) и selected (`var(--green-soft)`).
  - Верификация: `npm run build` в `inbox-app` пройден (2.08s, 0 ошибок), `init.ps1` пройден (33 теста, код 0).
- [x] **`UI-005` (Плавность ленты сообщений и уведомлений)** (passing):
  - Реализовано органичное микродвижение появления реплик в чате `@keyframes bubble-enter` (180ms, translateY(5px) -> 0, `--ease-out`) для `.message-bubble`.
  - Улучшена пространственная анатомия бабблов (скругление 14px, скошенные уголки 4px со стороны отправителя, тональные легкие тени, поддержка `.is-inbound/.inbound` и `.is-outbound/.outbound`).
  - Для контейнера ленты `.message-stream` задано `scroll-behavior: smooth` и `overscroll-behavior-y: contain`.
  - Реализован плавный вход тостов `@keyframes toast-slide-up` (240ms, translateY(12px) -> 0), подключен `z-index: var(--z-toast)` и скругление 12px.
  - Добавлена поддержка доступности `@media (prefers-reduced-motion: reduce)`.
  - Верификация: `npm run build` в `inbox-app` пройден (2.38s, 0 ошибок), `init.ps1` пройден (33 теста, код 0).
- [x] **`UI-006` (Состояния форм, плавная валидация и аккордеоны)** (passing):
  - Реализованы правила псевдоклассов `:user-invalid` и `:user-valid` (Modern Web Guidance), предотвращающие преждевременное окрашивание незаполненных полей до взаимодействия.
  - Настроен плавный фокус и мягкая подсветка для textarea поля ответа оператора.
  - Аккордеоны `details`/`summary` получили плавный hover, `:focus-visible` ринг и анимацию входа содержимого `@keyframes details-body-fade` (120ms).
  - Скелетоны (`.skeleton-row`, `.skeleton-message`) переведены на мягкий тональный градиент и плавный shimmer (1.8s, ease-in-out).
  - Добавлена поддержка `prefers-reduced-motion: reduce`.
  - Верификация: `npm run build` в `inbox-app` пройден (2.34s, 0 ошибок), `init.ps1` пройден (33 теста, код 0).
- [x] **`UI-007` (Очистка AI-паттернов и строгая типографика)** (passing):
  - Проведен полный аудит кодовой базы frontend: устранены все 11 символов длинного тире `—` (U+2014) в пользу аккуратных дефисов `-` в плейсхолдерах и профессиональных формулировок («Непокупатели: два сценария коммуникации», «Миграция: база непокупателей», «TG: ... / VK: ...»).
  - Повторный скриптовый поиск подтвердил 0 вхождений U+2014 во всех файлах `inbox-app/src`.
  - Пройден Pre-Flight чек-лист Design Taste: контрастность, читаемость, сохранение 100% брендовой теплой палитры, плавность всех переходов.
  - Верификация: `npm run build` в `inbox-app` пройден (2.38s, 0 ошибок), `init.ps1` пройден (33 теста, код 0).

- [x] **Деплой на прод и синхронизация с GitHub**:
  - Все коммиты фич UI Polish (`UI-001` - `UI-007`), настройки базы лидов (дефолт 50 лидов и 4 раскрытых аккордеона) и обогащения Яндекс Метрики / GetCourse отправлены в GitHub (`git push origin main`, коммит `239fd26`).
  - Фронтенд успешно собран в продакшн бандл `inbox-app/dist`.
  - Синхронизированы файлы проекта и выполнен удаленный деплой через `deploy_files.py`.
  - Успешно собраны Docker-образы всех сервисов, выполнена миграция базы данных `alembic upgrade head`.
  - Перезапущены и активны все контейнеры: `funnelhub-app-1`, `funnelhub-funnel-worker-1`, `funnelhub-most-funnel-worker-1`, `funnelhub-most-telegram-bot-1`, `funnelhub-most-vk-funnel-worker-1`, `funnelhub-telegram-bot-1`.
  - Эмпирическая проверка: эндпоинт `/inbox/` вернул HTTP 200 OK.

- [x] **Переименование вкладки и разделов в «Авторассылка» (2026-10-16)**:
  - Вкладка навигации, шапка раздела, модальные окна создания и редактирования переименованы в «Авторассылка».
  - Сборка фронтенда `inbox-app` (`tsc -b && vite build`) успешно выполнена (2.31s, бандл `index-MHbuRc-_.js`).
  - Верификация `verify.ps1` пройдена (8 passed, mypy passed, ruff passed).
- [x] **Ручная отписка лида от рассылки Unisender Go & FunnelHub (2026-10-17)**:
  - Обработано обращение по отписке лида Денис Трефелов (`GC 519650619`, `denistrefelov868@gmail.com`).
  - В Unisender Go через API endpoint `suppression/set.json` email занесен в `suppression list` (`cause: unsubscribed`, `source: user`), гарантируя блокировку любых последующих отправок на уровне почтового провайдера.
  - В базе данных FunnelHub на проде запись `EmailSubscription` переведена в статус `unsubscribed` с фиксацией `unsubscribed_at`, активная воронка `aisu_email_sequence` (`step=day_09`) переведена в `paused` со сбросом `next_run_at=None`, залогировано системное событие `email.unsubscribed`.
  - Разработан стандартный CLI-скрипт `scripts/unsubscribe-lead.py` и операционный регламент `SOP-EMAIL-001` в `AGENTS.md` для автоматизации последующих аналогичных операций.
  - Верификация: `scripts/verify.ps1 -Subproject funnel-hub` успешно пройден (8 passed, ruff passed, mypy passed, 0 ошибок).
- [x] **Деактивация архивных сервисов проекта «Мост ценностей» (2026-10-17)**:
  - Устранен циклический перезапуск контейнера `funnelhub-most-telegram-bot-1` (ошибка 401 Unauthorized из-за отозванного токена).
  - По согласованию с пользователем остановлены все сервисы профиля `most`: `funnelhub-most-telegram-bot-1`, `funnelhub-most-funnel-worker-1` и `funnelhub-most-vk-funnel-worker-1`.
  - Зафиксирован регламент `SOP-OPS-002` в `AGENTS.md`: сервисы профиля `most` архивированы и не должны запускаться в штатном режиме.
  - На боевом сервере оставлены только активные сервисы школы «Сатья-Юга» (`app`, `telegram-bot`, `funnel-worker`, `redis`, `postgres`).

### What's In Progress
*None (all features and production deployment complete)*

### What's Next
1. Ожидание указаний пользователя по дальнейшим задачам.

---

## Blockers / Risks
- **Risk**: Пароль приложения Яндекса был в репозитории; необходимо подтверждение пользователя о смене пароля в Яндекс ID.

---

## Decisions Made
- **2026-10-12**: Внедрена методология Harness Engineering. Все задачи выполняются строго по одной фиче за раз, с обязательным прогоном тестов, фиксацией доказательств и подтверждением перехода пользователем.
- **2026-10-12**: Добавлено строгое правило №7 в `AGENTS.md`: обязательный атомарный Git-коммит сразу после верификации каждой фичи в соответствующем репозитории до отчета пользователю.

- **2026-10-16 23:01** | docs(funnel-hub): add context bridge to harness standards

- **2026-10-17 13:19** | feat(funnel-hub): add unsubscribe-lead script and record SOP-EMAIL-001

- **2026-10-17 16:35** | ops(funnel-hub): stop and archive Most Tsennostey services (SOP-OPS-002)


- **2026-10-17 16:35** | ops(funnel-hub): archive most-tsennostey services and record SOP-OPS-002
