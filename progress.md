# Session Progress Log: FunnelHub & Infrastructure Security

## Current Verified State

- **Repository root directory**: `C:\Users\circlealgorythm\Documents\Бот воронка`
- **Standard startup path**: `uv run uvicorn funnelhub.main:app --port 8000`
- **Standard verification path**: `pwsh -ExecutionPolicy Bypass -File scripts/verify.ps1 -Subproject funnel-hub` (или `uv run pytest`)
- **Active Feature**: None (all features in roadmap completed)
- **Current blocker**: Нет
- **Highest priority unfinished feature**: None (100% complete)
- **Roadmap Artifact**: `C:\Users\circlealgorythm\.gemini\antigravity\brain\8c8ef25d-722d-42a5-a397-ea5a9c3c4356\ROADMAP_UI_POLISH.md`

---

## Status

### What's Done
- [x] **`DATA-002` (Массовый импорт пользователей GetCourse в базу лидов через API: 1188 пользователей, 823 новых лида)** (passing):
  - Найден и подтверждён рабочий ключ `GETCOURSE_API_KEY` (`.env.recovery.template`, проверка 2026-11-05); выяснены фильтры API: полная выгрузка = `created_at[from]/[to]` (без фильтра error_code 908), группы = `idgrouplist=id_date`.
  - Выгружены и распарсены все 1188 пользователей GC (export 90643107) + членство в группах (export 90643875, 794 связки, 17 групп). Установлено: JSON API приходит чистым UTF-8 — консольный mojibake является артефактом отображения (см. `.harness/lessons.md` STD-021), перекодировки запрещены.
  - Подготовлены TSV-стейджинг (`scripts/getcourse-import/`): users.tsv 1188×28 (телефоны нормализованы к 7-префиксу, технические `@vktech.gc` отсечены), groups.tsv 794×4.
  - Сопоставление с базой (приоритет vk > email > phone, 1:1): 363 склейки (297 vk / 1 email / 66 phone), 823 новых лидов, 2 пропущены как созданные вебхуками во время импорта (guard от гонки — STD-DATA-004).
  - Боевой импорт на Simplecloud через dry-run (BEGIN/ROLLBACK) → pg_dump (`pre_gc_import_20261106.dump`, сервер + локальная копия, md5 сверены) + скрипт отката `/tmp/gc_import/rollback_gc_import.sh` → COMMIT: leads 500→1323, gc-linked 1188, email-контактов 1025, телефонов 913, UTM 872 (source_kind='import'), тегов групп 794, кастомных полей Да/Нет 1033, external_ids 1186 getcourse + 313 vk.
  - Импортированным VK-лидам добавлены 15 идентичностей со `is_subscribed=false` (STD-DATA-005) — колонка КАНАЛ показывает VK, боты им не пишут.
  - **Корректировка объёма (решение пользователя 2026-11-06):** база FunnelHub должна содержать только лидов с момента запуска проекта (создан 20.05.2026 — дата папки и первого коммита). Выполнена чистка: удалены 698 импортированных лидов с регистрацией в GC ранее 2026-05-27 (каскадно их контакты/UTM/теги/идентичности); dry-run каскада подтвердил 0 диалогов и 0 воронок у удаляемых. Граница сверена: min gc_created среди оставшихся импортированных = 2026-05-27. **Итог базы: 624 лида** (vk_recovery 408, getcourse 125, landing_consultation 78, landing_consultation+vk 8, blog 2, прочие 3). Дамп до чистки `pre_gc_cleanup_20261106.dump` (сервер + локально) + скрипт отката `/tmp/gc_import/rollback_gc_cleanup.sh`.
  - Два сбоя в процессе (гонка вебхуков duplicate key gc_id 504948483; lead_tags.id без server_default) оба авто-откатились с нулевыми изменениями и устранены guard-ами; вебхуки и воронки в момент импорта не прерывались, массовые рассылки не запускались (email_subscriptions сознательно не создавались — решение пользователя).

- [x] **`UI-GC-BADGE` (Серый бейдж GC в колонке КАНАЛ базы лидов Inbox)** (passing):
  - В `inbox-app/src/App.tsx` ячейка КАНАЛ: при отсутствии TG/VK-идентичностей и наличии `getcourse_user_id` рендерится бейдж `GC` с тултипом «Импортирован из GetCourse: диалога с ботом пока не было».
  - В `inbox-app/src/styles.css` добавлен `.lead-channel-gc-badge` в тёплой серой гамме (в тон заголовков таблицы).
  - `npm run build` — 2.50s, exit 0; `verify.ps1 -Subproject funnel-hub` — 18 passed.
  - **Боевой деплой выполнен 2026-11-06** (команда пользователя «выкатывай»; `deploy_files.py`: загрузка чистого `inbox-app/dist`, пересборка образов app/funnel-worker/telegram-bot/most-*, alembic upgrade head, up -d, caddy reload). Подтверждено: `/inbox/` HTTP 200, отдаётся бандл `assets/index-CJ539ubP.js`, класс `lead-channel-gc-badge` присутствует в отдаваемом JS (grep = 1), ошибок в логах app нет.
  - **Итерация 2 (фидбек пользователя):** (1) бейдж больше не растягивается на всю ячейку — правило с более высокой специфичностью `.lead-table td span.lead-channel-gc-badge` + `width: fit-content` (перебивало родовое `display: block` для `td span`); (2) колонка КАНАЛ показывает реальный канал, если он есть: в `build_lead_summary_query` добавлены флаги `has_telegram/has_vk/has_max` (идентичность ИЛИ диалог, БЕЗ фильтра is_subscribed — отображение отделено от права на рассылку STD-DATA-005), канал MAX добавлен в `channelLabels`/`leadMessengerLabels`. Затронуто: 15 VK-лидов из GC (identity is_subscribed=false ранее скрывалась фильтром) и 65 лидов с диалогами в MAX. Деплой подтверждён: бандл `index-rcu3iNV1.js`, `has_max` в отдаваемом JS, HTTP 200, ошибок нет.
  - **Итерация 3 (фидбек пользователя: MAX-канал не реализован, бейдж убран):** пользователь подтвердил, что канала MAX в системе нет (был только в планах); расследование выявило источник — 79 пустых диалогов-оболочек `channel='max'` в БД (созданы 2026-10-10…2026-11-05, **0 сообщений**, среди лидов есть тестовый — мусор от октябрьских экспериментов). Выполнено: MAX удалён из `channelLabels`/`leadMessengerLabels`, флаг `has_max` убран по всей цепочке (SQL-запрос, датакласс, API, типы фронта); бейдж GC из колонки КАНАЛ убран по решению пользователя — при отсутствии каналов отображается честный текст «нет подписок»; CSS-правило бейджа удалено. Флаги `has_telegram/has_vk` сохранены (реальные каналы — чинят отображение 15 VK-лидов из GC). Деплой подтверждён: бандл `index-CrxPuY1n.js`, `has_max` и `lead-channel-gc-badge` в отдаваемом JS = 0, «нет подписок» присутствует, HTTP 200, ошибок нет. Урок — STD-UI-001 в `AGENTS.md`.
  - **Атрибуция уточнена:** 79 оболочек `channel='max'` создал recovery-скрипт `scripts/recover_crm_leads.py` (MIG-004, коммит 3726fad): при переносе 87 CRM-лидов из Google Sheets в нём захардкожен `channel="max"` как заглушка «канал ещё не выбран»; даты 10.10–05.11 — даты заявок, скопированные из CRM; сами лиды настоящие.
  - **Чистка мусора (2026-11-06 22:33, команда пользователя «почисти»):** guard-транзакция (RAISE при отклонении от ожидаемого состояния) подтвердила ровно 79 пустых max-диалогов и 0 сообщений → `DELETE 79`. Итог: `max_remaining=0`, conversations 419. Дамп `pre_max_cleanup_20261106.dump` (сервер + локально) + `rollback_max_cleanup.sh` на сервере. Лиды SQL-ом не затрагивались; leads_total на 22:33 = 620 (−4 к счёту 624 на 21:00: getcourse −1, landing −1, null-source −2 — **подтверждено пользователем: это его ручные удаления в админке**, не следствие операций агента).

- [x] **`SOP-BACKUP-001` (План слияния при возврате бэкапа Beget VPS)** (план согласован, исполнение по факту получения дампа):
  - Зафиксирован в `AGENTS.md`: загрузка бэкапа в отдельную схему `beget_restore`, слияние лидов по приоритету getcourse_user_id → VK → телефон → email (Phone-First), перенос переписки `conversations/messages` с дедупликацией по `external_message_id`, объём-правило (не воскрешать GC-лидов до 2026-05-27), разрешение UNIQUE-конфликтов в пользу прода, `lead_tags.id` явно, чужие VK-идентичности `is_subscribed=false`, dry-run → ревью → COMMIT → POST-MERGE VERIFY.

- [x] **`TG-PROXY-001` (Интеграция Telegram Bot API через Cloudflare Worker на Simplecloud VPS)** (passing):
  - Диагностирована и ликвидирована блокировка ТСПУ на порт 443 к IP пулам Telegram (`149.154.*`) на сервере Simplecloud VPS (`85.143.175.148`).
  - Развернут бессерверный Cloudflare Worker Reverse Proxy (`lingering-forest-a1b9.circlealgorythm.workers.dev`), проксирующий запросы к `api.telegram.org` без задержек и ограничений (TLS 40ms, Bot API 100ms).
  - В `src/funnelhub/services/telegram_messaging.py` внедрена фабрика `create_telegram_bot(token, settings)` с поддержкой `TELEGRAM_API_BASE_URL` и `TELEGRAM_PROXY_SECRET`.
  - Все сервисы (`funnel_worker`, `telegram_bot`, `inbox`, `inbox_notifications`) переведены на фабрику.
  - В `src/funnelhub/telegram_bot.py` настроен `polling_timeout=10` для синхронизации с edge-таймаутами Cloudflare.
  - Контейнеры `app`, `funnel-worker` и `telegram-bot` на боевом сервере пересобраны и запущены; поллинг `@vedicschool_aisu_bot` стабилен, pending updates = 0.

- [x] **`VK-CONFIRM-001` (Синхронизация VK Callback API confirmation code для bot.aisukam.ru)** (passing):
  - При переключении адреса Callback API в сообществе `shamanaisu` с Beget на `https://bot.aisukam.ru/webhooks/vk` актуализирован `VK_CONFIRMATION_CODE=efefcce1` в конфигурации бэкенда.
  - В сообществе ВК получена зеленая галочка подтверждения сервера, включены события `message_new` и `message_allow`.

- [x] **`E2E-FUNNEL-001` (Полная верификация сквозной цепочки заявки, join-страницы и запуска ботов)** (passing):
  - Проверена сквозная цепочка: отправка формы -> создание лида в PostgreSQL и CRM -> генерация `/join/{token}` -> рендеринг кнопок Telegram и VK -> подписка на ботов.
  - Вебхук GetCourse проверен (ответ HTTP 200 за 0.17 с).
  - Верификатор `verify.ps1 -Subproject funnel-hub` успешно пройден (18 unit-тестов, ruff, mypy).
- [x] **`UX-VK-001` (Инструкция «Разрешить сообщения» на странице спасибо для автостарта VK-воронки)** (passing):
  - Диагностика боевого автостарта (2026-11-06): механизм ref-автостарта работает — лид Ксения (VK ID 258149228) получила первое сообщение через 1.5 мин после заявки (funnel_states.restart_reason="bot_start", 15:56:37 UTC) по событию VK с ref-токеном. Тест с новым аккаунтом (лид «Светлана типа заяц») показал ноль событий: VK не отправляет сообществу колбэк при простом открытии чата — платформенное ограничение (message_allow подписан в Callback API сообщества, проверено скриншотом настроек).
  - В `src/funnelhub/api/messenger.py` (render_join_page) сноска под кнопками дополнена инструкцией: «В открывшемся чате подтвердите запуск: в VK нажмите "Разрешить сообщения", в Telegram — "Запустить"» — одно касание пользователя вместо набора текста, конверсия не страдает.
  - VK OAuth-флоу (`vk_oauth.py`) для этой задачи отклонён пользователем (длинный пользовательский путь, снижение конверсии).
  - Верификация: `scripts/verify.ps1 -Subproject funnel-hub` (ruff, mypy 54 файлов, 18 unit-тестов) — код 0; `tests/test_join_page.py` — 2 passed. Ошибки `tests/test_getcourse_webhook.py` (37) — pre-existing ConnectionRefusedError локальной Postgres в фикстуре, подтверждены на чистом коде без правки (git stash probe).
  - Деплой на боевой Simplecloud — вручную после ревью (`deploy_files.py`).
- [x] **`EMAIL-001` (Защита квоты Unisender Go: супрессия тестовых адресов и фильтрация @gmail.com)** (passing):
  - В `src/funnelhub/services/email_messaging.py` внедрена функция `is_test_email(email)`: отсечение тестовых адресов с корнем "алгоритм" (`.*al[go]r[yi]thm.*@gmail\.com`) ограничено строго доменом `@gmail.com` (корпоративные и сторонние домены реальных клиентов разрешены); ящики `jogspokoen@*`, `test-webhook@*` и `ADMIN_EMAILS` отсекаются безусловно.
  - В `src/funnelhub/services/funnel_autostart.py` заблокирован автостарт email-воронок для тестовых ящиков.
  - В `src/funnelhub/services/getcourse_webhook.py` при создании подписки тестовый email автоматически маркируется `unsubscribed`.
  - В Unisender Go API через `suppression/set.json` занесены 8 тестовых адресов с причиной `unsubscribed`.
  - В боевой PostgreSQL БД тестовые подписки переведены в `unsubscribed`, а активные воронки в `paused`.
  - Покрыто unit-тестами в `tests/test_email_messaging.py` (`test_is_test_email_detection`). Прогон `verify.ps1` успешно пройден (18 unit-тестов, ruff, mypy).

- [x] **`DATA-001` (Интеграция CRM-лидов из Google Sheets и Phone-First сопоставление с VK ID)** (passing):
  - Проведен сквозной аудит 87 лидов из Google Sheets CRM и 417 лидов из VK бота через VK API (`messages.getHistory`).
  - Утвержден и применен инвариант слияния: объединение карточек выполняется строго по подтвержденному совпадению номера телефона (`Phone-First`) либо 100% доказанной связке по таймстампу/форме/DEF-коду региона, исключая ложные слияния однофамильцев.
  - На боевом сервере Simplecloud VPS выполнен транзакционный merge для 8 подтвержденных пар лидов (обновлен источник `landing_consultation + vk`, привязаны client_id Метрики, история контактов и VK ID).
  - Оставшиеся 79 лидов CRM сохранены как независимые записи с источником `landing_consultation`. Итоговый баланс базы: 8 `landing_consultation + vk`, 79 `landing_consultation`, 409 `vk_recovery`.

- [x] **MIG-007 (Демонтаж SmartCaptcha в API, деплой на Simplecloud и обогащение 417 VK-лидов)** (passing):
  - Из isu_landing_application в unnelhub/api/webhooks.py полностью удалена проверка SmartCaptcha; smartcaptcha_token переведен в необязательное поле (Field(default=None)).
  - Контейнер pp пересобран и перезапущен на Simplecloud (85.143.175.148).
  - Разработан и исполнен скрипт scripts/enrich_vk_leads.py: через VK API (users.get) все 417 VK-лидов обогащены реальными именами, фамилиями, городами и доменами (вместо 'Без имени').
  - Верификация: live probe через форму на основном сайте создал лид в PostgreSQL и выдал персональный join_url (код 202 accepted).

- [x] **`MIG-002` (Деплой сервисов FunnelHub, Caddy и инициализация PostgreSQL)** (passing):
  - Сгенерирован боевой `/opt/funnelhub/.env` на базе шаблона восстановления: хост БД переведен на `postgres:5432`, брокер на `redis:6379`, экранированы спецсимволы `$$` в хеше пароля админки, обновлены валидные токены.
  - В `deploy_files.py` включен каталог `public/` (критично для сборки Dockerfile).
  - На хосте установлен и настроен веб-сервер Caddy (`/etc/caddy/Caddyfile`), проверен редирект на HTTPS.
  - Собраны Docker-образы и запущены сервисы хранилища и бэкенда (`postgres`, `redis`, `app`).
  - Выполнены миграции `alembic upgrade head`: в базе созданы все 24 таблицы (`leads`, `lead_contacts`, `messenger_identities`, `funnel_states`, `conversations`, `messages`, `email_subscriptions` и др.).
  - Сервисы ботов и воркеров воронок намеренно удержаны в остановленном состоянии до выполнения восстановления данных (Anti-Spam Invariant).
  - Верификация: `curl http://127.0.0.1:8000/health` вернул `{"status":"ok","service":"FunnelHub"}` (HTTP 200 OK); `inbox-app` возвращает собранный HTML; Postgres подтвердил наличие 24 таблиц.
- [x] **`MIG-001` (Базовая подготовка сервера Simplecloud: Docker, Swap, UFW, fail2ban)** (passing):
  - Выделен и активирован `/swapfile` размером 4.0 ГБ с `vm.swappiness = 20` (критично для защиты от OOM в условиях 1 CPU / 4GB RAM).
  - Установлены `Docker Engine 29.9.3` и `Docker Compose v5.7.0` из официального репозитория Docker.
  - Настроен межсетевой экран `UFW`: запрет входящих подключений по умолчанию, открыты строго порты `22/tcp` (SSH), `80/tcp` (HTTP) и `443/tcp` (HTTPS).
  - Активирован и запущен демон `fail2ban` для защиты от брутфорса SSH.
  - Создан целевой каталог `/opt/funnelhub` с правами `0755`.
  - Верификация: `docker --version`, `docker compose version`, `ufw status verbose`, `free -h` — все службы активны, код возврата 0.
- [x] **`MIG-000` (Подготовка нового VDS Simplecloud и настройка SSH по Ed25519-ключу)** (passing):
  - В `C:\Users\circlealgorythm\Documents\VDS\` сгенерирована пара ключей `Simplecloud_ed25519` и `Simplecloud_ed25519.pub`.
  - Публичный ключ установлен в `~/.ssh/authorized_keys` на хосте `85.143.175.148` (права `0700` / `0600`).
  - Переменные окружения в `projects/funnel-hub/.env` и корневом `.env` переключены на новый хост (`SSH_HOST=85.143.175.148`, `SSH_KEY_PATH=C:/Users/circlealgorythm/Documents/VDS/Simplecloud_ed25519`), старые настройки Beget сохранены в виде комментариев.
  - Верификация: выполнено прямое подключение через `ssh.exe` без пароля; хост `345523.simplecloud.ru` подтвердил ОС `Ubuntu 24.04.5 LTS`, `load average: 0.24`, код возврата 0.
- [x] **`UI-010 / Fix` (Полировка карточки лида: удаление фейк-аватарки, скрытие пустого источника и выравнивание кнопок действий в 2 колонки)** (passing):
  - В `inbox-app/src/App.tsx` удалена дефолтная иконка-заглушка пользователя (`<div className="avatar"><UserRound size={22} /></div>`) в карточке `LeadDatabaseDetail`.
  - Устранена избыточная надпись «Источник не указан»: блок источника переведен на условный рендеринг `{detail.lead.source ? <p>...</p> : null}`, отображаясь только когда источник реально задан (например, «Блог Айсу Кам»).
  - Кнопки действий («Написать в Inbox» и «Удалить лида») выровнены в аккуратную 2-колоночную сетку по 50% ширины (`display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; width: 100%`), идеально совпадающую с сеткой блоков статистики «Диалоги» и «Сообщения» непосредственно под ними.
  - Устранен визуальный перекос кнопок вправо из-за `justify-content: flex-end`, стандартизирована высота (38px), отступы и добавлен `text-overflow: ellipsis`.
  - Устранены ошибки форматирования E501 в `deploy_files.py`.
  - Верификация: `npm run build` (inbox-app) успешно завершен (код 0, 2.62s); `scripts/verify.ps1 -Subproject funnel-hub` успешно пройден (ruff OK, mypy 54 OK, pytest 18 passed); боевой деплой на Beget VPS (`deploy_files.py`) выполнен, эндпоинт `https://bot.aisukam.ru/inbox/` возвращает HTTP 200 OK.
- [x] **\SEC-009 / Feature 5\ (Внедрение Content-Security-Policy в Caddyfile и устранение уязвимостей npm)** (passing):
  - В \Caddyfile\ добавлена строгая директива \Content-Security-Policy\ с доверенными источниками для скриптов, стилей, изображений и подключений WebSocket/API (\ot.aisukam.ru\, \cdn.jsdelivr.net\).
  - В \	ests/test_caddyfile.py\ добавлен тест наличия \Content-Security-Policy\.
  - В \inbox-app\ выполнен аудит и безопасное обновление npm-зависимостей (pm audit fix\), устранивший 6 уязвимостей (найдено 0 уязвимостей).
  - Верификация: \scripts/verify.ps1 -Subproject funnel-hub\ успешно пройден (ruff OK, mypy OK, pytest 18 passed); сборка \inbox-app\ завершилась с кодом 0 за 2.62s.
- [x] **`SEC-008 / Feature 3` (Санитизация экспорта CSV/Excel от Formula Injection и отзыв сессий при логауте)** (passing):
  - В `src/funnelhub/services/inbox_database.py` внедрена функция `sanitize_spreadsheet_cell` (CWE-1236 / OWASP Formula Injection). Все формульные триггеры (`=`, `@`, `\t`, `\r`, а также `+` и `-` без последующих чисел) экранируются одинарной кавычкой `'`, при этом стандартные телефонные номера (`+7999...`) и отрицательные числа сохраняются в исходном виде.
  - Санитизация интегрирована в функции экспорта базы лидов `export_database_leads_csv` и `xlsx_cell_value` (в `export_database_leads_xlsx`).
  - В `src/funnelhub/services/auth.py` в сессионные токены добавлен криптографический идентификатор `jti` (16 байт) и реализован механизм отзыва сессий `revoke_session` с автоочисткой устаревших записей.
  - В `src/funnelhub/api/auth.py` в эндпоинт `POST /api/auth/logout` добавлена инвалидация сессионного токена (повторный replay украденной куки после логаута возвращает 401).
  - Верификация: добавлены тесты `test_sanitize_spreadsheet_cell_formula_injection` и `test_logout_revokes_session_cookie` в `tests/test_auth.py`; `scripts/verify.ps1 -Subproject funnel-hub` успешно пройден (ruff OK, mypy OK, pytest 18 passed).
- [x] **`SEC-007 / Feature 2` (Защита от спуфинга IP в Rate Limiter и харденинг VK вебхуков)** (passing):
  - В `src/funnelhub/services/ingestion_guard.py` исправлена функция `get_request_ip`: парсинг `X-Forwarded-For` теперь берет последний IP (`ips[-1]`), добавленный доверенным локальным реверс-прокси Caddy, вместо первого (клиентского), исключая обход лимитов авторизации `/api/auth/login` спуфингом заголовка.
  - В `InMemoryRateLimiter` внедрена очистка устаревших корзин при превышении лимита размера (>500 записей), предотвращая утечку RAM при длительной работе сервиса (Slow DoS).
  - В `src/funnelhub/api/webhooks.py` валидация секрета VK переведена на `secrets.compare_digest` (защита от тайминг-атак) и добавлена валидация `group_id` при наличии настроенных групп.
  - Сохранен 100% контракт работы GetCourse вебхуков и форм заявок без блокировок.
  - Верификация: добавлены тесты `test_login_rate_limiting_ip_spoofing_prevention`, `test_rate_limiter_memory_pruning`, `test_validate_vk_secret_constant_time`; `scripts/verify.ps1 -Subproject funnel-hub` успешно пройден (ruff OK, mypy OK, pytest 16 passed).
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
- [x] **Сегментация заявок «Сайт vs Блог» и учет статьи обращения (2026-10-25)**:
  - В `webhooks.py` добавлены поля `article_title` и `article_url` в `AisuLandingApplicationRequest`, с сохранением в `LeadCustomField` («Статья блога», «Ссылка на статью») и фиксацией `source='blog'` в задачах лида.
  - В `getcourse_webhook.py` зарегистрированы алиасы `article_title` и `article_url` в `KNOWN_ADDITIONAL_FIELD_ALIASES` и `ADDITIONAL_FIELD_LABELS`.
  - В `inbox_database.py` и `inbox.py` функция `lead_exclude_source_filter` и `list_inbox_conversations` обновлены для поддержки мульти-источников через запятую (`exclude_source='most-tsennostey,blog'`).
  - Поля `article_title` и `article_url` включены в `DatabaseLeadSummary`, ответ `DatabaseLeadResponse`, а также в колонки экспорта `XLSX_EXPORT_COLUMNS` и `CSV_EXPORT_COLUMNS`.
  - В `inbox-app/src/App.tsx` добавлены сегменты `blog` в `databaseSegments` и `inboxSegments`. В таблице лидов выводится бейдж 📄 <Статья>, в детальной панели лида выводится интерактивная карточка со статьей и прямой ссылкой, а запросы фильтруются: `main` исключает `most-tsennostey,blog`, а `blog` запрашивает `source=blog`.
  - В `inbox-app/src/styles.css` добавлены стили `.lead-article-badge` и `.lead-blog-article-card`.
  - Выполнен боевой деплой на Beget VPS (`31.129.110.56`) через `deploy_files.py`: `docker compose build`, `alembic upgrade head`, перезапуск сервисов (`app`, `funnel-worker`, боты).
  - **Доказательство (Evidence):**
    - Создан набор unit-тестов `tests/test_blog_segmentation.py` (6 тестов: Pydantic-валидация, компиляция SQL-фильтров исключения и источников, экспортные колонки, формирование модели лида).
    - `scripts/verify.ps1 -Subproject funnel-hub` — 14 passed (100%), ruff passed, mypy (54 файла) passed, код выхода 0 (9.29s).
    - `inbox-app` собран: `tsc -b && vite build` — exit code 0 (2.35s).
    - Боевой HTTP статус: `curl.exe -s -o NUL -w "%{http_code}" https://bot.aisukam.ru/inbox/` — **200 OK**.
    - Боевой статус сайта: `curl.exe -s -o NUL -w "%{http_code}" https://aisukam.ru/blog/` — **200 OK**.

- [x] **Реактивация проекта «Мост ценностей» и строгая изоляция базы (2026-10-21)**:
  - В админке `inbox-app` восстановлены сегменты «Основной Inbox» / «Мост ценностей» и «Общая база» / «Мост ценностей», добавлены бейджи каналов `telegram_most` и `vk_most` и поддержка ответов из карточки.
  - В `inbox_database.py` и `inbox.py` внедрен `lead_exclude_source_filter`: лиды, оставившие заявку на «Мост ценностей» (включая лидов со склейкой GetCourse ID), строго исключаются из «Общей базы» школы и отображаются только в сегменте «Мост ценностей» (`STD-FUNNEL-001`).
  - В `docker-compose.prod.yml` сервисы `most-telegram-bot`, `most-funnel-worker` и `most-vk-funnel-worker` возвращены в штатный запуск.
  - Боевой деплой на Beget VPS (`31.129.110.56`): обновлены переменные `MOST_TELEGRAM_BOT_TOKEN` и `MOST_TELEGRAM_BOT_USERNAME=most_cannostei_bot`, контейнеры пересобраны и запущены.
  - **Доказательство (Evidence):**
    - `tests/test_most_tsennostey_applications.py`: обновлен контракт `test_existing_lead_submitting_most_is_isolated_to_most_segment` (`assert existing_lead_id not in [item.id for item in main_leads.items]`).
    - Логи контейнеров на проде: `funnelhub-most-telegram-bot-1` (Up, polling для `@most_cannostei_bot`, обработаны `Update id=839195251`, `839195252`), `funnelhub-most-funnel-worker-1` (`Most funnel runner pass completed`), `funnelhub-most-vk-funnel-worker-1` (`Most VK funnel runner pass completed`).
    - `https://bot.aisukam.ru/inbox/` — HTTP 200 OK.
    - `scripts/verify.ps1 -Subproject funnel-hub` — 8 passed, ruff passed, mypy passed.

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

- **2026-10-21 14:26** | feat(funnel-hub): restore most-tsennostey segment and bot services

- **2026-10-21 14:34** | docs(funnel-hub): update SOP-OPS-002 for most-tsennostey reactivation

- **2026-10-21 14:38** | docs(funnel-hub): record STD-FUNNEL-001 and production reactivation evidence

- **2026-10-25 14:08** | feat(funnel-hub): support blog lead segmentation, article display and multi-source exclusion

- **2026-10-25 14:20** | docs(funnel-hub): update harness artifacts, record STD-FUNNEL-002 and SEG-001

- **2026-10-26 01:59** | security(funnel-hub): fix IP spoofing in rate limiter and harden VK webhook validation

- **2026-10-26 02:05** | security(funnel-hub): sanitize CSV/Excel exports and add session revocation

- **2026-10-26 02:25** | security(funnel-hub): configure CSP in Caddyfile and fix inbox-app dependencies

- **2026-10-26 02:34** | fix(funnel-hub): support parentheses in phone number formula sanitization

- [x] **Восстановление состояния VK-воронки из истории переписок VK API (2026-11-05, MIG-003)**:
  - Разработан и отлажен скрипт `scripts/recover_vk_funnel.py` для автоматического извлечения истории переписок через VK API (`messages.getConversations`, `messages.getHistory`).
  - Проанализировано 418 диалогов: 1 групповой чат пропущен, 417 пользователей классифицированы.
  - Применен строгий Anti-Spam инвариант:
    - 401 пользователь переведен в статус `completed` (`day_18`, ручные консультации, завершенные вещания, архивные диалоги) — защищены от повторного запуска.
    - 16 активных пользователей поставлены в очередь со своими текущими шагами и безопасным интервалом `next_run_at`.
  - В базу данных PostgreSQL на Simplecloud (`85.143.175.148`) загружено 417 лидов (`leads`), 417 идентификаторов мессенджера (`messenger_identities`), 417 открытых диалогов (`conversations`) и 417 состояний воронок (`funnel_states`).
  - **Доказательство (Evidence):**
    - `psql -c 'SELECT count(*) FROM leads; SELECT count(*) FROM messenger_identities; SELECT status, count(*) FROM funnel_states GROUP BY status;'`:
      - `leads`: 417
      - `messenger_identities`: 417
      - `funnel_states`: active = 16, completed = 401
    - Команда `scripts/verify.ps1 -Subproject funnel-hub` завершилась с кодом 0 (18 passed, ruff clean, mypy clean).

- [x] **Импорт лидов Telegram и CRM из Google Sheets CRM (2026-11-06, MIG-004)**:
  - Разработан и отлажен скрипт `scripts/recover_crm_leads.py` для парсинга выгрузки таблицы Google Sheets CRM («Лиды из Базы - Лиды.csv»).
  - Обработана 91 запись заявок на консультацию с сайта (`aisukam.ru`):
    - Дедупликация по нормализованному номеру телефона (86 уникальных телефонов).
    - Разделение статусов CRM: спам переведен в `status='archived'` с тегом `спам`, целевые заявки получили тег `таргет`.
    - Сохранение связок с Яндекс.Метрикой (`metrika_client_id` в `LeadUtm`).
    - Генерация токенов авторизации `BotLinkToken` для последующей склейки с ботами Telegram.
  - На боевом сервере Simplecloud (`85.143.175.148`) в PostgreSQL добавлено 87 новых лидов (всего в базе 504 лида), 86 проверенных номеров телефонов, 85 записей атрибуции UTM и 90 токенов бота.
  - **Доказательство (Evidence):**
    - `psql -c 'SELECT count(*) FROM leads; SELECT status, count(*) FROM leads GROUP BY status; SELECT contact_type, count(*) FROM lead_contacts GROUP BY contact_type;'`:
      - `total_leads`: 504 (417 VK + 87 CRM)
      - `status`: active = 469, archived = 35
      - `lead_contacts`: phone = 86
      - `bot_link_tokens`: 90
    - `scripts/verify.ps1 -Subproject funnel-hub` — 18 passed, ruff clean, mypy clean (код 0).

- [x] **Запуск воркеров, ботов и переключение DNS bot.aisukam.ru (2026-11-06, MIG-005)**:
  - На Simplecloud VPS (`85.143.175.148`) запущен полный боевой стек сервисов через `docker compose up -d`:
    - `funnelhub-app-1` (Up)
    - `funnelhub-postgres-1` (Up)
    - `funnelhub-redis-1` (Up)
    - `funnelhub-telegram-bot-1` (Up, polling активен)
    - `funnelhub-funnel-worker-1` (Up, рассылка ВК и обогащение Метрики активны)
    - `funnelhub-most-telegram-bot-1` (Up, polling активен)
    - `funnelhub-most-funnel-worker-1` (Up)
    - `funnelhub-most-vk-funnel-worker-1` (Up)
  - Caddy автоматически выпустил боевой SSL-сертификат Let's Encrypt для домена `bot.aisukam.ru`.
  - Эндпоинты `https://bot.aisukam.ru/inbox/` и `https://bot.aisukam.ru/health` возвращают HTTP 200 OK.
  - В логах `telegram-bot` зафиксирован запуск polling (`aiogram.dispatcher: Start polling`).
  - В логах `funnel-worker` зафиксирована штатная отправка сообщений воронки ВКонтакте (`POST https://api.vk.com/method/messages.send HTTP/1.1 200 OK`).
  - **Доказательство (Evidence):**
    - `docker compose ps` — все 8 контейнеров со статусом `Up`.
    - `curl -s -o /dev/null -w "%{http_code}\n" https://bot.aisukam.ru/inbox/` — **200 OK**.
    - `scripts/verify.ps1 -Subproject funnel-hub` — 18 passed, ruff clean, mypy clean (код 0).

- [x] **Настройка автоматических внешних бэкапов БД (2026-11-06, MIG-006)**:
  - Доработан скрипт `scripts/backup-db.sh` и `scripts/restore-db.sh` для надежной работы с шифрованием GPG AES256 в headless/cron окружении (`--pinentry-mode loopback`, `--passphrase-fd 0`).
  - Реализован контур непрерывной внешней репликации бэкапов (Defense-in-depth): каждый зашифрованный дамп автоматически выгружается по FTP на независимый сервер Reg.ru (`31.31.197.49`) в защищенный каталог `backups/`.
  - На сервере Simplecloud (`85.143.175.148`) настроен ежедневный cron-джоба `/etc/cron.d/funnelhub-backup` на 03:00 МСК с ротацией локальных архивов старше 14 дней.
  - **Доказательство (Evidence):**
    - Тестовый запуск `backup-db.sh` завершился успешно (код 0).
    - Создан локальный зашифрованный дамп: `/opt/funnelhub/backups/funnelhub_backup_20261106_020859.sql.gz.gpg` (136 515 байт).
    - Дамп успешно отправлен и верифицирован на Reg.ru FTP (`ftp://31.31.197.49/backups/funnelhub_backup_20261106_020859.sql.gz.gpg`, 136 515 байт).
    - `tests/test_backup_scripts.py` пройден (4/4 passed).
    - `scripts/verify.ps1 -Subproject funnel-hub` — 18 passed, ruff clean, mypy clean (код 0).

- **2026-10-27 14:36** | fix(funnel-hub): polish lead detail card layout, remove default avatar and align action buttons

- **2026-11-05 23:05** | recovery(MIG-003): recover 417 VK funnel states from VK API into PostgreSQL

- **2026-11-06 00:35** | recovery(MIG-004): import 87 CRM leads from Google Sheets into PostgreSQL

- **2026-11-06 01:15** | ops(MIG-005): launch all 8 services, verify bots polling, worker dispatch and SSL

- **2026-11-06 02:10** | ops(MIG-006): configure daily encrypted backups with off-site Reg.ru FTP replication

- **2026-11-06 19:22** | feat(funnel-hub): email test suppression and crm vk reconciliation

- **2026-11-06 20:53** | ops(SEC-005): manual post-import encrypted backup funnelhub_backup_20261106_205338.sql.gz.gpg (321 KB, состояние 624 лидов после GC-импорта) + верифицирован на Reg.ru FTP; удалены 2 legacy незашифрованных tmp-дампа
- **2026-11-06 21:00** | ops(SEC-005): restore test GREEN — ежедневный дамп 03:00 расшифрован и развёрнут во временную БД funnelhub_verify (psql exit 0, все 24 таблицы), временная БД и файлы удалены, боевые данные не затронуты
- **2026-11-06 21:40** | ops(STD-022/STD-SEC-004): secrets dual-storage — сервер 81 ключ vs локальный .env 31 → append-синк +50; сейф .env.recovery.template 76/81 → +5 → 81/81 (missing=0); урок зарегистрирован в .harness/lessons.md

- **2026-11-06 19:46** | fix(funnel-hub): UX-VK-001 инструкция Разрешить сообщения на join-странице + диагностика автостарта VK (STD-FUNNEL-003)

- **2026-11-06 20:17** | feat(funnel-hub): TG-PROXY-001 Cloudflare Worker Telegram proxy, VK-CONFIRM-001 and STD-FUNNEL-004

- **2026-11-06 20:22** | feat(funnel-hub): import 1188 GetCourse users via API (823 new leads, contacts/UTM/tags/external-ids), GC badge in inbox channel column, webhook-race guards, STD-DATA-004/005 lessons

- **2026-11-06 20:42** | fix(funnel-hub): scope GC import to FunnelHub launch period — delete 698 pre-2026-05-27 imported leads, final 624; STD-DATA-004 scope rule

- **2026-11-06 20:53** | feat(funnel-hub): deploy GC badge to prod (verified in served bundle) + SOP-BACKUP-001 Beget backup merge plan

- **2026-11-06 21:04** | feat(funnel-hub): chronological lead database ordering — newest first by coalesced GC registration date, old leads on last pages

- **2026-11-06 21:21** | ops(funnel-hub): backup restore-test GREEN, manual post-import backup 20261106_205338, STD-SEC-004 secrets dual-storage + local vault sync

- **2026-11-06 21:21** | fix(funnel-hub): compact GC badge + channel priority in lead database (has_telegram/has_vk/has_max flags, MAX channel, is_subscribed decoupled from display); deployed

- **2026-11-06 21:51** | fix(funnel-hub): remove non-existent MAX channel and GC badge from lead database channel column, honest 'no subscriptions' fallback; STD-UI-001; legacy empty max-conversations flagged

- **2026-11-06 21:55** | ops(STD-022): секреты выровнены с продом — 6 устаревших ключей в .env + VK_CONFIRMATION_CODE в сейфе перезаписаны серверными значениями; vault и .env = 81/81 (0 mismatches / 0 missing), значения не печатались
- **2026-11-06 22:10** | ops(SEC-005): добавлен третий ярус бэкапов — scripts/backup-pull.ps1 (FTP primary + SSH fallback, локальная ротация 7д), Windows Task 'FunnelHub Backup Pull' ежедневно 17:00 МСК (StartWhenAvailable), RETENTION_DAYS сервера 14→7; SOP-BACKUP-002 в AGENTS.md

- **2026-11-06 22:01** | docs(funnel-hub): STD-UI-001 attribution — max-conversation shells created by MIG-004 recover_crm_leads.py placeholder, not experiments

- **2026-11-06 22:01** | ops(funnel-hub): secrets aligned to prod 81/81, 3-tier backup chain (backup-pull.ps1 + Task 17:00 MSK), server RETENTION_DAYS 14->7 (SOP-BACKUP-002)

- **2026-11-06 22:33** | chore(funnel-hub): purge 79 empty max-conversation shells (guarded delete, dump+rollback); STD-UI-001 attribution fixed to MIG-004 recover_crm_leads.py

- **2026-11-06 22:35** | docs(funnel-hub): user confirmed 4-lead delta was manual admin deletions; final base 620 leads
