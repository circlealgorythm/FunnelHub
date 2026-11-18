# База локальных уроков, SOP и инцидентов: FunnelHub

> **Назначение:** Детальный справочник инцидентов, операционных регламентов (`SOP-*`) и локальных стандартов (`STD-*`) бэкенда, ботов, БД PostgreSQL и админки `inbox-app`.  
> **Как использовать:** На старте читать весь файл **не нужно** — ищите кейсы точечно через `pwsh -ExecutionPolicy Bypass -File scripts/query-harness.ps1 -Query "<ключевые_слова>" -Subproject funnel-hub`.  
> **Краткий операционный роутер:** [`AGENTS.md`](file:///./projects/funnel-hub/AGENTS.md)

---

## Оглавление и быстрые маркеры
- **Эксплуатация, деплой, мониторинг и бэкапы:** `STD-OPS-010` (verify exit codes / UTF-8 BOM), `STD-OPS-011` (Telegram proxy & external monitoring), `SOP-OPS-002` (реактивация Моста), `SOP-OPS-003` (чистка docker build cache), `SOP-BACKUP-001` (слияние дампа Beget), `SOP-BACKUP-002` (3-ярусный конвейер бэкапов), `SOP-EMAIL-001` (ручная отписка лида), `STD-SEC-004` (зеркалирование секретов в сейф).
- **Боты, воронки и GetCourse:** `STD-FUNNEL-001..002` (сегменты Моста и Блога), `STD-FUNNEL-003` (автостарт VK / `message_allow`), `STD-FUNNEL-004` (Cloudflare Worker proxy & тайминги aiogram), `STD-FUNNEL-005` (`/join/getcourse` & 403-луп), `STD-FUNNEL-006` (`create_telegram_bot` & skip без identity), `STD-FUNNEL-007` (VK-колбэк Моста), `STD-FUNNEL-008` (отсутствие access-логов uvicorn), `STD-FUNNEL-009` (маркерный дрейф email & `verify-deep.ps1`), `STD-FUNNEL-010` (диплинк `/join/{token}/tg` & fallback по телефону).
- **Безопасность, данные и CRM Inbox:** `STD-SEC-001..003` (IP spoofing, Formula Injection + `jti`, CSP Caddyfile), `STD-EMAIL-002` (супрессия тестовых email), `STD-DATA-003..007` (`Phone-First`, импорт GC, VK `is_subscribed=false`, восстановление/слияние дампов и 10-цифровых телефонов), `STD-UI-001..002` (отображение каналов, мульти-identity и уведомления `@leadsaisubot`).

---

## 🛠️ Операционные регламенты (SOP) и стандарты эксплуатации

### STD-OPS-010 | Проверка кодов этапов FunnelHub и UTF-8 бэкапа на Windows
* **Сигнал/Маркер (Cue):** `verifyCmd`, `$LASTEXITCODE`, `ruff` failed, verify OK; `backup-pull.ps1`, Windows PowerShell 5, кириллица в пути, устаревшая локальная копия.
* **Проблема & Причина:** PowerShell возвращает код последней команды в цепочке, скрывая предыдущую ошибку. Windows PowerShell 5 иначе читает UTF-8 без BOM, из-за чего путь резервной копии с кириллицей искажается; асинхронный VBS не передаёт итоговый код дочерней задачи.
* **Стандарт и контрмера:** В `verifyCmd` после каждого внешнего этапа проверять `$LASTEXITCODE` и немедленно возвращать ненулевой код. Для `backup-pull.ps1` сохранять UTF-8 BOM; планировщик должен запускать PowerShell непосредственно и ожидать завершения, а наличие копии проверять по пути и хешу.
* **Доказательство (Evidence):** `verify.ps1 -Subproject funnel-hub` при ошибках Ruff до исправления вернул 0 (RED); после исправления — 1, имитация ошибки каждого из четырёх этапов вернула 17, полный прогон — 0. Копия от 08.11 после исправления совпала по SHA-256 на VPS/FTP/ПК; запуск задачи 08.11 23:34 записал `source=ftp ... failed=0`, код 0.

### STD-OPS-011 | Telegram-прокси и независимость мониторинга VPS
* **Сигнал/Маркер (Cue):** `health-monitor.py`, Cloudflare Worker, Python urllib, HTTP 403 / error code 1010, внешний мониторинг VPS.
* **Проблема & Причина:** Cloudflare отклонял стандартный User-Agent urllib; внутренний монитор не работает при полном отключении самого VPS.
* **Стандарт и контрмера:** Для уведомлений через текущий Worker задавать проверенный User-Agent клиента; при отказе доставки не сохранять состояние оповещения как отправленное. Мониторинг полного отказа VPS размещать вне него; существующий внутренний cron этого не заменяет.
* **Доказательство (Evidence):** Тест `notify()` со стандартным urllib → HTTP 403 / 1010; проверка `getMe` с User-Agent aiohttp → HTTP 200; после исправления тест `notify()` → `NOTIFICATION_ACCEPTED`, cron 09.11 00:30:01 → `Проблем: 0`.

### SOP-EMAIL-001 | Ручная отписка лида от email-рассылок (Unisender Go & FunnelHub)
* **Сигнал/Маркер (Cue):** отписка, удалить из рассылки, unsubscribe-lead.py, Unisender Go, suppression, EmailSubscription, FunnelState paused.
При обращении лида с просьбой отписать его от рассылки («удалить из Unisender / почтовой рассылки»):
1. **Единая точка входа:** запускать стандартный CLI-скрипт:
   ```bash
   python scripts/unsubscribe-lead.py --email <EMAIL>
   # или по UUID лида:
   python scripts/unsubscribe-lead.py --lead-id <UUID>
   ```
2. **Атомарные инварианты отписки:**
   - **Провайдер (Unisender Go):** отправка в `https://goapi.unisender.ru/ru/transactional/api/v1/suppression/set.json` параметров `{"email": email, "cause": "unsubscribed"}` с проверкой через `suppression/get.json`.
   - **Подписка (PostgreSQL):** перевод `EmailSubscription.status` в `"unsubscribed"` и установка `unsubscribed_at = UTC now`.
   - **Воронки (PostgreSQL):** перевод всех активных `FunnelState` (`channel="email"`) в `status="paused"`, сброс `next_run_at = None`, фиксация `paused_reason="user_requested_unsubscribe"`.
   - **Аудит (PostgreSQL):** запись события `Event(event_type="email.unsubscribed", source="manual_admin")`.

### SOP-OPS-002 | Реактивация сервисов проекта «Мост ценностей» (2026-10-21)
* **Сигнал/Маркер (Cue):** Мост ценностей, `@most_cannostei_bot`, `most-telegram-bot`, `most-funnel-worker`, `most-vk-funnel-worker`, сегменты Inbox.
Проект «Мост ценностей» реактивирован по запросу пользователя.
1. Сервисы в `docker-compose.prod.yml`:
   - `most-telegram-bot` (актуальный бот: `@most_cannostei_bot`, ID: `8705381132`)
   - `most-funnel-worker`
   - `most-vk-funnel-worker`
2. **Инвариант эксплуатации:** Сервисы запущены в штатном режиме. Токен `MOST_TELEGRAM_BOT_TOKEN` обновлен в боевом `.env`, бот успешно опрашивает Telegram API. В админке FunnelHub возвращены раздельные вкладки сегментов для Inbox и Базы, а лиды «Моста ценностей» изолированы в соответствующем сегменте.
3. **Доказательство (Evidence):**
   - Успешный деплой через `deploy_files.py` (exit 0).
   - Логи контейнеров: `funnelhub-most-telegram-bot-1` (Start polling for `@most_cannostei_bot`, обработка updates `839195251`, `839195252`), `funnelhub-most-funnel-worker-1` (`Most funnel runner pass completed`), `funnelhub-most-vk-funnel-worker-1` (`Most VK funnel runner pass completed`).
   - Админка `https://bot.aisukam.ru/inbox/` — HTTP 200 OK.

### SOP-BACKUP-001 | Слияние при возврате бэкапа Beget VPS (план восстановления, 2026-11-06 / частично исполнен 2026-11-18)
* **Сигнал/Маркер (Cue):** `SOP-BACKUP-001`, возврат дампа Beget, `beget_restore`, слияние бэкапа, `ON CONFLICT DO NOTHING`, `lead_tags`, `vk_recovery`, переписка.
* **Контекст:** Бывший Beget VPS `31.129.110.56` уничтожен инфраструктурным инцидентом 2026-11; FunnelHub работает на Simplecloud (`85.143.175.148`) на БД, собранной через GC-импорт (`DATA-002`, граница 2026-05-27) + живые вебхуки. При возврате архива Beget: **история переписки (`conversations`/`messages`), `funnel_states`, `events` и исходные лиды восстановимы из него**.
* **Инварианты слияния:**
  1. Дамп Beget загружать в ОТДЕЛЬНУЮ схему/БД на Simplecloud (например `beget_restore`); боевые таблицы не трогать до сухого прогона.
  2. Слияние лидов по ключам в порядке приоритета: `getcourse_user_id` → VK-identity (`messenger_identities.channel='vk'`) → нормализованный телефон → email (lower). Только подтверждённые совпадения (Phone-First, `STD-DATA-003`); однофамильцев не сливать.
  3. Переписку (`conversations`/`messages`) переносить из бэкапа целиком, только для лидов, существующих в текущей базе; дедупликация по `external_message_id` либо `(lead_id, channel, sent_at)`; конфликты — в пользу более свежей записи.
  4. Объём-правило (`STD-DATA-004` п.5): лиды GC с регистрацией ранее 2026-05-27 из бэкапа НЕ воскрешать.
  5. UNIQUE-конфликты решать в пользу прод-записи (`ON CONFLICT DO NOTHING`): `lead_contacts(contact_type, normalized_value)`, `leads.getcourse_user_id`, `lead_external_ids(provider, external_id)`, `messenger_identities(channel, external_user_id)`, `lead_tags(lead_id, tag)`, `lead_custom_fields(lead_id, source, field_key)`.
  6. Лиды из бэкапа без аналога в проде вставлять только из FunnelHub-каналов (`vk_recovery`, `landing_consultation`); `lead_tags.id` задаётся явно (`gen_random_uuid()`, у таблицы нет server_default).
  7. Чужие VK-идентичности из бэкапа — только `is_subscribed=false` (`STD-DATA-005`).
* **Процедура:** дамп текущего прода (`pg_dump -Fc`) + копия локально → загрузка бэкапа в отдельную схему → dry-run слияния (`BEGIN…ROLLBACK`: счётчики мёржа/вставок, список конфликтов, выборка карточек) → ревью пользователем → `COMMIT` → `POST-MERGE VERIFY` (счётчики до/после, выборочные диалоги, `verify.ps1 -Subproject funnel-hub`, HTTP 200 `/inbox/`, чистые логи вебхуков).
* **Статус и Evidence:** план согласован `2026-11-06`; **частично исполнен `2026-11-18`** по фактическому возврату архива Beget (`backup.tar` на `2026-10-19 11:55 МСК`, дамп `funnelhub_backup_20261019_030002.sql.gz`). По решению пользователя восстановлены только недостающие лиды (`+131`), их профили/контакты/UTM/согласия и `56` Telegram-идентичностей (`38` subscribed / `18` unsubscribed); `funnel_states`, `email_subscriptions`, `conversations` и `messages` не переносились. Затем выполнена пост-проверка и склейка `8` пар дублей (10-значные телефоны `9xxxxxxxxx` без `7`, опечатки email-домена, `vk_recovery + away.vk.ru`). Evidence: `dry-run` `ROLLBACK` (`skipped_collision_leads=0`) → pre-restore дамп `pre_beget1019_restore_20261118.dump` (`sha256=1d5be317...`) → `COMMIT` (`leads 670→801→793`, `tg_idents 10→66`, `contacts 727→1127→1120`, `utm 406→937`, `funnel_states 499` без изменений, `0` дублей email/реальных телефонов); `/health` и `/inbox/` HTTP 200, 8 контейнеров Up.

### SOP-BACKUP-002 | Трёхъярусная цепочка бэкапов БД: сервер → FTP → ПК (конвейер pull, 2026-11-06)
* **Сигнал/Маркер (Cue):** `backup-pull.ps1`, `backup-db.sh`, `restore-db.sh`, `RETENTION_DAYS`, FTP Reg.ru `/backups/`, Windows Task `FunnelHub Backup Pull`, 03:00, 17:00, GPG AES256.
* **Контекст:** `SEC-005`/`MIG-006` даёт серверный дамп и оффсайт-FTP, `STD-022` — локальное хранение секретов. Третий ярус достраивает цепочку: ежедневный pull зашифрованных дампов на ПК пользователя (DR-логика: тянуть надо с независимого хранилища, при смерти сервера забирать с него нечего).
* **Архитектура цепочки:**
  1. **Сервер Simplecloud (85.143.175.148):** cron `/etc/cron.d/funnelhub-backup` 03:00 МСК → `backup-db.sh` (`pg_dump` → `gzip -9` → GPG AES256) → `/opt/funnelhub/backups/`; ротация `RETENTION_DAYS=7` в `/opt/funnelhub/.env`.
  2. **FTP Reg.ru (31.31.197.49:/backups/):** дамп выгружается сразу после создания; ротации НЕТ — полная история (~320 КБ/день) — «архивный ярус» на случай, если проблема обнаружится позже 7 дней.
  3. **ПК:** `scripts/backup-pull.ps1` (хаб-репо) — Windows Task `FunnelHub Backup Pull`, ежедневно **17:00 МСК** (ПК обычно включён), `StartWhenAvailable` (догоняет пропуск после включения ПК). Источник: FTP primary → SSH fallback (`root@85.143.175.148:/opt/funnelhub/backups/`). Локальная ротация 7 дней по дате из имени дампа. Креды — из канонических локальных `.env` (`BACKUP_FTP_*` / `FTP_MAIN_SITE_*` / `SSH_*`), без хардкода; `backups/` в `.gitignore` репо FunnelHub — в git не попадает.
* **Процедуры:**
  - Регистрация задачи: `pwsh -ExecutionPolicy Bypass -File scripts/backup-pull.ps1 -RegisterTask [-TaskTime "17:00"]`
  - Ручной прогон: `pwsh -ExecutionPolicy Bypass -File scripts/backup-pull.ps1` (exit 0 — ок; 1 — оба источника недоступны; 2 — часть скачиваний упала)
  - Восстановление: дамп `.gpg` (с ПК или FTP) + passphrase из сейфа `Бот воронка\.env.recovery.template` → `restore-db.sh` на сервере.
* **Доказательство (Evidence):**
  - Тестовый прогон: FTP listing OK → 4 дампа скачаны, `Done: source=ftp downloaded=4 failed=0 rotated=0`, exit 0.
  - Идемпотентность: второй прогон `missing=0, downloaded=0`, exit 0.
  - SSH-фолбэк: scp-скачанный дамп байт-в-байт идентичен FTP-копии (md5 `e2972b3378b304f7a8d8b6dd444f36c5` совпал).
  - Задача: `State=Ready`, Trigger `2026-11-06T17:00:00+03:00`, NextRun `2026-11-07 17:00:00`.
  - Ротация сервера: `grep RETENTION_DAYS /opt/funnelhub/.env` → `RETENTION_DAYS=7` (было 14).

### SOP-OPS-003 | Профилактика раздувания docker build cache на Simplecloud (2026-11-07)
* **Сигнал/Маркер (Cue):** `docker builder prune`, `docker system df`, Build Cache, место на диске VPS, `--volumes` запрещён, Simplecloud диск.
* **Контекст:** Каждый прогон `deploy_files.py` выполняет `docker compose build` всех app-сервисов; старые слои остаются в build cache. За ~2 недели деплоев cache вырос до 2.7 ГБ (66 записей, 0 активных) на диске VPS.
* **Процедура:** Раз в 1–2 месяца (или после серии деплоев) на сервере:
  1. Диагностика: `docker system df` (строка Build Cache = объём + Reclaimable) и `df -h /`.
  2. Чистка: `docker builder prune -af` — удаляет ТОЛЬКО кэш сборки.
  3. ЗАПРЕЩЕНО: `docker system prune --volumes` (сносит том с боевой БД `postgres_data`); любая чистка томов (`Local Volumes` в `docker system df`).
* **Доказательство (Evidence):**
  - ДО: `df -h /` → `9.3G used / 40G (25%)`; `docker system df` → `Build Cache 66 entries, 2.709GB, reclaimable 2.215GB`.
  - ПОСЛЕ `docker builder prune -af`: Build Cache `0 entries, 0B`; `df -h /` → `6.9G used (19%)`, освобождено ~2.4 ГБ.
  - Инварианты подтверждены: `Local Volumes 3 / 71.29MB / 0B (0%)` — не изменились; 7 контейнеров продолжают работать (`docker ps`).

---

## 🔍 Детальные локальные стандарты (FunnelHub & Inbox App)

### STD-FUNNEL-001 | Мультипроектная изоляция сегментов базы и дедупликация GetCourse
* **Сигнал/Маркер (Cue):** `exclude_source`, `lead_exclude_source_filter`, `inbox_database.py`, `most-tsennostey`, сегменты базы, склейка лида, дублирование в Общей базе.
* **Проблема:** При склейке существующего контакта школы (GetCourse ID, email, телефон) с заявкой из дочернего лендинга («Мост ценностей») базовое поле `Lead.source` сохраняет исходный источник контакта. Простой фильтр `Lead.source != exclude_source` не исключал такой склеенный лид из «Общей базы», что приводило к дублированию лида в обоих разделах админки.
* **Стандарт и контрмера:** Фильтрация по исключению источника (`exclude_source`) в `inbox_database.py` и `inbox.py` обязана строиться через `lead_exclude_source_filter`, проверяющий как отсутствие прямого `Lead.source == exclude_source`, так и отсутствие связанных событий `Event.source == exclude_source`.
* **Доказательство (Evidence):**
  - Тест `test_existing_lead_submitting_most_is_isolated_to_most_segment` в `tests/test_most_tsennostey_applications.py` подтверждает изоляцию (`assert existing_lead_id not in [item.id for item in main_leads.items]`).
  - Прогон `scripts/verify.ps1 -Subproject funnel-hub` завершен с кодом 0 (8 passed, ruff passed, mypy passed).

### STD-FUNNEL-002 | Мультипроектная сегментация лидов: Контентный блог и статьи обращения
* **Сигнал/Маркер (Cue):** `source='blog'`, `article_title`, `article_url`, вкладка «Блог» в `inbox-app`, `exclude_source='most-tsennostey,blog'`, `LeadCustomField`.
* **Проблема:** Лиды с контентного блога (`aisukam.ru/blog/*`) и основного сайта (`aisukam.ru`) отправляли заявки через единый бэкенд `submit-lead.php`. Заявки смешивались в сегменте «Общая база», а оператор и маркетолог не видели, с какой конкретно статьи блога пришел пользователь.
* **Стандарт и контрмера:**
  1. Формы блога обязаны принудительно задавать `source = 'blog'` и передавать метаданные `article_title` и `article_url`. На сервере `submit-lead.php` действует резервный fallback по `HTTP_REFERER`.
  2. Вебхук FunnelHub сохраняет поля статьи в `LeadCustomField` («Статья блога», «Ссылка на статью»).
  3. `inbox_database.py` и `inbox.py` обязаны поддерживать множественное исключение `exclude_source` через запятую (например, `exclude_source='most-tsennostey,blog'` для вкладки «Общая база»).
  4. Вкладка «Блог» в `inbox-app` изолированно запрашивает `source=blog`, выводит бейдж `📄 <Название статьи>` в таблице лидов и интерактивную карточку со ссылкой в карточке лида, а поля `article_title` и `article_url` включаются в экспорт CSV/XLSX.
* **Доказательство (Evidence):**
  - Unit-тесты `tests/test_blog_segmentation.py` (6 тестов: Pydantic-схема, мульти-фильтрация SQL, экспортные колонки) — `14 passed in 5.74s`.
  - Успешный боевой деплой на сервер, HTTP 200 на `https://bot.aisukam.ru/inbox/`.

### STD-SEC-001 | Защита от спуфинга IP в Rate Limiter и харденинг VK вебхуков (HARNESS-002)
* **Сигнал/Маркер (Cue):** `get_request_ip`, `X-Forwarded-For`, `InMemoryRateLimiter`, `/api/auth/login`, `validate_vk_secret`, `secrets.compare_digest`, `group_id`.
* **Проблема:**
  1. `get_request_ip` брал первый IP из `X-Forwarded-For`. Злоумышленник мог передавать поддельные IP в заголовке (`X-Forwarded-For: <fake_ip>, <real_ip>`), обходя лимит попыток входа в админку `/api/auth/login`.
  2. `InMemoryRateLimiter` накапливал корзины IP в памяти без очистки устаревших ключей (риск разрастания памяти).
  3. Проверка секрета VK использовала оператор `!=` (теоретический риск timing-атак).
* **Стандарт и контрмера:**
  1. В `get_request_ip` доверять строго последнему IP в списке `X-Forwarded-For` (`ips[-1]`), который гарантированно дописывается доверенным реверс-прокси Caddy на сервере.
  2. В `InMemoryRateLimiter` при превышении порога в 500 ключей автоматически удалять устаревшие и пустые корзины.
  3. В `validate_vk_secret` использовать `secrets.compare_digest` и валидировать `group_id` по доверенным группам (`vk_group_id`, `most_vk_group_id`).
* **Доказательство (Evidence):**
  - Unit-тест `test_login_rate_limiting_ip_spoofing_prevention` в `tests/test_auth.py`: запросы с поддельными клиентскими IP при одинаковом прокси-IP блокируются с кодом 429 (GREEN).
  - Unit-тест `test_rate_limiter_memory_pruning`: 550 устаревших корзин очищаются до 1 свежей при добавлении нового ключа (GREEN).
  - Unit-тест `test_validate_vk_secret_constant_time` в `tests/test_cors_and_vk_failclosed.py` (GREEN).
  - `pwsh -ExecutionPolicy Bypass -File scripts/verify.ps1 -Subproject funnel-hub` успешно пройден (код 0 за 10.3s).

### STD-SEC-002 | Защита от Formula Injection в экспорте таблиц и отзыв сессий (HARNESS-002)
* **Сигнал/Маркер (Cue):** `sanitize_spreadsheet_cell`, Formula Injection, CSV, XLSX, экспорт базы, `REVOKED_SESSIONS`, `jti`, logout.
* **Проблема:**
  1. Пользовательский ввод в формах (имя, город, комментарии, UTM-метки) при экспорте в CSV или Excel (`inbox_database.py`) мог содержать формульные префиксы (`=cmd|...`, `@SUM(...)`), вызывая Formula Injection при открытии файла в Microsoft Excel.
  2. Сессионные куки JWT после нажатия кнопки «Выход» в админке оставались валидными по криптоподписи до истечения TTL (Hardening 3.1).
* **Стандарт и контрмера:**
  1. В `inbox_database.py` функция `sanitize_spreadsheet_cell` обязана экранировать префиксы `=`, `@`, `\t`, `\r`, а также `+` и `-` (если за ними не следует валидный числовой телефон/число) одинарной кавычкой `'`. Экранирование применяется ко всем ячейкам при экспорте CSV и XLSX.
  2. В `auth.py` сессионные куки содержат `jti`. При логауте токен регистрируется в хранилище отозванных сессий `REVOKED_SESSIONS` с автоочисткой по истечении TTL.
* **Доказательство (Evidence):**
  - Unit-тест `test_sanitize_spreadsheet_cell_formula_injection`: опасные формулы экранируются, телефоны `+79991234567` и числа `-500` не искажаются (GREEN).
  - Unit-тест `test_logout_revokes_session_cookie`: попытка повторного использования куки после логаута завершается HTTP 401 (GREEN).
  - `pwsh -ExecutionPolicy Bypass -File scripts/verify.ps1 -Subproject funnel-hub` (18 passed, ruff passed, mypy passed).

### STD-FUNNEL-003 | Автостарт VK-воронки: платформенный предел VK и UX-контрмера «Разрешить сообщения» (HARNESS-002)
* **Сигнал/Маркер (Cue):** «VK бот не пишет первым», «воронка не стартует автоматически после заявки», «новый аккаунт VK — тишина в чате», `message_allow`, `vk.me?ref`, переход со страницы спасибо `/join/{token}`.
* **Проблема & Причина:** VK Callback API **не отправляет сообществу никакого события**, когда пользователь просто открывает чат (даже с нового аккаунта и даже при подписанном `message_allow`). Автостарт воронки физически возможен только по событию `message_allow` (тап «Разрешить сообщения») или `message_new` (первое сообщение пользователя) — в обоих VK передает `ref` из ссылки `vk.me/<screen>?ref=<token>`. Прямая отправка без события падает с VK error 901 (классифицируется как permanent → пауза воронки), а узнать VK ID без действия пользователя нельзя (VK OAuth-флоу `vk_oauth.py` реализован, но отклонён пользователем: длинный путь снижает конверсию). После переноса БД на Simplecloud база `messenger_identities` пуста для новых людей — путь `relaunch_vk_for_known_lead` (мгновенная отправка известным VK ID) перестал покрывать новых лидов, и платформенный разрыв стал видимым.
* **Стандарт и контрмера:**
  1. Диагностику автостарта вести по БД, а не по docker-логам (uvicorn не пишет access-логи, INFO логи `funnelhub.*` не проходят root-handler): `funnel_states.metadata->>'restart_reason' = 'bot_start'` + ключ `ref` в `messenger_identities.raw_profile` = событие пришло с токеном и воронка стартовала по нему.
  2. При подозрениях на `message_allow` сверять подписку события в UI настроек Callback API сообщества («Разрешение на получение»); токен группы имеет scope только `messages` — `groups.getCallbackSettings` вернёт error 15/1133. Чекбокс «Исходящее сообщение» (`message_reply`) включать не нужно — это эхо собственных отправок.
  3. UX-стандарт: на join-странице (`render_join_page`) обязана быть инструкция одного касания: «в VK нажмите "Разрешить сообщения", в Telegram — "Запустить"». Набор текста пользователем не требуется, конверсия не страдает.
* **Доказательство (Evidence):**
  - Ксения (VK ID 258149228, заявка 2026-11-06 15:55 UTC): SQL `funnel_states` → `restart_reason='bot_start'`, 15:56:37 — первое сообщение ушло автоматически по событию с ref (`raw_profile` содержит ключ `ref`).
  - Светлана/«Екатерина Пушкина» (заявка 15:59 UTC, заведомо новый VK-аккаунт): ноль строк в `messenger_identities`/`messages`/`events` по VK — открытие чата без тапа «Разрешить» не генерирует событий.
  - Скриншот настроек Callback API сообщества: «Разрешение на получение» включён; `groups.getCallbackSettings` под токеном группы → `error_code 15 (no scopes)`.
  - Верификация правки: `verify.ps1 -Subproject funnel-hub` код 0 (ruff, mypy 54 файлов, 18 тестов); `tests/test_join_page.py` 2 passed; визуальный контроль `render_join_page` (десктоп 1280px + мобайл 390px).

### STD-SEC-003 | Защита периметра через Content-Security-Policy в Caddyfile (HARNESS-002)
* **Сигнал/Маркер (Cue):** `Caddyfile`, `Content-Security-Policy`, XSS, кликджекинг, `tests/test_caddyfile.py`, `bot.aisukam.ru`.
* **Проблема:** В заголовках безопасности реверс-прокси Caddy отсутствовала директива `Content-Security-Policy`, что снижало защиту от атак XSS и кликджекинга при работе с веб-интерфейсом FunnelHub (`bot.aisukam.ru`).
* **Стандарт и контрмера:**
  В блоке `header` конфигурации `Caddyfile` задавать строгую политику CSP:
  `Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self' https://bot.aisukam.ru; frame-ancestors 'self';"`
  Обязательно покрывать наличие CSP и балансировку скобок тестом в `tests/test_caddyfile.py`.
* **Доказательство (Evidence):**
  - Unit-тест `tests/test_caddyfile.py` проверяет директиву `Content-Security-Policy` и сбалансированность фигурных скобок (PASS).
  - Прогон `scripts/verify.ps1 -Subproject funnel-hub` (ruff, mypy, 18 unit-тестов) успешно завершен с кодом 0.

### STD-EMAIL-002 | Защита квоты Unisender Go: супрессия тестовых адресов и фильтрация по Gmail (HARNESS-002)
* **Сигнал/Маркер (Cue):** `is_test_email`, Unisender Go, супрессия, suppression list, `circlealgorythm@gmail.com`, `jogspokoen`, `ADMIN_EMAILS`, тестовые заявки.
* **Проблема:** Тестовые заявки администратора с ключевыми словами алгоритма (`circlealgorythm@gmail.com`, `test-webhook@aisukam.ru`, `jogspokoen@*`) приводили к холостому расходу лимита Unisender Go (6,000 писем/мес). При этом требовалось не отсекать реальных лидов с корпоративными или сторонними доменами, содержащими корень "алгоритм".
* **Стандарт и контрмера:**
  1. В `email_messaging.py` внедрена функция `is_test_email(email)`.
  2. Для корней `algor...` / `alory...` отсечение выполняется СТРОГО на домене `@gmail.com` (`.*al[go]r[yi]thm.*@gmail\.com`). Все остальные почтовые провайдеры разрешены для клиентов.
  3. Для паттернов `jogspokoen` и административных адресов `ADMIN_EMAILS` отсечение действует безусловно.
  4. На уровне `funnel_autostart.py` и `getcourse_webhook.py` тестовые адреса автоматически маркируются как `unsubscribed`, исключаются из запуска рассылок и заносятся в Unisender Suppression List (`cause="unsubscribed"`).
* **Доказательство (Evidence):**
  - Unit-тест `test_is_test_email_detection` в `tests/test_email_messaging.py`: покрывает тестовые ящики на gmail (`circlealgorythm@gmail.com`), легитимные ящики на других доменах (`algorithm.lead@mail.ru`, `client.algorithm@yandex.ru` -> False), `jogspokoen@*`, `aisukam-info@yandex.ru` (GREEN).
  - Запрос `suppression/get.json` к API Unisender Go подтвердил наличие 8 тестовых адресов в статусе `unsubscribed`.
  - `pwsh -ExecutionPolicy Bypass -File scripts/verify.ps1 -Subproject funnel-hub` успешно пройден (18 unit-тестов, ruff, mypy).

### STD-DATA-003 | Инвариант слияния лидов: Phone-First и сопоставление с VK ID (HARNESS-002)
* **Сигнал/Маркер (Cue):** Phone-First, слияние лидов, `landing_consultation`, `vk_recovery`, однофамильцы, `client_id` Яндекс.Метрики, склейка дублей.
* **Проблема:** При интеграции 87 лидов из Google Sheets CRM и 417 лидов из VK бота требовалось сопоставить профили. Попытка слияния по именам несла высокий риск ложных объединений (однофамильцы, распространенные имена "Ольга", "Елена").
* **Стандарт и контрмера:**
  1. Строгий инвариант: слияние записей (`landing_consultation` + `vk_recovery`) разрешено СТРОГО при совпадении нормализованного номера телефона (`+7...` / 11 цифр) или при 100% подтвержденном совпадении по таймстампу, форме и уникальному ФИО/DEF-коду региона.
  2. Все остальные лиды CRM без подтвержденного телефона или профиля VK сохраняются как независимые сущности с источником `landing_consultation` без риска коллизий.
  3. При объединении профилю присваивается составной источник `landing_consultation + vk`, привязывается `client_id` Яндекс.Метрики и объединяется история контактов.
* **Доказательство (Evidence):**
  - Транзакционный аудит базы данных PostgreSQL на Simplecloud VPS (`85.143.175.148`): успешно объединено ровно 8 подтвержденных пар лидов; оставшиеся 79 лидов CRM изолированы без искажения персональных данных.
  - Запрос `SELECT source, count(*) FROM leads GROUP BY source;` подтвердил: `landing_consultation + vk`: 8, `landing_consultation`: 79, `vk_recovery`: 409.

### STD-FUNNEL-004 | Интеграция Telegram Bot API через Cloudflare Worker Reverse Proxy и калибровка таймаутов aiogram (HARNESS-002)
* **Сигнал/Маркер (Cue):** Telegram Bot API, Simplecloud VPS, aiogram 3, ТСПУ, TCP 443 timeout, Cloudflare Worker, `TelegramAPIServer`, `TELEGRAM_API_BASE_URL`, `create_telegram_bot`, `polling_timeout`, `getUpdates` timeout.
* **Проблема & Причина:** На российских серверах Simplecloud исходящие TCP-соединения к пулам IP Telegram (`149.154.*`, `91.108.*`) на порт 443 блокируются ТСПУ (`Connection timed out`), из-за чего aiogram не может связаться с `api.telegram.org`. Попытка поднять PHP-прокси на Reg.ru натолкнулась на аналогичную фильтрацию ТСПУ. Кроме того, при long-polling опросе `getUpdates` через Cloudflare Worker разрыв соединений по внутренним edge-таймаутам Cloudflare (100–300 с) при дефолтном таймауте aiohttp вызывал периодические ошибки `TelegramNetworkError: Request timeout error`.
* **Стандарт и контрмера:**
  1. Разворачивается бессерверный Cloudflare Worker Reverse Proxy (`export default { async fetch(req) { const u = new URL(req.url); u.hostname = 'api.telegram.org'; return fetch(new Request(u, req)); } }`), трафик к которому из РФ не блокируется и имеет задержку < 40 мс.
  2. В `src/funnelhub/services/telegram_messaging.py` создана централизованная фабрика `create_telegram_bot(token, settings)`. При наличии `settings.telegram_api_base_url` создается `TelegramAPIServer.from_base(base_url)` и передается в `AiohttpSession`.
  3. Все точки создания бота (`funnel_worker.py`, `telegram_bot.py`, `inbox.py`, `inbox_notifications.py`) используют исключительно `create_telegram_bot`, исключая прямой вызов `Bot(token=...)`.
  4. Оба бота задают long polling из настроек: `dispatcher.start_polling(bot, polling_timeout=settings.telegram_polling_timeout)` (`TELEGRAM_POLLING_TIMEOUT`, дефолт 30с). Вариант Б (2026-11-08): 10с → 30с — втрое меньше `getUpdates`-раундтрипов через CF-прокси при неизменной задержке доставки.
  5. Контракт таймаутов: клиентский aiohttp request timeout (`TELEGRAM_REQUEST_TIMEOUT`, дефолт 90с, задается в `create_telegram_bot`) ОБЯЗАН превышать polling timeout с запасом на латентность Cloudflare Worker — иначе периодические `TelegramNetworkError: Request timeout` на edge-задержках CF.
* **Доказательство (Evidence):**
  - RED: Прямой вызов с Simplecloud `curl -m 5 https://api.telegram.org/bot<token>/getMe` ➔ `Connection timed out (exit 28)`.
  - Вариант Б (деплой 2026-11-08, commit `8b5b56e`): `poll=30 / req=90.0` подтверждены `docker exec` в живых контейнерах ОБОИХ ботов; 0 таймаутов за 3 мин после деплоя; `/health` и `/inbox/` 200.
  - GREEN: Вызов через Cloudflare Worker `curl -s https://lingering-forest-a1b9.circlealgorythm.workers.dev/bot<token>/getMe` ➔ `{"ok":true,"result":{"id":8963890043,"is_bot":true,"username":"vedicschool_aisu_bot"}}` (exit 0, ответ 100 мс).
  - Верификатор `verify.ps1 -Subproject funnel-hub` успешно пройден (18 unit-тестов, ruff, mypy без ошибок).
  - Контейнер `funnelhub-telegram-bot-1` на Simplecloud стабильно вычитывает события, `curl .../getWebhookInfo` подтвердил `pending_update_count: 0`.

### STD-DATA-004 | Массовый импорт лидов GetCourse через API: гонка с вебхуками, guard UNIQUE-ссылки и lead_tags.id (HARNESS-002)
* **Сигнал/Маркер (Cue):** GetCourse API, `/pl/api/account/users`, `created_at[from]`, `idgrouplist=id_date`, массовый импорт, `uq_leads_getcourse_user_id`, duplicate key 504948483, вебхук-гонка, `getcourse_webhook`, `lead_tags.id`, `import_gc_users.sql`, `dry-run`, `pg_dump` rollback.
* **Проблема & Причина:** Боевой импорт 1188 пользователей GetCourse (823 новых лидов) дважды падал на проде: (1) `duplicate key value violates unique constraint "uq_leads_getcourse_user_id"` на gc_id 504948483 — живой вебхук GetCourse создал лида между dry-run и коммитом; (2) `null value in column "id" of relation "lead_tags"` — в миграции `20260806_01` у `lead_tags.id` UUID НЕТ `server_default`.
* **Стандарт и контрмера:**
  1. Любой массовый импорт в `leads` обязан содержать guard от гонки с вебхуками: и в UPDATE-линк (`AND NOT EXISTS (SELECT 1 FROM leads l2 WHERE l2.getcourse_user_id = s.gc_id AND l2.id <> l.id)`), и в INSERT новых (`AND NOT EXISTS (SELECT 1 FROM leads l WHERE l.getcourse_user_id = s.gc_id)`). Пропущенных «вебхуковых» лидов обогащать через карту `gc_id→lead_id` (`JOIN leads ON l.getcourse_user_id = s.gc_id`).
  2. В raw-SQL вставках UUID-первичные ключи без `server_default` (`lead_tags`) задавать явно: `SELECT gen_random_uuid(), ...`.
  3. Обязательный пайплайн боевого импорта: `dry-run` (`BEGIN…ROLLBACK`, отчёт на ревью) → `pg_dump` на сервере + копия локально + скрипт отката → commit-прогон → `POST-IMPORT VERIFY`.
  4. GetCourse API: без фильтра `error_code 908` («Должен быть передан хотя бы один фильтр»); полная выгрузка = `created_at[from]=YYYY-MM-DD&created_at[to]=...`; группы = `idgrouplist=id_date` (формат `idgrouplist=id` отдаёт пустую колонку); ключ — `GETCOURSE_API_KEY` из `.env.recovery.template`; технические email `@vktech.gc` отсекать (`is_getcourse_technical_email`), их VK-ID извлекать из префикса `id<N>`.
  5. Объём импорта ограничен датой запуска FunnelHub (создан 2026-05-20): в базу входят только лиды GC, зарегистрированные с 2026-05-27 (согласовано с пользователем). Если импорт выполнен шире границы, чистка = `DELETE FROM leads WHERE raw_getcourse_data->>'origin'=<маркер> AND getcourse_created_at < <граница>`.
* **Доказательство (Evidence):**
  - RED-1: `psql -v commit=1 -f import_gc_users.sql` ➔ `ERROR: duplicate key ... (Key (getcourse_user_id)=(504948483))`, авто-ROLLBACK (`leads 500, gc-linked 1`).
  - RED-2: повтор ➔ `UPDATE 363, INSERT 823 ... ERROR: null value in column "id" of relation "lead_tags"`, авто-ROLLBACK (`leads 500`).
  - GREEN: guard-версия ➔ `UPDATE 363; INSERT 0 823; ... COMMIT`. POST-IMPORT VERIFY: `leads 1323, leads_with_gc_id 1188, emails 1025, phones 913, utm 872, gc_tags 794`.
  - Чистка объёма: `DELETE 698` (регистрации `2024-10-16…2026-05-19`) ➔ `leads 624, gc_linked 490`, `min gc_created = 2026-05-27`. Контейнеры Up, `/inbox/` HTTP 200.

### STD-DATA-005 | Импорт VK-идентичностей из GetCourse: только is_subscribed=false (HARNESS-002)
* **Сигнал/Маркер (Cue):** `messenger_identities`, `is_subscribed`, колонка КАНАЛ, VK-бейдж, inbox lead database, импорт VK-ID, `uq_messenger_identities_channel_external_user_id`.
* **Проблема & Причина:** Колонка КАНАЛ в базе лидов пуста у импортированных из GetCourse лидов: identities создаются только ботами при живом диалоге. `messenger_identities.is_subscribed` по умолчанию true; все механики отправок фильтруют `is_subscribed IS TRUE`, поэтому наивная вставка identity с дефолтом `true` дала бы ботам право слать VK-сообщения неподписанным пользователям (ошибки 901/902).
* **Стандарт и контрмера:**
  1. При импорте VK-ID из внешних источников (GetCourse и др.) identity создавать СТРОГО с `is_subscribed=false` + `raw_profile={"origin": ...}`.
  2. Telegram из GetCourse восстановить нельзя: поле ссылки на бота пусто у всех пользователей; КАНАЛ заполнится сам при первом сообщении лиду боту.
  3. UI-маркер лидов без канала — см. эволюцию в `STD-UI-001` (бейджи `GC`/`MAX` заменены на честный текст «нет подписок»).
* **Доказательство (Evidence):**
  - `INSERT INTO messenger_identities ... is_subscribed=false` ➔ `INSERT 0 15`; итого `vk_total 432` (`414 subscribed / 18 not-subscribed`).
  - Фильтры-разрешения подтверждены кодом: `vk_messaging.py:297`, `funnel_runner.py:260,271,514,536` — `MessengerIdentity.is_subscribed.is_(True)`.
  - `npm run build` (`inbox-app`) 2.50s exit 0; `verify.ps1 -Subproject funnel-hub` — 18 passed.

### STD-SEC-004 | Двойное хранение секретов: каждый ключ дублируется в локальный сейф (инвариант STD-022)
* **Сигнал/Маркер (Cue):** `/opt/funnelhub/.env`, ключи, токены, passphrase, `BACKUP_ENCRYPTION_PASSPHRASE`, VPS down, DR, `.env.recovery.template`, Бот воронка, env drift.
* **Проблема:** Секреты, добавленные прямо на сервере (бэкапы, GC-вебхуки, email-провайдер), существуют только там. При гибели VPS (кейс Beget 2026-11-06) они теряются: GPG-бэкапы не расшифровать, сервисы не восстановить.
* **Стандарт и контрмера:** Канонический локальный сейф FunnelHub — `C:\Users\circlealgorythm\Documents\Бот воронка\.env.recovery.template`. Любой новый/изменённый секрет вносится в него той же сессией, что и на сервер (и в рабочую копию `projects/funnel-hub/.env`, append-only); в git — НИКОГДА. Периодическая проверка дрейфа: имена ключей «сервер vs сейф», цель `0 missing`; значения секретов не печатать в чат.
* **Доказательство (Evidence):**
  - Дрейф 2026-11-06: сервер 81 ключ / локальный `.env` 31 → append-синк +50; сейф 76/81 → +5 → 81/81, `missing=0` (GREEN).
  - `git check-ignore -v .env.recovery.template` → `.gitignore:9:.env.*`; `ls-files --error-unmatch` → not tracked (в git не попадает).

### STD-UI-001 | Отображение каналов: только реально реализованные каналы, честный fallback, флаги присутствия отдельно от права на рассылку (HARNESS-002)
* **Сигнал/Маркер (Cue):** колонка КАНАЛ, lead database, `has_telegram`, `has_vk`, `is_subscribed` фильтр отображения, `channelLabels`, `leadMessengerLabels`, MAX канал, пустые диалоги-оболочки, «нет подписок», mojibake-мусор данных.
* **Проблема & Причина:** Право на рассылку (`is_subscribed`) и факт наличия канала у лида — разные сущности. (1) Колонка КАНАЛ брала канал только из `messenger_identity_subquery` (`is_subscribed IS TRUE`), скрывая 15 импортированных из GetCourse VK-лидов. (2) Попытка показать каналы по таблице `conversations` вытолкнула 79 пустых оболочек `channel='max'` от `recover_crm_leads.py` (канал MAX в системе НЕ реализован).
* **Стандарт и контрмера:**
  1. В `build_lead_summary_query` отображение каналов строится на флагах присутствия `has_telegram`/`has_vk` (`channel_presence_subquery`: идентичность ИЛИ диалог, БЕЗ фильтра `is_subscribed`); `telegram`/`vk` остаются хендлами подписанных идентичностей для карточки/экспорта.
  2. В UI отображаются ТОЛЬКО реально реализованные каналы (`telegram`, `telegram_most`, `vk`, `vk_most`, `email`); список каналов расширяется строго вместе с внедрением канала в бэкенде, не раньше.
  3. Если у лида нет ни одного канала — честный текст «нет подписок»; никаких подстановочных бейджей/значений в колонке КАНАЛ.
  4. Новые пустые сущности (диалоги без сообщений) не должны создаваться для нереализованных каналов.
* **Доказательство (Evidence):**
  - RED-1: 15 GC VK-лидов с identity `is_subscribed=false` показывали «мессенджер нет».
  - RED-2: 65 лидов показали бейдж «MAX» из-за 79 пустых строк `conversations WHERE channel='max'` (`messages = 0`).
  - GREEN: MAX/бейдж удалены, fallback «нет подписок»; деплой подтверждён в бандле `index-CrxPuY1n.js`: `has_max = 0`, `lead-channel-gc-badge = 0`, «нет подписок» = 1; `verify.ps1 -Subproject funnel-hub` — 18 passed; HTTP 200.

### STD-FUNNEL-005 | GetCourse redirect join-страница и воркер-сабмит: guard без секрета для браузера, воркер не открывает финальный редирект (HARNESS-002)
* **Сигнал/Маркер (Cue):** 403 Forbidden `/join/getcourse`, `getcourse_consultation_submission` retry-луп, дубли заявок в GetCourse, `lead_post_submit_tasks` failed 5/5, «Browser redirect без секрета», join page не открывается после формы.
* **Проблема & Причина:** После включения `GETCOURSE_WEBHOOK_SECRET_REQUIRED=true` строгий guard лег и на GET `/join/getcourse`, который вызывается браузером реального лида после редиректа GetCourse (без секрета в query). Итог: реальные лиды видели 403, а фоновая задача `getcourse_consultation_submission` следовала за редиректом, упиралась в 403, ретраилась 5/5 и создавала дубли форм в GetCourse.
* **Стандарт и контрмера:**
  1. Guard `enforce_getcourse_ingestion_guard` получил параметр `require_secret` (default `true` — строго везде по умолчанию). Только `/join/getcourse` вызывает с `require_secret=False`: секрет опционален (при передаче проверяется `compare_digest`, неверный → 403), rate-limit 120/min остаётся. Вебхук `/webhooks/getcourse` — строго с секретом.
  2. `GetCourseConsultationFormClient._submit_with_client` делает POST с `follow_redirects=False`; 302 от GetCourse = заявка принята. Финальный редирект на `bot.aisukam.ru` воркер не открывает. Внимание: httpx `raise_for_status()` бросает и на 3xx — вызывать только при `response.is_error`.
* **Доказательство (Evidence):**
  - RED-A: тест `test_consultation_form_client_does_not_follow_funnelhub_redirect` — `403 Forbidden` → GREEN: запросов ровно 2 (GET формы + POST).
  - RED-B: прод-проба `curl https://bot.aisukam.ru/join/getcourse` → 403; тест `test_join_getcourse_renders_join_page_without_secret` → GREEN 200 + join-страница; неверный секрет 403; вебхук без секрета 403. `verify.ps1 -Subproject funnel-hub` — 18 passed, mypy 54 файлов OK.

### STD-FUNNEL-006 | Все aiogram Bot() на Simplecloud — только через create_telegram_bot(); пропуск funnel-шага без подписанной identity — graceful skip (2026-11-07)
* **Сигнал/Маркер (Cue):** `TelegramNetworkError: Request timeout error`, RestartCount растёт (248), крэш-луп most-бота; в логах funnel-worker сотни `ERROR ... Failed to run funnel step` / `ValueError: Lead has no subscribed messenger identity.`; `Bot(token=` в коде; переезд Simplecloud.
* **Проблема & Причина:** (1) На Simplecloud прямой доступ к `api.telegram.org` заблокирован — рабочая схема одна: Cloudflare Worker (`TELEGRAM_API_BASE_URL` + опциональный `TELEGRAM_PROXY_SECRET`) через `create_telegram_bot()` (`telegram_messaging.py`). Сервисы Моста создавали сырой `Bot(token=...)` → крэш-луп и потеря отправок. (2) Funnel-шаг `step.channel="messenger"` при отсутствии подписанной identity поднимал `ValueError` → ERROR КАЖДЫЙ проход (~3 мин) → 547 ошибок/24ч.
* **Стандарт и контрмера:**
  1. Инвариант: **любой** `aiogram.Bot` в проекте создаётся только через `create_telegram_bot(token, settings)`. Запрещено `Bot(token=...)` напрямую — grep-страж при ревью: `grep -rn 'Bot(token' src/` должен находить только `telegram_messaging.py`.
  2. `MessengerIdentityNotSubscribedError(RuntimeError)` в `funnel_runner`: raise в messenger-ветке `send()`, ловится в `run_due_funnel_once` ДО проверки permanent-маркеров → `session.rollback()`, `skipped += 1`, WARNING «Skipping funnel step: lead has no subscribed messenger identity yet», state остаётся active.
* **Доказательство (Evidence):**
  - ДО: `docker inspect funnelhub-most-telegram-bot-1` → `restarts=248`; funnel-worker 24ч → `547×ERROR`.
  - ПОСЛЕ (`b580395`): most-бот `Run polling for bot @most_cannostei_bot` через прокси, `restarts=0`; funnel-worker → `Skipping funnel step` (WARNING) = 1, `Failed` (ERROR) = 0; 3 passed на локальном `fh-test-pg`, mypy 54 OK.

### STD-UI-002 | Мульти-identity у лида и полный контур уведомлений оператору @leadsaisubot (2026-11-07)
* **Сигнал/Маркер (Cue):** `sqlalchemy.exc.MultipleResultsFound` в `get_inbox_conversation_detail` (`inbox.py`), toast «Inbox detail failed: 500», дубли карточек диалога в списке Inbox; «в `@leadsaisubot` не приходят нажатия кнопок»; лид привязал второй аккаунт того же канала (`messenger_identities`: 2×VK у одного `lead_id`).
* **Проблема & Причина:** (1) `build_conversation_summary_query` делал `.outerjoin(MessengerIdentity, lead_id & channel)` — при двух identity одного канала join размножал строку диалога: список показывал карточку дважды, деталь падала на `one_or_none()` с 500. (2) Уведомление оператору (`notify_admin_about_inbound_message`) вызывалось только когда воронка НЕ распознала ответ (`elif` в ветке `handled`): авто-обработанные нажатия кнопок не уходили в `@leadsaisubot`. (3) Сообщения от пользователей VK без identity молча отбрасывались (`return "ok"`).
* **Стандарт и контрмера:**
  1. Инвариант запросов: по `messenger_identities` в row-запросах диалогов/лидов НЕ джойнить — брать скалярные подзапросы с `ORDER BY created_at DESC LIMIT 1` (идиома `primary_contact_subquery`). Лид может иметь несколько аккаунтов одного канала.
  2. Контракт уведомлений `@leadsaisubot`: (а) каждый входящий ответ лида — текст ИЛИ нажатие кнопки, включая авто-обработанные воронкой; (б) сообщение от непривязанного пользователя VK — через `notify_admin_about_unbound_messenger_message` (`vk_id` + текст, без создания диалога); (в) обе воронки — основная (`telegram_bot`/`vk_bot`) и Мост (`most_telegram_bot`/`most_vk_bot`).
* **Доказательство (Evidence):**
  - ДО: прод-трейсбек `MultipleResultsFound`; 2 строки для VK-диалога Ксении; сообщения непривязанного VK терялись.
  - ПОСЛЕ (`0d7f975`): регресс-тест `test_inbox_detail_with_two_identities_of_same_channel` RED → GREEN; `test_inbox.py` 7/7 passed; `test_inbox_notifications.py` 4/4; mypy OK; контейнеры `restarts=0`, inbox 200.

### STD-FUNNEL-007 | VK-колбэк Моста: секрет/код сверять с VK-админкой, безопасный зонд колбэка (2026-11-07)
* **Сигнал/Маркер (Cue):** `/webhooks/most-vk`, `MOST_VK_CONFIRMATION_CODE`, `MOST_VK_CALLBACK_SECRET`, «Адрес сервера успешно сохранён», `403 Unexpected VK group` / `Invalid VK secret`, health-check VK-бота, «бот VK не реагирует».
* **Проблема & Причина:** (1) `MOST_VK_CONFIRMATION_CODE` в `.env` пуст → на confirmation-рукопожатие сервер отвечал 503. (2) Серверный secret (32 симв.) ≠ секрету в VK-админке (14 симв.) → все `message_new` отбивались бы 403. (3) В хендлере `/most-vk` проверка `group_id` стоит ДО выдачи confirmation-кода — зонд без `group_id` даёт 403.
* **Стандарт и контрмера:**
  1. Секрет и строку подтверждения VK-колбэка брать ТОЛЬКО из админки группы (UI → Настройки → Работа с API → Callback API; через API не выдаются) и синхронизировать в 3 места: сервер `.env` + локальный `.env` + сейф (`STD-022`). При health-check VK-бота сверять ДЛИНЫ значений «админка vs `.env`» (значения не печатать).
  2. Безопасный зонд колбэка (ничего не создаёт): `confirmation` + `group_id` → ожидать точную строку кода; `message_new` с настоящим secret + `text:"/stop"` → `ok` (выход до `record_inbound_messenger_message`, без диалога/уведомлений).
  3. После `docker compose up -d` приложение стартует ~30–60 с: curl в этот период даёт 000 — ждать и повторять.
* **Доказательство (Evidence):**
  - ДО: confirmation → 503 `MOST_VK_CONFIRMATION_CODE is not configured`; secret 32 симв. vs VK 14 симв.
  - ПОСЛЕ: confirmation+`group_id` → `65d51d4d`; wrong secret → 403; real secret + `/stop` → `ok`; баннер VK «Адрес сервера успешно сохранён»; школьный `/webhooks/vk` не задет.

### STD-DATA-006 | Восстановление из дампа: «пропавшие по UUID» могут быть синтетикой — ищи людей по контактам, прогоняй dry-run (2026-11-07)
* **Сигнал/Маркер (Cue):** восстановление из `pg_dump`, сверка «дамп vs боевая база», `EXCEPT`/`INTERSECT` по UUID, «N лидов отсутствуют», `vk_recovery`, lead с `full_name=\N`, счётчики лидов == identities == funnel_states, `duplicate key value violates unique constraint` на dry-run.
* **Проблема & Причина:** (1) Наивная сверка по UUID лида даёт ЛОЖНЫХ пропавших: 417 из 504 лидов — синтетические заготовки `vk_recovery` (`full_name=\N`); их людей в целевой базе уже может представлять ДРУГОЙ лид. (2) Разбор COPY-дампа по `split('\t')` с dict-маппингом порождает сдвиги колонок.
* **Стандарт и контрмера:**
  1. Перед восстановлением определить ПРИРОДУ строк: `source`, пустые имена, соотношение счётчиков; людей искать в целевой базе по phone/email/VK `external_user_id`, а не по UUID лида.
  2. Вставка только через сухой прогон: `BEGIN; COPY…; SELECT-проверки; ROLLBACK` в ОДНОЙ psql-сессии.
  3. Финальная сверка восстановления — по сущностям (`funnel_states`/`identities`/`leads`).
  4. Сырые строки дампа переносить ВЕРБАТИМ (фильтрация строк COPY-блока), не пересобирая значения.
* **Доказательство (Evidence):**
  - Наивный `EXCEPT`: «9 лидов отсутствуют» → dry-run: `duplicate key` (8 уже в базе под другими UUID) → восстановлен 1 реальный (`vk_recovery 2026-06-18`); итог: `leads 621→622`, `funnel_states 417/417`, `messenger_identities 417/417`, 0 лишних рассылок.

### STD-FUNNEL-008 | В app-контейнере FunnelHub нет access-логов: «0 строк в docker logs» ≠ «трафика не было» (2026-11-07)
* **Сигнал/Маркер (Cue):** `grep 'POST /webhooks' docker logs funnelhub-app-1` → пусто; «доходят ли заявки?», «были ли запросы?», health-check приёма лидов.
* **Проблема & Причина:** uvicorn access-логи не пишутся в `docker logs` app-контейнера — по строке «в логах 0 POST» легко ошибочно заключить отсутствие трафика/заявок.
* **Стандарт и контрмера:** факты приёма устанавливать по БД (`leads`/`messages`/`tasks` с `created_at`) и внешним зондам с ожидаемым статусом (`401`/`422`/`403` на кривых данных — маршрут жив и ничего не создаёт); тайминги — по меткам в БД, не по логам.
* **Доказательство (Evidence):** `docker logs funnelhub-app-1` → 0 строк `POST /webhooks/*` при одновременно успешных внешних зондах в тот же час (`65d51d4d` и `422` от PHP-обработчика).

### STD-FUNNEL-009 | Маркерный дрейф сообщений об ошибках и глубокие DB-тесты в гейте verify (HARNESS-002)
* **Сигнал/Маркер (Cue):** `PERMANENT_DELIVERY_ERROR_MARKERS`, `"(or is test account)"`, email bounce, пауза воронки, вечный ретрай, 4578 ошибок, `verify.ps1` 18 passed, глубокие DB-тесты, `fh-test-pg`, `ORDER BY created_at` tie.
* **Проблема & Причина:** Текст исключения в `email_messaging.py:220` получил суффикс `(or is test account)` (`STD-EMAIL-002`), а строковый маркер в `PERMANENT_DELIVERY_ERROR_MARKERS` остался со старым текстом и хвостовой точкой — классификация перестала совпадать, пауза не ставилась, email-шаги ретраились бесконечно (4 лида → 4578 ошибок/сутки). Дрейф не ловился гейтом, потому что `verify.ps1` гонял только 18 быстрых тестов без DB-набора.
* **Стандарт и контрмера:**
  1. При изменении текста исключений-маркеров обновлять ОБЕ стороны; маркеры держать стабильными префиксами БЕЗ хвостовых знаков препинания (совпадение подстрокой).
  2. RED-тест воспроизводить ТОЧНЫМ текстом продовой ошибки (из лога/трейсбека), а не реконструированным по памяти.
  3. Глубокие DB-тесты — обязательная ступень гейта: `scripts/verify-deep.ps1` (52 теста) через контейнер `fh-test-pg`; на машинах без Docker — SKIP с пометкой.
  4. В тестах, где несколько сообщений пишутся в одной транзакции, `ORDER BY created_at` нестабилен — сравнивать тела как мультимножество (`sorted(...)`).
* **Доказательство (Evidence):**
  - RED: `test_run_due_funnel_once_pauses_email_step_without_subscription` падает ошибкой `ValueError: Lead has no subscribed email subscription (or is test account).` (state active).
  - GREEN: после фикса маркера — глубокий набор 52 passed, 4 skipped; полный гейт `verify.ps1 -Subproject funnel-hub` → 18 passed + `[DEEP] 52 passed` (23.6s); деплой `2608f32`, шторм остановлен.

### STD-FUNNEL-010 | Надёжный диплинк Telegram ботов, транзитный переход /join/{token}/tg и телефонный fallback (HARNESS-002)
* **Сигнал/Маркер (Cue):** `bot_link_tokens`, `?start=token`, `handle_start`, `command.args is None`, `Update id is handled`, «перейдите по ссылке на странице после заявки», Telegram Web, WhatsApp/VK in-app browser stripping query params, пустой старт.
* **Проблема & Причина:** Прямые ссылки вида `https://t.me/bot?start=token`, передаваемые лидам вручную из CRM, открываются во встроенных WebView или Telegram Web, где `tg://resolve` срезает query-параметр `?start=`, либо при существующей истории чата `/start` передаёт команду без аргументов (`command.args is None`), давая тупиковый отказ без создания идентичности.
* **Стандарт и контрмера:**
  1. В CRM в карточке лида выдавать 3 раздельные ссылки: (а) страница подарков `/join/{token}`, (б) транзитная ссылка Telegram `/join/{token}/tg` (пробрасывает прямое приложение `tg://resolve?domain=...&start=...`), (в) VK `/join/{token}/vk`.
  2. В `telegram_bot.py` и `most_telegram_bot.py`:
     - парсить токен из любого текстового сообщения лида (прямой URL, `t.me` URL, чистый токен) через `extract_bot_link_token`;
     - при пустом `/start` предлагать подтверждение заявки кнопкой «📱 Подтвердить заявку по номеру телефона» (`request_contact=True`) либо вводом телефона/ссылки;
     - по номеру телефона сопоставлять лида в `lead_contacts` и автоматически привязывать к воронке.
* **Доказательство (Evidence):**
  - RED: Update `662570790` (2026-11-11 17:19:55 UTC) обработан с отказом без создания `messenger_identities`.
  - GREEN: `tests/test_telegram_bot.py` (6 passed), `tests/test_join_page.py` (3 passed), `verify.ps1 -Subproject funnel-hub` (18 passed, ruff/mypy clean), `npm run build` (`inbox-app`) 2.25s.

### STD-DATA-007 | Слияние дампа Beget: строгий 1:1 `rn_prod = 1` теряет контакты и UTM с вторичных карточек одного человека (2026-11-18)
* **Сигнал/Маркер (Cue):** `SOP-BACKUP-001`, `rn_prod = 1`, `skipped_collision_leads`, дубли карточек лида в дампе (`landing` + `@vktech.gc`), `lead_contacts.is_primary`, `beget_restore`, `st_match`, 10-цифровой телефон `9xxxxxxxxx`.
* **Проблема & Причина:** Один и тот же человек на Beget часто существовал в двух несклеенных карточках (лендинг + `@vktech.gc`). На Simplecloud привязана была только одна. Фильтрация `WHERE rn_st = 1 AND rn_prod = 1` отбрасывала 22 вторичные карточки (терялись `45` реальных контактов и `61` UTM-строка). Плюс 10-значные номера `9xxxxxxxxx` без `7` и опечатки домена (`@yandexry`) не ловились точным `=`.
* **Стандарт и контрмера:**
  1. Для маппинга `st_match` («строка дампа → продовый лид») фильтровать только `WHERE rn_st = 1`, допуская маппинг нескольких дублей из дампа на одного `prod_id`.
  2. `rn_prod = 1` применять только в `UPDATE leads`, а для `lead_contacts` при массовой вставке использовать `row_number() OVER (PARTITION BY prod_id, contact_type ORDER BY is_primary DESC, created_at, id) = 1` + проверку `NOT EXISTS (... is_primary IS TRUE)`.
  3. Тестовые адреса и пустые карточки без контактов/идентичностей/`gc_id` исключать до маппинга.
  4. Сравнивать телефоны по `right(regexp_replace(normalized_value, '\D', '', 'g'), 10)`, а email — также по `split_part(..., '@', 1)`; при склейке переносить `bot_link_tokens` и все 17 FK на выжившую карточку до удаления донора.
* **Доказательство (Evidence):**
  - RED (`rn_st = 1 AND rn_prod = 1`): `skipped_collision_leads=22` (терялись `45` контактов и `61` UTM), выявлено 8 скрытых дублей.
  - GREEN (`rn_st = 1` + CTE `rn_prim` + склейка `8` пар): `skipped_collision_leads=0`, `inserted_new_leads=131`, `inserted_contacts=400`, `inserted_utm=531`, `inserted_identities=56`, затем `deleted_donor_leads=8` (`leads 801→793`), повторный аудит: `0` дублей.
