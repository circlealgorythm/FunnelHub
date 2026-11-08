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
- [x] **Сессия 2026-11-08–09: проверка здоровья, резервирование и качество проверок:**
  1. Проверены VPS, контейнеры, HTTP, PostgreSQL и Redis; диагностические ошибки SQL идентифицированы как отдельные некорректные запросы.
  2. Исправлен запуск выгрузки бэкапов на ПК: UTF-8 BOM для Windows PowerShell и прямое действие планировщика с передачей exit code; копии сервера, FTP и ПК совпали по SHA-256. Планировщик проверен вручную, следующая выгрузка в 17:00.
  3. Развернут внутренний мониторинг с Telegram-оповещениями и проверками контейнеров, БД, Redis, HTTP, диска, серверного и FTP бэкапов; cron каждые 5 минут. Telegram принял тестовое уведомление, cron 09.11 00:30:01 — 0 проблем.
  4. Введена еженедельная проверка восстановления в изолированный временный контейнер (воскресенье 05:00 МСК); контрольный запуск восстановил 624 лида и 432 состояния, временный контейнер удалён.
  5. Устранены 15 замечаний Ruff в скриптах импорта и исправлена передача ошибок всех четырёх этапов проверки FunnelHub. Evidence: до исправления линтер возвращал ошибку, а verify — 0; после — verify 1, имитация сбоев каждого этапа — 17, полный verify — 0: ruff/mypy OK, 18 passed, deep 52 passed/4 skipped.
  6. Осталось: независимый внешний мониторинг полного отказа VPS и сквозная проверка воронок на согласованном тестовом аккаунте; установленный VPS-монитор не может уведомить при отключении самого VPS.
- [x] **`OPS-DR-001` (Beget DR закрыт: доаварийный дамп расшифрован, воронки подтверждены бесшовными, восстановлен последний пробел; бэкап-цепочка за сегодня проверена)** (passing, 2026-11-07):
  - **Бэкап-контур за сегодня (3 яруса):** дамп `funnelhub_backup_20261107_030002.sql.gz.gpg` (319 812 Б) — сервер (cron `/etc/cron.d/funnelhub-backup`, 03:00) + FTP Reg.ru `backups/` + ПК (pull-задача 17:00); sha256 трёх копий совпали байт-в-байт (`c6bd2f3f…`); расшифровка сегодняшнего дампа успешна (620 лидов, 423 fs, метки до 07.11 06:00). Нюанс: бэкап-FTP аккаунт = `BACKUP_FTP_*` (корень = FTP основного сайта aisukam.ru + каталог `backups/`), `FTP_MOST_*` — отдельный сайт-аккаунт, бэкапов там нет.
  - **Драматургия восстановления:** доаварийный дамп Beget 06.11 03:00 (наш backup-контур, выложенный ДО аварии) расшифрован ключом из сейфа (STD-022 — сработал ровно для этого сценария) → доказано, что Simplecloud-база поднималась из НЕГО (495/504 UUID лидов, 416/417 fs/identities) → **воронки продолжили сами**: 13 active-состояний с Beget остались active, шаги с `next_run_at=07.11 06:00` (day_03/05/06/14/15) ушли ровно по расписанию уже с нового сервера — разрыв для пользователей невидим; окно простоя потерь шагов не создало (воркеры были мертвы — нечего было пропускать).
  - **«9 пропавших лидов» разрешены:** 417 из 504 лидов дампа — синтетические заготовки `vk_recovery` (скрипт восстановления VK на Beget); 8 из 9 «пропавших» — дубли людей, уже восстановленных GC-импортом как «landing_consultation + vk» (телефоны совпали 1-в-1); **восстановлен 1 реальный** (vk_recovery 2026-06-18, VK 299125798 subscribed, fs completed day_18, диалог): сухой прогон BEGIN→ROLLBACK → COMMIT; пост: leads 621→622, fs 417/417, identities 417/417, 0 рассылок (state completed). Урок **STD-DATA-006** в `AGENTS.md`.
  - **Unisender:** восстанавливать нечего — `email_subscriptions` пуста даже в доаварийном дампе (email-воронка неактивна), состояние контактов живёт в Unisender Go (внешний SaaS, от Beget не зависел). Расшифрованные дампы с PII из `tmp/beget-recovery` удалены.

- [x] **`OPS-MOST-001` (Health-check «Моста ценностей»: устранены 2 разрыва — приём заявок с сайта и VK-колбэк)** (passing, 2026-11-07):
  - Контейнеры/боты GREEN: most-telegram-bot / most-vk-funnel-worker / most-funnel-worker — 0 рестартов, 0 ошибок, проходы чистые; TG-поллинг через CF-прокси (таймауты ~5-6/час — системика прокси, у основного бота 140/24ч, self-heal за 1 попытку — не баг).
  - **Разрыв №1 (критичный):** токен в FTP `config.php` хостинга most.aisukam.ru — 43 символа против серверного 64 (`MOST_TSENNOSTEY_INGEST_TOKEN`) → каждая заявка с формы отбивалась 401 молча; в БД 0 лидов `most-tsennostey` за всё время, вкладка «Мост ценностей» пуста. Исправлено: залит серверный токен (бэкап старого ТОЛЬКО локально — .bak в web root хостинга отдаётся как plain text, доказано пробой .txt → 200 с содержимым); локальное зеркало живого конфига = `projects/landing-most/php-hosting/config.php` (gitignored). Верификация: повторное скачивание — совпадение байт; зонд с правильным Bearer на `/webhooks/landing-applications/most-tsennostey` → 422 (валидация Pydantic, НЕ 401 — приём восстановлен, лид не создаётся).
  - **Разрыв №2 (VK-колбэк):** `MOST_VK_CONFIRMATION_CODE` пуст (рукопожатие → 503) и серверный secret 32 симв. ≠ секрету VK-админки 14 симв. (все message_new отбивались бы 403). Синхронизированы из VK-админки в 3 места: сервер `/opt/funnelhub/.env` (бэкап `.env.bak_mostvk_20261107`) + локальный `.env` + `.env.recovery.template` (STD-022). Верификация: handshake `/webhooks/most-vk` c group_id 240711612 → `65d51d4d` (=админке); wrong secret → 403; real secret + `/stop` → ok (без побочек); VK-баннер «Адрес сервера успешно сохранён»; школьный VK MATCH (не задет). Уроки **STD-FUNNEL-007/008** в `AGENTS.md`.
  - Живой тест 2026-11-07 (подтверждён пользователем вручную): заявка с most.aisukam.ru → лид во вкладке «Мост ценностей» + кнопки TG/VK; сообщение в VK-группе → диалог + уведомление @leadsaisubot.

- [x] **`OPS-NOTIFY-001` (Контур уведомлений @leadsaisubot + фикс 500 в Inbox + ротация ключа GC)** (passing, 2026-11-07):
  - **Диагностика заявки Айсу (тест вторым VK-аккаунтом):** лид «Ксения» создан ещё 06.11 18:55 (GC 514368053); вебхук 07.11 04:59:52 смэтчил его (дедуп — новой строки в Базе нет, это штатно). «Привет» 05:00–05:01 от нового VK-аккаунта потеряны: аккаунт не был привязан (STD-FUNNEL-003: привязка только через one-tap кнопку/токен); в 05:04:06 привязка сработала → welcome мгновенно. Задержка «4 минуты» = момент нажатия кнопки привязки, не доставка.
  - **Фикс 500 Inbox:** `MultipleResultsFound` в `get_inbox_conversation_detail` — outerjoin по identities размножал строку при двух VK-аккаунтах лида (карточка дублировалась + 500 при открытии детали). Заменён на скалярные подзапросы (created_at DESC LIMIT 1). Коммит `9a28452`. Регресс-тест RED→GREEN; test_inbox.py 7/7.
  - **Уведомления оператору восстановлены как до переезда:** авто-обработанные ответы кнопок теперь тоже уведомляют @leadsaisubot (telegram_bot, vk_bot, most_telegram_bot, most_vk_bot — раньше `elif` пропускал уведомление в ветке handled, коммит `6ac6ba0` + `0d7f975`); сообщения VK от непривязанных пользователей (написали в группу напрямую) уходят оператору с vk_id и текстом через новый `notify_admin_about_unbound_messenger_message` (диалог в Inbox по-прежнему не создаётся — STD-FUNNEL-003). Урок **STD-UI-002** в `AGENTS.md`.
  - **Ротация GETCOURSE_API_KEY (ключ предоставлен пользователем):** новый проверен с сервера (`success:true`, HTTP 200) → обновлён `/opt/funnelhub/.env` (бэкап `.env.bak_gc_key_20261107`) + локально `.env` и `.env.recovery.template` (STD-022/SEC-004, зеркально); временные файлы удалены. После деплоя: GC API из боевого контура `success:true`. Старый ключ — отозвать пользователю в админке GC.
  - Деплой exit 0 (двойной: `9a28452`+`6ac6ba0`, затем `0d7f975`); прод-верификация: 8 контейнеров Up, рестартов 0, most-бот поллит через прокси, funnel-worker 0 ошибок, inbox 200.

- [x] **`OPS-HEALTH-001` (Полный health-check перед рекламной кампанией + фикс most-ботов и funnel_runner)** (passing, 2026-11-07):
  - Health-check по ярусам: железо (load 0.16, диск 19%, RAM 2.2ГБ своб.), 8 контейнеров, Caddy/HTTPS (серт до 03.02.2027), 5xx=0, app-ошибок 0, inbox 200, guard вебхука строгий (403 без секрета), БД 620 лидов / 421 диалог, funnel_states 18 active, GC API жив после тарифной блокировки (`success:true`), бэкапы 3 ярусов (сервер 03:00, FTP, ПК-тяга 21:53 06.11).
  - E2E-заявка через боевой вебхук (`test-webhook@aisukam.ru`): POST `/webhooks/getcourse` → HTTP 200 → матчинг лида → event `getcourse.webhook.received` → задача enrichment поставлена → воркер обработал. Уведомления о заявках 5/5 completed за 24ч; реальные диалоги TG (6 in/19 out) и VK (5 in/54 out) за 48ч.
  - **Найдено:** (1) most-telegram-bot — крэш-луп 248 рестартов: сырой `Bot(token=...)` без Cloudflare-прокси (на Simplecloud api.telegram.org заблокирован; сломано при переезде); most-funnel-worker — та же проблема, молча терял TG-отправки. (2) 547 ERROR/24ч в funnel-worker от одного funnel_state (blog-лид 02.11 без подписанной TG-identity): шаг channel="messenger" без identity поднимал ValueError каждый проход раннера.
  - **Фиксы (команда пользователя «выкатывай»):** оба most-сервиса переведены на `create_telegram_bot(settings)`; в funnel_runner введён `MessengerIdentityNotSubscribedError` → graceful skip (rollback, WARNING, state active). Коммит `b580395`, деплой `deploy_files.py` exit 0, прод-верификация: most-бот `Run polling @most_cannostei_bot` через прокси, restarts=0; funnel-worker Skipping=1 (WARNING) / Failed=0 (было 547). Урок **STD-FUNNEL-006** в `AGENTS.md`.
  - Тесты: новый skip-тест + обновлены `records_failed` (FailingTelegramBot) и `continues_after`; 3 passed (fh-test-pg), mypy 54 OK; 2 email-падения доказаны pre-existing через git stash (дрейф PUBLIC_BASE_URL).

- [x] **`DATA-002` (Массовый импорт пользователей GetCourse в базу лидов через API: 1188 пользователей, 823 новых лида)** (passing):
  - Найден и подтверждён рабочий ключ `GETCOURSE_API_KEY` (`.env.recovery.template`, проверка 2026-11-05); выяснены фильтры API: полная выгрузка = `created_at[from]/[to]` (без фильтра error_code 908), группы = `idgrouplist=id_date`.
  - Выгружены и распарсены все 1188 пользователей GC (export 90643107) + членство в группах (export 90643875, 794 связки, 17 групп). Установлено: JSON API приходит чистым UTF-8 — консольный mojibake является артефактом отображения (см. `.harness/lessons.md` STD-023), перекодировки запрещены.
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

> [!NOTE]
> Задачи за октябрь 2026 года (UI-001..010, SEC-001..009 на Beget VPS) перемещены в архив: [Архив 2026-10](archive/2026-10-progress.md)

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

- **2026-11-06 23:1x** | fix(funnel-hub): 403-луп getcourse_consultation_submission устранён — воркер не открывает финальный редирект GC на /join/getcourse (follow_redirects=False, httpx raise_for_status только при is_error); GET /join/getcourse переведён на require_secret=False (секрет опционален, rate-limit остаётся, вебхук строго) — реальный лид после GC-формы снова видит join-страницу вместо 403. STD-FUNNEL-005. RED→GREEN на локальном postgres 16 (docker fh-test-pg); FIX A + тесты A/B попали в чужой коммит ef98e57 (гонка с параллельной сессией чистки max-диалогов), FIX B (ingestion_guard.py + messenger.py) — отдельным коммитом; 10 падений DB-тестов доказаны pre-existing на чистом дереве (сеть VK API, прод-PUBLIC_BASE_URL в локальном .env, дрейф тестов)

### Сессия 2026-11-06 (вечер) | Диагностика тестового лида + STD-FUNNEL-005 (403-луп и join-страница) — пакетная фиксация
1. **Диагностика «тестовый лид не пришёл в базу, диалога нет в Inbox»:** лид «Чупупуньк Петрович» найден в БД (`f4624357`, 2026-11-02, source `https://aisukam.ru/blog/` — сырой URL из MIG-004-восстановления CRM), сегодня слинкован с GC (id 457323000), TG-identity создана 22:09:44 МСК по токену, воронка активна (restart_reason=bot_start), 5 сообщений ушли. Невидимость объяснена: поиск «Чу**б**упуньк» с опечаткой; во вкладке «Блог» лида нет (source ≠ `blog`); в «Общей базе» задавлен 624 GC-лидами импорта. Диалог в Inbox появляется только после первого ВХОДЯЩЕГО сообщения лида (исходящие воронки до этого пишутся с conversation_id=NULL и подтягиваются при первом ответе) — **UX-решение пользователя: оставить как есть** («в диалогах нужны только те, кто написал»).
2. **FIX A:** устранён вечный 403-луп post-submit задачи `getcourse_consultation_submission` — воркер открывал всю цепочку редиректов GC до `/join/getcourse` без секрета (403) и до 5 раз повторно слал форму в GC (дубли). `GetCourseConsultationFormClient`: POST с `follow_redirects=False`, 302 = успех; httpx `raise_for_status` только при `is_error` (бросает и на 3xx). Тест RED→GREEN (`test_consultation_form_client_does_not_follow_funnelhub_redirect`). Коммит: попал в `ef98e57` (гонка с параллельной сессией чистки max-диалогов, уже в origin).
3. **FIX B:** GET `/join/getcourse` переведён на `require_secret=False` в guard (`ingestion_guard.py`, default `true` везде) — легитимный вызывающий страницы это браузер лида после редиректа GC, секрет ему неоткуда передать. Вебхук `/webhooks/getcourse` остался строгим, неверный секрет = 403, rate-limit 120/min сохранён. Тесты RED→GREEN: `test_join_getcourse_renders_join_page_without_secret` (403→200+join-страница), `test_join_getcourse_rejects_invalid_secret`, `test_getcourse_webhook_rejects_missing_secret_in_required_mode`. Коммит `539ea9b` (push).
4. **Тестовая инфраструктура:** DB-тесты впервые запущены локально — поднят disposable postgres 16 в docker (`fh-test-pg`, 127.0.0.1:5432); 10 падений всех доказаны pre-existing на чистом дереве (4×vk_callback — сеть VK API, 2×join_page — прод-PUBLIC_BASE_URL из локального .env, 4×webhook/enrich — дрейф тестов от эволюции кода/ENV). `verify.ps1 -Subproject funnel-hub`: 18 passed, mypy 54 файлов OK (15 ruff-ошибок в `scripts/getcourse-import/` — legacy, не гейтится).
5. **STD-FUNNEL-005** записан в локальный AGENTS.md (сигнал/причина/стандарт/Evidence RED→GREEN).
6. **Деплой на Simplecloud** (по явной команде пользователя): `deploy_files.py` exit 0, все 6 app-контейнеров Up, alembic чисто. Боевые пробы: `/join/getcourse` без секрета **403→400** (guard прошёл), неверный секрет **403**, `/webhooks/getcourse` без секрета **403**, `/inbox/` **200**. Транзиентный 502 после reload Caddy самоустранился (uvicorn стартовал).

- **2026-11-06 23:25** | fix(funnel-hub): STD-FUNNEL-005 — 403-луп getcourse_consultation_submission устранён, join/getcourse guard ослаблен для браузерного редиректа GC (вебхук строго); деплой на Simplecloud, пробы 403→400/403/403/200

- **2026-11-07** | ops(funnel-hub): профилактика docker build cache на Simplecloud — builder prune освободил 2.4 ГБ (9.3G→6.9G used), тома БД/образы/контейнеры не тронуты; SOP-OPS-003 в AGENTS.md (повторять раз в 1–2 месяца, --volumes запрещён)

- **2026-11-07 00:24** | ops(funnel-hub): SOP-OPS-003 — профилактика docker build cache на Simplecloud, builder prune освободил 2.4 ГБ (тома БД не тронуты)

- **2026-11-07 05:04** | fix(funnel-hub): STD-FUNNEL-006 — most-боты через Cloudflare-прокси (крэш-луп 248 устранён), graceful skip funnel_runner без identity (547 ERROR/24ч -> 0), health-check перед рекламой OPS-HEALTH-001

- **2026-11-07 05:48** | fix(funnel-hub): STD-UI-002 — фикс 500 Inbox при двух identity, уведомления @leadsaisubot восстановлены (кнопки+непривязанные VK+обе воронки), ротация GETCOURSE_API_KEY

- **2026-11-07 17:30** | ops(funnel-hub): OPS-MOST-001 — health-check «Моста ценностей»: восстановлен приём заявок с most.aisukam.ru (токен config.php 43→64 симв.) и VK-колбэк Моста (код+секрет синхронизированы с VK-админкой, handshake 65d51d4d); STD-FUNNEL-007/008 в AGENTS.md

- **2026-11-07 17:30** | ops(funnel-hub): OPS-MOST-001 — health-check Моста: приём заявок восстановлен (токен config.php 43→64), VK-колбэк Моста синхронизирован с VK-админкой; STD-FUNNEL-007/008

- **2026-11-07 18:40** | ops(funnel-hub): OPS-DR-001 — Beget DR закрыт: доаварийный дамп 03:00 расшифрован, бесшовность воронок доказана по расписанию (day_03/05/06/14/15 ушли в 06:00 07.11), восстановлен последний пробел (vk_recovery июньский, dry-run→commit, fs 417/417); бэкап-цепочка за сегодня проверена по sha256; STD-DATA-006 в AGENTS.md

- **2026-11-07 21:06** | ops(funnel-hub): OPS-DR-001 — Beget DR закрыт: доаварийный дамп расшифрован, бесшовность воронок доказана, восстановлен последний пробел (fs 417/417); бэкап-цепочка проверена по sha256; STD-DATA-006

- **2026-11-08 19:10** | ops(funnel-hub): server health check — all 8 containers Up, HTTP 200, DB growing (638 leads), backups Nov 7+8 on FTP, PC pull ran on schedule 17:00; found email-funnel retry storm (4578 err/day: 4 bounced-lead states retried forever)
- **2026-11-08 19:20** | ops(funnel-hub): paused 4 stuck email funnel states (UPDATE 4, reversible, metadata paused_by=ops_manual_2026-11-08); storm stopped — 0 errors in 4 min
- **2026-11-08 19:30** | fix(funnel-hub): FUNNEL-EMAIL-001 marker drift — PERMANENT_DELIVERY_ERROR_MARKERS had old message text, real message gained "(or is test account)" suffix (STD-EMAIL-002) -> no pause, infinite retry; TDD RED->GREEN via existing test pauses_email_step_without_subscription; marker substring fixed; 14 passed (1 pre-existing failure test_run_due_funnel_once_resolves_email_bot_buttons vk_url drift, unrelated — proven via git stash); ruff+mypy clean; deploy pending user command

- **2026-11-08 18:38** | fix(funnel-hub): FUNNEL-EMAIL-001 marker drift broke email-funnel pause classification (4.5k err/day retry storm); 4 stuck states paused ops-manually; TDD RED->GREEN

- **2026-11-08 19:45** | deploy(funnel-hub): FUNNEL-EMAIL-001 fix deployed via deploy_files.py (exit 0, 6 app-контейнеров recreated, alembic clean); маркер подтверждён в живом контейнере, /health 200, шторм не возобновился
- **2026-11-08 20:00** | test(funnel-hub): исправлены 2 устаревших теста (buttons vk_url -> ожидание по public_base_url — прод-код прав, тест отстал; engine metadata + calendar_day_offset/funnel_started_at) и флак ORDER BY created_at при равных таймстампах одной транзакции -> сравнение мультимножеством; глубокий набор 52 passed
- **2026-11-08 20:05** | ops(harness): глубокие DB-тесты встроены в гейт verify (scripts/verify-deep.ps1 + verifyCmd в hub-manifest; SKIP на машинах без Docker/fh-test-pg); урок STD-FUNNEL-009 зарегистрирован в AGENTS.md

- **2026-11-08 19:00** | test(funnel-hub): fix 2 stale tests + ORDER BY tie flake, wire deep DB tests into verify gate (STD-FUNNEL-009); FUNNEL-EMAIL-001 deploy verified live

- **2026-11-08 21:00** | feat(funnel-hub): TELEGRAM-B-001 — вариант Б поллинга: polling_timeout 10->30 через TELEGRAM_POLLING_TIMEOUT (втрое меньше getUpdates-раундтрипов через CF-прокси, задержка доставки не растёт), явный aiohttp request timeout 90s (TELEGRAM_REQUEST_TIMEOUT) в create_telegram_bot; .env.example задокументирован; тесты фабрики 7 passed; контракт: request_timeout > polling_timeout
- **2026-11-08 21:05** | ops(test-infra): эпизод Exited(255) fh-test-pg (сбой Docker Desktop/WSL, не postgres) -> 30 ERROR в гейте; контейнер перезапущен, verify 18+52 GREEN; verify-deep честно падает на мёртвом Docker вместо тихого пропуска

- **2026-11-08 19:18** | feat(funnel-hub): TELEGRAM-B-001 polling tuning 10->30s + aiohttp timeout 90s (option B, STD-FUNNEL-004 residual CF timeouts)

- **2026-11-08 21:40** | deploy(funnel-hub): TELEGRAM-B-001 выкачен на прод (deploy_files.py exit 0, 6 app-контейнеров recreated); poll=30/req=90.0 подтверждены docker exec в обоих живых ботах, Start polling, 0 таймаутов с деплоя; /health+/inbox/ 200 после стартового окна (~60с 502 — паттерн STD-UI-002); контрольный замер таймаутов за 24ч (цель <100/сутки на бота против ~290) — при следующей сессии; STD-FUNNEL-004 калибровка обновлена (п.4-5)

- **2026-11-08 19:28** | docs(funnel-hub): harness fixation - TELEGRAM-B-001 deploy verified live, STD-FUNNEL-004 calibration updated to option B

- **2026-11-08 19:29** | docs(funnel-hub): STD-FUNNEL-004 calibration updated to option B (poll 30s settings-driven, request 90s contract)

- **2026-11-09 00:57** | ops(funnel-hub): secure backup monitoring and verification checks
