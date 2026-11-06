# Operating Manual: FunnelHub & Infrastructure Security Harness

This repository is governed by the **Harness Engineering** methodology.
The repository is the **Single System of Record**.

> **Сквозные стандарты школы:** Перед реализацией общих стандартов безопасности и инфраструктуры сверяться с [.harness/lessons.md](file:///./.harness/lessons.md).  
> **Локальный журнал прогресса:** [progress.md](file:///./projects/funnel-hub/progress.md)

---

## 🚀 Startup Workflow

Перед написанием любого кода или внесением изменений:

1. **Подтвердить рабочую директорию**: `C:\Users\circlealgorythm\Documents\Бот воронка`.
2. **Прочитать этот файл (`AGENTS.md`)** полностью.
3. **Запустить скрипт верификации окружения**:
   - Windows: `powershell -ExecutionPolicy Bypass -File .\init.ps1`
   - Linux / Bash: `./init.sh`
4. **Прочитать `feature_list.json`**: определить текущее состояние фич.
5. **Прочитать `progress.md`**: увидеть текущий статус сессии и активную задачу.
6. **Проверить `git status` и последние коммиты**: `git log --oneline -5`.

Если базовая верификация (`init.ps1` / `pytest`) падает, сначала устраняется поломка базовой ветки перед взятием любой новой задачи.

---

## ⚡ Working Rules (Строгий регламент работы)

1. **Строго одна фича за раз (One Feature at a Time):**
   - Выбирается ровно одна незавершенная задача из `feature_list.json` с наивысшим приоритетом.
   - Статус переводится в `"in-progress"`. В любой момент времени **только одна** фича может иметь статус `"in-progress"`.
2. **Запрет самовольного перехода к следующей задаче (Human Gate):**
   - Реализуется выбранная фича.
   - Проводится эмпирическая верификация (запуск тестов, проверка синтаксиса, curl/статус-коды).
   - Фиксируются доказательства (`evidence`) в `feature_list.json` и `progress.md`.
   - Статус переводится в `"passing"`.
   - **Фиксируется атомарный Git-коммит фичи** (согласно правилу 7) до отчета.
   - **ОСТАНОВКА:** Агент отчитывается пользователю с хешем коммита и доказательствами работы, после чего **ждет команды пользователя** перед переходом к следующей фиче.
3. **Эмпирическая верификация (Verification Required):**
   - Запрещено объявлять задачу завершенной без запуска команд верификации.
   - Никаких заглушек (`TODO`, `pass`, `coming soon`) и закомментированного кода.
4. **Соблюдение границ изменений (Scope Discipline):**
   - Не трогать и не модифицировать файлы, не относящиеся к текущей задаче.
5. **Чистое состояние (Clean State):**
   - По завершении шага `init.ps1` / тесты должны проходить чисто.
   - Обновляются артефакты: `feature_list.json`, `progress.md`, `session-handoff.md`.
6. **Протокол защиты от поломок (Zero-Regression & Business Continuity):**
   - Любое изменение обязано сохранять 100% обратную совместимость.
   - Формы сайта: поля, валидация SmartCaptcha, отправка в Google Sheets и JSON-ответ `{ ok: true }` остаются неизменными.
   - База данных: структура таблиц (`leads`, `lead_contacts`) и том с данными `postgres_data` неприкосновенны. Изменение учетных данных БД проводится синхронно для приложения, ботов и фоновых воркеров.
   - Перед объявлением фичи завершенной обязательно проводится синтаксическая и интеграционная проверка.
7. **Обязательная атомарная фиксация в Git (Mandatory Atomic Git Commit):**
   - Сразу после завершения реализации фичи, её успешной верификации и обновления артефактов (`feature_list.json`, `progress.md`, `session-handoff.md`), все изменения фичи **ОБЯЗАНЫ быть зафиксированы атомарным коммитом** в Git соответствующего репозитория (`AisuKam_site` или `FunnelHub`).
   - Запрещено переходить к отчету пользователю и ожидать команду на следующую задачу с незакоммиченными изменениями.
   - В `git add` добавляются строго файлы текущей фичи и обновленные артефакты; запрещено делать `git add .` или включать посторонние рабочие файлы.
   - Формат коммита: `<тип>(<ID_фичи>): <описание>`, например: `security(SEC-004): add security headers and body limit in caddyfile`.
   - Это гарантирует полную безопасность и возможность чистого отката (`git revert` / `git checkout`) в любой момент.

---

## 📦 Обязательные артефакты Harness

- `feature_list.json` — машиночитаемый реестр задач и статусов (источник истины).
- `progress.md` — непрерывный журнал сессий и прогресса.
- `session-handoff.md` — протокол передачи контекста между сессиями.
- `init.ps1` / `init.sh` — стартовые скрипты верификации окружения.

---

## 🛠️ Операционные регламенты (SOP)

### SOP-EMAIL-001 | Ручная отписка лида от email-рассылок (Unisender Go & FunnelHub)
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
Проект «Мост ценностей» реактивирован по запросу пользователя.
1. Сервисы в `docker-compose.prod.yml`:
   - `most-telegram-bot` (актуальный бот: `@most_cannostei_bot`, ID: `8705381132`)
   - `most-funnel-worker`
   - `most-vk-funnel-worker`
2. **Инвариант эксплуатации:** Сервисы запущены в штатном режиме. Токен `MOST_TELEGRAM_BOT_TOKEN` обновлен в боевом `.env`, бот успешно опрашивает Telegram API. В админке FunnelHub возвращены раздельные вкладки сегментов для Inbox и Базы, а лиды «Моста ценностей» изолированы в соответствующем сегменте.
3. **Доказательство (Evidence):**
   - Успешный деплой через `deploy_files.py` (exit 0).
   - Логи на сервере Beget: `funnelhub-most-telegram-bot-1` (Start polling for `@most_cannostei_bot`, обработка updates `839195251`, `839195252`), `funnelhub-most-funnel-worker-1` (`Most funnel runner pass completed`), `funnelhub-most-vk-funnel-worker-1` (`Most VK funnel runner pass completed`).
   - Админка `https://bot.aisukam.ru/inbox/` — HTTP 200 OK.

### SOP-BACKUP-001 | Слияние при возврате бэкапа Beget VPS (план восстановления, 2026-11-06)
* **Контекст:** Beget VPS `31.129.110.56` уничтожен инфраструктурным инцидентом 2026-11; FunnelHub работает на Simplecloud (`85.143.175.148`) на БД, собранной через GC-импорт (DATA-002, граница 2026-05-27) + живые вебхуки. Beget обещает вернуть файловые бэкапы VPS части пользователей (обновление от 2026-11-06). Если дамп Beget вернётся: **история переписки (`conversations`/`messages`), `funnel_states`, `events` и исходные ~499 лидов восстановимы ТОЛЬКО из него** — в текущей базе их нет.
* **Инварианты слияния:**
  1. Дамп Beget загружать в ОТДЕЛЬНУЮ схему/БД на Simplecloud (например `beget_restore`); боевые таблицы не трогать до сухого прогона.
  2. Слияние лидов по ключам в порядке приоритета: `getcourse_user_id` → VK-identity (`messenger_identities.channel='vk'`) → нормализованный телефон → email (lower). Только подтверждённые совпадения (Phone-First, STD-DATA-003); однофамильцев не сливать.
  3. Переписку (`conversations`/`messages`) переносить из бэкапа целиком, только для лидов, существующих в текущей базе; дедупликация по `external_message_id` либо `(lead_id, channel, sent_at)`; конфликты — в пользу более свежей записи.
  4. Объём-правило (STD-DATA-004 п.5): лиды GC с регистрацией ранее 2026-05-27 из бэкапа НЕ воскрешать.
  5. UNIQUE-конфликты решать в пользу прод-записи (`ON CONFLICT DO NOTHING`): `lead_contacts(contact_type, normalized_value)`, `leads.getcourse_user_id`, `lead_external_ids(provider, external_id)`, `messenger_identities(channel, external_user_id)`, `lead_tags(lead_id, tag)`, `lead_custom_fields(lead_id, source, field_key)`.
  6. Лиды из бэкапа без аналога в проде вставлять только из FunnelHub-каналов (`vk_recovery`, `landing_consultation`); `lead_tags.id` задаётся явно (`gen_random_uuid()`, у таблицы нет server_default).
  7. Чужие VK-идентичности из бэкапа — только `is_subscribed=false` (STD-DATA-005).
* **Процедура:** дамп текущего прода (`pg_dump -Fc`) + копия локально → загрузка бэкапа в отдельную схему → dry-run слияния (BEGIN…ROLLBACK: счётчики мёржа/вставок, список конфликтов, выборка карточек) → ревью пользователем → COMMIT → POST-MERGE VERIFY (счётчики до/после, выборочные диалоги, `verify.ps1 -Subproject funnel-hub`, HTTP 200 `/inbox/`, чистые логи вебхуков).
* **Статус:** план согласован с пользователем 2026-11-06; Evidence (RED→GREEN) появится по факту исполнения слияния.

### STD-FUNNEL-001 | Мультипроектная изоляция сегментов базы и дедупликация GetCourse
* **Проблема:** При склейке существующего контакта школы (GetCourse ID, email, телефон) с заявкой из дочернего лендинга («Мост ценностей») базовое поле `Lead.source` сохраняет исходный источник контакта. Простой фильтр `Lead.source != exclude_source` не исключал такой склеенный лид из «Общей базы», что приводило к дублированию лида в обоих разделах админки.
* **Стандарт:** Фильтрация по исключению источника (`exclude_source`) в `inbox_database.py` и `inbox.py` обязана строиться через `lead_exclude_source_filter`, проверяющий как отсутствие прямого `Lead.source == exclude_source`, так и отсутствие связанных событий `Event.source == exclude_source`.
* **Доказательство (Evidence):**
   - Тест `test_existing_lead_submitting_most_is_isolated_to_most_segment` в `tests/test_most_tsennostey_applications.py` подтверждает изоляцию (`assert existing_lead_id not in [item.id for item in main_leads.items]`).
   - Прогон `scripts/verify.ps1 -Subproject funnel-hub` завершен с кодом 0 (8 passed, ruff passed, mypy passed).

### STD-FUNNEL-002 | Мультипроектная сегментация лидов: Контентный блог и статьи обращения
* **Проблема:** Лиды с контентного блога (`aisukam.ru/blog/*`) и основного сайта (`aisukam.ru`) отправляли заявки через единый бэкенд `submit-lead.php`. Заявки смешивались в сегменте «Общая база», а оператор и маркетолог не видели, с какой конкретно статьи блога пришел пользователь.
* **Стандарт:** 
  1. Формы блога обязаны принудительно задавать `source = 'blog'` и передавать метаданные `article_title` и `article_url`. На сервере `submit-lead.php` действует резервный fallback по `HTTP_REFERER`.
  2. Вебхук Funnel Hub сохраняет поля статьи в `LeadCustomField` («Статья блога», «Ссылка на статью»).
  3. `inbox_database.py` и `inbox.py` обязаны поддерживать множественное исключение `exclude_source` через запятую (например, `exclude_source='most-tsennostey,blog'` для вкладки «Общая база»).
  4. Вкладка «Блог» в `inbox-app` изолированно запрашивает `source=blog`, выводит бейдж `📄 <Название статьи>` в таблице лидов и интерактивную карточку со ссылкой в карточке лида, а поля `article_title` и `article_url` включаются в экспорт CSV/XLSX.
* **Доказательство (Evidence):**
  - Unit-тесты `tests/test_blog_segmentation.py` (6 тестов: Pydantic-схема, мульти-фильтрация SQL, экспортные колонки) — `14 passed in 5.74s`.
  - Успешный боевой деплой на Beget VPS (`deploy_files.py`), HTTP 200 на `https://bot.aisukam.ru/inbox/`.

### STD-SEC-001 | Защита от спуфинга IP в Rate Limiter и харденинг VK вебхуков (HARNESS-002)
* **Проблема:**
  1. `get_request_ip` брал первый IP из `X-Forwarded-For`. Злоумышленник мог передавать поддельные IP в заголовке (`X-Forwarded-For: <fake_ip>, <real_ip>`), обходя лимит попыток входа в админку `/api/auth/login`.
  2. `InMemoryRateLimiter` накапливал корзины IP в памяти без очистки устаревших ключей (риск разрастания памяти).
  3. Проверка секрета VK использовала оператор `!=` (теоретический риск timing-атак).
* **Стандарт:**
  1. В `get_request_ip` доверять строго последнему IP в списке `X-Forwarded-For` (`ips[-1]`), который гарантированно дописывается доверенным реверс-прокси Caddy на сервере.
  2. В `InMemoryRateLimiter` при превышении порога в 500 ключей автоматически удалять устаревшие и пустые корзины.
  3. В `validate_vk_secret` использовать `secrets.compare_digest` и валидировать `group_id` по доверенным группам (`vk_group_id`, `most_vk_group_id`).
* **Доказательство (Evidence):**
  - Unit-тест `test_login_rate_limiting_ip_spoofing_prevention` в `tests/test_auth.py`: запросы с поддельными клиентскими IP при одинаковом прокси-IP блокируются с кодом 429 (GREEN).
  - Unit-тест `test_rate_limiter_memory_pruning`: 550 устаревших корзин очищаются до 1 свежей при добавлении нового ключа (GREEN).
  - Unit-тест `test_validate_vk_secret_constant_time` в `tests/test_cors_and_vk_failclosed.py` (GREEN).
  - `pwsh -ExecutionPolicy Bypass -File scripts/verify.ps1 -Subproject funnel-hub` успешно пройден (код 0 за 10.3s).

### STD-SEC-002 | Защита от Formula Injection в экспорте таблиц и отзыв сессий (HARNESS-002)
* **Проблема:**
  1. Пользовательский ввод в формах (имя, город, комментарии, UTM-метки) при экспорте в CSV или Excel (`inbox_database.py`) мог содержать формульные префиксы (`=cmd|...`, `@SUM(...)`), вызывая Formula Injection при открытии файла в Microsoft Excel.
  2. Сессионные куки JWT после нажатия кнопки «Выход» в админке оставались валидными по криптоподписи до истечения TTL (Hardening 3.1).
* **Стандарт:**
  1. В `inbox_database.py` функция `sanitize_spreadsheet_cell` обязана экранировать префиксы `=`, `@`, `\t`, `\r`, а также `+` и `-` (если за ними не следует валидный числовой телефон/число) одинарной кавычкой `'`. Экранирование применяется ко всем ячейкам при экспорте CSV и XLSX.
  2. В `auth.py` сессионные куки содержат `jti`. При логауте токен регистрируется в хранилище отозванных сессий `REVOKED_SESSIONS` с автоочисткой по истечении TTL.
* **Доказательство (Evidence):**
  - Unit-тест `test_sanitize_spreadsheet_cell_formula_injection`: опасные формулы экранируются, телефоны `+79991234567` и числа `-500` не искажаются (GREEN).
  - Unit-тест `test_logout_revokes_session_cookie`: попытка повторного использования куки после логаута завершается HTTP 401 (GREEN).
  - `pwsh -ExecutionPolicy Bypass -File scripts/verify.ps1 -Subproject funnel-hub` (18 passed, ruff passed, mypy passed).

### STD-FUNNEL-003 | Автостарт VK-воронки: платформенный предел VK и UX-контрмера «Разрешить сообщения» (HARNESS-002)
* **Сигнал/Маркер (Cue):** «VK бот не пишет первым», «воронка не стартует автоматически после заявки», «новый аккаунт VK — тишина в чате», `message_allow`, `vk.me?ref`, переход со страницы спасибо `/join/{token}`.
* **Проблема & Причина:** VK Callback API **не отправляет сообществу никакого события**, когда пользователь просто открывает чат (даже с нового аккаунта и даже при подписанном message_allow). Автостарт воронки физически возможен только по событию `message_allow` (тап «Разрешить сообщения») или `message_new` (первое сообщение пользователя) — в обоих VK передает `ref` из ссылки `vk.me/<screen>?ref=<token>`. Прямая отправка без события падает с VK error 901 (классифицируется как permanent → пауза воронки), а узнать VK ID без действия пользователя нельзя (VK OAuth-флоу `vk_oauth.py` реализован, но отклонён пользователем: длинный путь снижает конверсию). После переноса БД на Simplecloud база `messenger_identities` пуста для новых людей — путь `relaunch_vk_for_known_lead` (мгновенная отправка известным VK ID) перестал покрывать новых лидов, и платформенный разрыв стал видимым.
* **Стандарт и контрмера:**
  1. Диагностику автостарта вести по БД, а не по docker-логам (uvicorn не пишет access-логи, INFO логи `funnelhub.*` не проходят root-handler): `funnel_states.metadata->>'restart_reason' = 'bot_start'` + ключ `ref` в `messenger_identities.raw_profile` = событие пришло с токеном и воронка стартовала по нему.
  2. При подозрениях на `message_allow` сверять подписку события в UI настроек Callback API сообщества («Разрешение на получение»); токен группы имеет scope только `messages` — `groups.getCallbackSettings` вернёт error 15/1133. Чекбокс «Исходящее сообщение» (message_reply) включать не нужно — это эхо собственных отправок.
  3. UX-стандарт: на join-странице (`render_join_page`) обязана быть инструкция одного касания: «в VK нажмите "Разрешить сообщения", в Telegram — "Запустить"». Набор текста пользователем не требуется, конверсия не страдает.
* **Доказательство (Evidence):**
  - Ксения (VK ID 258149228, заявка 2026-11-06 15:55 UTC): SQL `funnel_states` → `restart_reason='bot_start'`, 15:56:37 — первое сообщение ушло автоматически по событию с ref (`raw_profile` содержит ключ `ref`).
  - Светлана/«Екатерина Пушкина» (заявка 15:59 UTC, заведомо новый VK-аккаунт): ноль строк в `messenger_identities`/`messages`/`events` по VK — открытие чата без тапа «Разрешить» не генерирует событий.
  - Скриншот настроек Callback API сообщества: «Разрешение на получение» включён; `groups.getCallbackSettings` под токеном группы → error_code 15 (no scopes).
  - Верификация правки: `verify.ps1 -Subproject funnel-hub` код 0 (ruff, mypy 54 файлов, 18 тестов); `tests/test_join_page.py` 2 passed; визуальный контроль render_join_page (десктоп 1280px + мобайл 390px).

### STD-SEC-003 | Защита периметра через Content-Security-Policy в Caddyfile (HARNESS-002)
* **Проблема:**
  В заголовках безопасности реверс-прокси Caddy отсутствовала директива `Content-Security-Policy`, что снижало защиту от атак XSS и кликджекинга при работе с веб-интерфейсом FunnelHub (`bot.aisukam.ru`).
* **Стандарт:**
  В блоке `header` конфигурации `Caddyfile` задавать строгую политику CSP:
  `Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self' https://bot.aisukam.ru; frame-ancestors 'self';"`
  Обязательно покрывать наличие CSP и балансировку скобок тестом в `tests/test_caddyfile.py`.
* **Доказательство (Evidence):**
  - Unit-тест `tests/test_caddyfile.py` проверяет директиву `Content-Security-Policy` и сбалансированность фигурных скобок (PASS).
  - Прогон `scripts/verify.ps1 -Subproject funnel-hub` (ruff, mypy, 18 unit-тестов) успешно завершен с кодом 0.

### STD-EMAIL-002 | Защита квоты Unisender Go: супрессия тестовых адресов и фильтрация по Gmail (HARNESS-002)
* **Проблема:**
  Тестовые заявки администратора с ключевыми словами алгоритма (`circlealgorythm@gmail.com`, `test-webhook@aisukam.ru`, `jogspokoen@*`) приводили к холостому расходу лимита Unisender Go (6,000 писем/мес). При этом требовалось не отсекать реальных лидов с корпоративными или сторонними доменами, содержащими корень "алгоритм".
* **Стандарт:**
  1. В `email_messaging.py` внедрена функция `is_test_email(email)`.
  2. Для корней `algor...` / `alory...` отсечение выполняется СТРОГО на домене `@gmail.com` (`.*al[go]r[yi]thm.*@gmail\.com`). Все остальные почтовые провайдеры разрешены для клиентов.
  3. Для паттернов `jogspokoen` и административных адресов `ADMIN_EMAILS` отсечение действует безусловно.
  4. На уровне `funnel_autostart.py` и `getcourse_webhook.py` тестовые адреса автоматически маркируются как `unsubscribed`, исключаются из запуска рассылок и заносятся в Unisender Suppression List (`cause="unsubscribed"`).
* **Доказательство (Evidence):**
  - Unit-тест `test_is_test_email_detection` в `tests/test_email_messaging.py`: покрывает тестовые ящики на gmail (`circlealgorythm@gmail.com`), легитимные ящики на других доменах (`algorithm.lead@mail.ru`, `client.algorithm@yandex.ru` -> False), `jogspokoen@*`, `aisukam-info@yandex.ru` (GREEN).
  - Запрос `suppression/get.json` к API Unisender Go подтвердил наличие 8 тестовых адресов в статусе `unsubscribed`.
  - `pwsh -ExecutionPolicy Bypass -File scripts/verify.ps1 -Subproject funnel-hub` успешно пройден (18 unit-тестов, ruff, mypy).

### STD-DATA-003 | Инвариант слияния лидов: Phone-First и сопоставление с VK ID (HARNESS-002)
* **Проблема:**
  При интеграции 87 лидов из Google Sheets CRM и 417 лидов из VK бота требовалось сопоставить профили. Попытка слияния по именам несла высокий риск ложных объединений (однофамильцы, распространенные имена "Ольга", "Елена").
* **Стандарт:**
  1. Строгий инвариант: слияние записей (`landing_consultation` + `vk_recovery`) разрешено СТРОГО при совпадении нормализованного номера телефона (`+7...` / 11 цифр) или при 100% подтвержденном совпадении по таймстампу, форме и уникальному ФИО/DEF-коду региона.
  2. Все остальные лиды CRM без подтвержденного телефона или профиля VK сохраняются как независимые сущности с источником `landing_consultation` без риска коллизий.
  3. При объединении профилю присваивается составной источник `landing_consultation + vk`, привязывается `client_id` Яндекс.Метрики и объединяется история контактов.
* **Доказательство (Evidence):**
  - Транзакционный аудит базы данных PostgreSQL на Simplecloud VPS (`85.143.175.148`): успешно объединено ровно 8 подтвержденных пар лидов; оставшиеся 79 лидов CRM изолированы без искажения персональных данных.
  - Запрос `SELECT source, count(*) FROM leads GROUP BY source;` подтвердил: `landing_consultation + vk`: 8, `landing_consultation`: 79, `vk_recovery`: 409.


### STD-FUNNEL-004 | Интеграция Telegram Bot API через Cloudflare Worker Reverse Proxy и калибровка таймаутов aiogram (HARNESS-002)
* **Сигнал/Маркер (Cue):** Telegram Bot API, Simplecloud VPS, aiogram 3, ТСПУ, TCP 443 timeout, Cloudflare Worker, TelegramAPIServer, TELEGRAM_API_BASE_URL, create_telegram_bot, polling_timeout, getUpdates timeout.
* **Проблема:**
  На российских серверах Simplecloud исходящие TCP-соединения к пулам IP Telegram (`149.154.*`, `91.108.*`) на порт 443 блокируются ТСПУ (`Connection timed out`), из-за чего aiogram не может связаться с `api.telegram.org` и бот падает в бесконечный реконнект. Попытка поднять PHP-прокси на хостинге Reg.ru натолкнулась на аналогичную фильтрацию ТСПУ.
* **Причина:**
  Сетевая фильтрация на уровне провайдеров РФ отсекает прямой доступ к домену Telegram. Кроме того, при long-polling опросе `getUpdates` через Cloudflare Worker разрыв соединений по внутренним edge-таймаутам Cloudflare (100–300 с) при дефолтном таймауте aiohttp вызывал периодические ошибки `TelegramNetworkError: Request timeout error`.
* **Стандарт и контрмера:**
  1. Разворачивается бессерверный Cloudflare Worker Reverse Proxy (`export default { async fetch(req) { const u = new URL(req.url); u.hostname = 'api.telegram.org'; return fetch(new Request(u, req)); } }`), трафик к которому из РФ не блокируется и имеет задержку < 40 мс.
  2. В `src/funnelhub/services/telegram_messaging.py` создана централизованная фабрика `create_telegram_bot(token, settings)`. При наличии `settings.telegram_api_base_url` создается `TelegramAPIServer.from_base(base_url)` и передается в `AiohttpSession`.
  3. Все точки создания бота (`funnel_worker.py`, `telegram_bot.py`, `inbox.py`, `inbox_notifications.py`) используют исключительно `create_telegram_bot`, исключая прямой вызов `Bot(token=...)`.
  4. В `telegram_bot.py` для aiogram задается явный таймаут long polling: `dispatcher.start_polling(bot, polling_timeout=10)`, что исключает зависание сессий на границе таймаутов прокси и обеспечивает автоматическое переподключение без потери апдейтов.
* **Доказательство (Evidence):**
  - RED: Прямой вызов с Simplecloud `curl -m 5 https://api.telegram.org/bot<token>/getMe` ➔ `Connection timed out (exit 28)`.
  - GREEN: Вызов через Cloudflare Worker `curl -s https://lingering-forest-a1b9.circlealgorythm.workers.dev/bot<token>/getMe` ➔ `{"ok":true,"result":{"id":8963890043,"is_bot":true,"username":"vedicschool_aisu_bot"}}` (exit 0, ответ 100 мс).
  - Верификатор `verify.ps1 -Subproject funnel-hub` успешно пройден (18 unit-тестов, ruff, mypy без ошибок).
  - Контейнер `funnelhub-telegram-bot-1` на Simplecloud стабильно вычитывает события, `curl .../getWebhookInfo` подтвердил `pending_update_count: 0`.

### STD-DATA-004 | Массовый импорт лидов GetCourse через API: гонка с вебхуками, guard UNIQUE-ссылки и lead_tags.id (HARNESS-002)
* **Сигнал/Маркер (Cue):** GetCourse API, /pl/api/account/users, created_at[from], idgrouplist=id_date, массовый импорт, uq_leads_getcourse_user_id, duplicate key 504948483, вебхук-гонка, getcourse_webhook, lead_tags.id, import_gc_users.sql, dry-run, pg_dump rollback.
* **Проблема:**
  Боевой импорт 1188 пользователей GetCourse (823 новых лидов) дважды падал на проде: (1) `duplicate key value violates unique constraint "uq_leads_getcourse_user_id"` на gc_id 504948483 — живой вебхук GetCourse создал лида между dry-run и коммитом; (2) `null value in column "id" of relation "lead_tags"` — в миграции 20260806_01 у lead_tags.id UUID НЕТ server_default.
* **Причина:**
  Импорт и вебхуки GC пишут в `leads` параллельно: raw-SQL INSERT/UPDATE без guard-а предполагал отсутствие конкурирующих писателей. Дополнительно raw-SQL вставка в lead_tags не генерирует UUID (в отличие от таблиц 0001_core_data_model, где id имеет server_default gen_random_uuid()).
* **Стандарт и контрмера:**
  1. Любой массовый импорт в `leads` обязан содержать guard от гонки с вебхуками: и в UPDATE-линк (`AND NOT EXISTS (SELECT 1 FROM leads l2 WHERE l2.getcourse_user_id = s.gc_id AND l2.id <> l.id)`), и в INSERT новых (`AND NOT EXISTS (SELECT 1 FROM leads l WHERE l.getcourse_user_id = s.gc_id)`). Пропущенных «вебхуковых» лидов обогащать через карту gc_id→lead_id (`JOIN leads ON l.getcourse_user_id = s.gc_id`).
  2. В raw-SQL вставках UUID-первичные ключи без server_default (lead_tags) задавать явно: `SELECT gen_random_uuid(), ...`.
  3. Обязательный пайплайн боевого импорта: dry-run (BEGIN…ROLLBACK, отчёт на ревью) → pg_dump на сервере + копия локально + скрипт отката → commit-прогон → POST-IMPORT VERIFY.
  4. GetCourse API: без фильтра `error_code 908` («Должен быть передан хотя бы один фильтр»); полная выгрузка = `created_at[from]=YYYY-MM-DD&created_at[to]=...`; группы = `idgrouplist=id_date` (формат `idgrouplist=id` отдаёт пустую колонку); ключ — `GETCOURSE_API_KEY` из `.env.recovery.template`; технические email `@vktech.gc` отсекать (`is_getcourse_technical_email`), их VK-ID извлекать из префикса `id<N>`.
  5. Объём импорта ограничен датой запуска FunnelHub (создан 2026-05-20): в базу входят только лиды GC, зарегистрированные с 2026-05-27 (согласовано с пользователем). Полная выгрузка «всей базы GC» избыточна — GC существовал с 2024, и лиды до запуска FunnelHub в базу не нужны. Если импорт уже выполнен шире границы, чистка = `DELETE FROM leads WHERE raw_getcourse_data->>'origin'=<маркер> AND getcourse_created_at < <граница>` (каскад сносит контакты/UTM/теги/идентичности; dialogs/funnel_states у импортированных отсутствуют).
* **Доказательство (Evidence):**
  - RED-1: `psql -v commit=1 -f import_gc_users.sql` ➔ `ERROR: duplicate key ... (Key (getcourse_user_id)=(504948483))`, авто-ROLLBACK (leads 500, gc-linked 1).
  - RED-2: повтор ➔ `UPDATE 363, INSERT 823 ... ERROR: null value in column "id" of relation "lead_tags"`, авто-ROLLBACK (leads 500).
  - GREEN: guard-версия ➔ `UPDATE 363; INSERT 0 823; INSERT 0 1020 (email); INSERT 0 823 (phone); INSERT 0 784 (utm); INSERT 0 794 (tags); INSERT 0 1033 (custom); INSERT 0 1186+313 (ext ids); COMMIT`. POST-IMPORT VERIFY: leads 1323, leads_with_gc_id 1188, emails 1025, phones 913, utm 872, gc_tags 794.
  - Чистка объёма: `DELETE 698` (регистрации 2024-10-16…2026-05-19) ➔ leads 624, gc_linked 490, min gc_created оставшихся импортированных = 2026-05-27.
  - Контейнеры Up, `https://bot.aisukam.ru/inbox/` HTTP 200, ошибок в логах app за 10 мин нет.

### STD-DATA-005 | Импорт VK-идентичностей из GetCourse: только is_subscribed=false (HARNESS-002)
* **Сигнал/Маркер (Cue):** messenger_identities, is_subscribed, колонка КАНАЛ, VK-бейдж, inbox lead database, импорт VK-ID, uq_messenger_identities_channel_external_user_id.
* **Проблема:**
  Колонка КАНАЛ в базе лидов пуста у импортированных из GetCourse лидов: identities создаются только ботами при живом диалоге. Наивная вставка identity с дефолтом `is_subscribed=true` дала бы ботам «право» слать VK-сообщения пользователям, никогда не подписывавшимся на сообщество (первая же отправка упала бы 901/902 и fail-closed отписал бы их).
* **Причина:**
  `messenger_identities.is_subscribed` по умолчанию true; все механики отправок фильтруют `is_subscribed IS TRUE`, поэтому флаг = прямое разрешение на рассылку.
* **Стандарт и контрмера:**
  1. При импорте VK-ID из внешних источников (GetCourse и др.) identity создавать СТРОГО с `is_subscribed=false` + `raw_profile={"origin": ...}`.
  2. Telegram из GetCourse восстановить нельзя: поле «FunnelHub — ссылка перехода в новый Telegram-бот» пусто у всех пользователей; КАНАЛ заполнится сам при первом сообщении лиду боту.
  3. UI-маркер лидов без канала: серый бейдж `GC` в колонке КАНАЛ (inbox-app, `lead-channel-gc-badge`), условие — нет TG/VK identity и есть getcourse_user_id.
* **Доказательство (Evidence):**
  - `INSERT INTO messenger_identities ... is_subscribed=false` ➔ `INSERT 0 15`; итого vk_total 432 (414 subscribed / 18 not-subscribed).
  - Фильтры-разрешения подтверждены кодом: `vk_messaging.py:297`, `funnel_runner.py:260,271,514,536` — `MessengerIdentity.is_subscribed.is_(True)`.
  - `npm run build` (inbox-app) 2.50s exit 0; `verify.ps1 -Subproject funnel-hub` — 18 passed.
