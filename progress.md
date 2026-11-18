# Session Progress Log: FunnelHub & Infrastructure Security

## Current Verified State

- **Repository root directory**: `C:\Users\circlealgorythm\Documents\Бот воронка`
- **Standard startup path**: `uv run uvicorn funnelhub.main:app --port 8000`
- **Standard verification path**: `pwsh -ExecutionPolicy Bypass -File scripts/verify.ps1 -Subproject funnel-hub` (или `uv run pytest`)
- **Active Feature**: Нет незакрытых фич; актуальная база кейсов — [`docs/lessons-local.md`](file:///./projects/funnel-hub/docs/lessons-local.md)
- **Current blocker**: Нет

---

## Сессионный журнал подпроекта

### Сессия: 2026-11-18 | Прогрессивное раскрытие памяти (тонкий AGENTS.md + lessons-local.md), ротация progress.md и архивация легаси Harness v1 (STD-033)
  1. **Progressive Disclosure (`AGENTS.md` + `docs/lessons-local.md`):** операционный роутер `AGENTS.md` сжат с `427` до `74` строк (`~27.1k -> ~3.0k` токенов); все локальные стандарты и SOP (`SOP-BACKUP-001`, `STD-DATA-*`, `STD-FUNNEL-*`, `STD-UI-*`, `STD-EMAIL-*`) с полными `Cue` и `Evidence` вынесены в On-Demand реестр `docs/lessons-local.md` (`360` строк, индексируется `query-harness.ps1`).
  2. **Ротация журнала и уборка легаси:** `progress.md` нормализован по секциям `### Сессия:` и сжат через исправленный `archive-docs.ps1` (`353 -> 84` строки до записи сессии, история сохранена в `archive/`); устаревшие файлы Harness v1 (`feature_list.json`, `session-handoff.md`) перемещены в `archive/legacy-v1/`; 4 ручных `.dump`-архива БД перенесены с побайтовой проверкой в `backups/manual-dumps/`.
  3. **Верификация (Evidence):** `verify.ps1 -Subproject funnel-hub` (`ruff`, `mypy` 54 файла, `pytest` 23 passed — exit 0), `query-harness.ps1 -Query "MultipleResultsFound" -Subproject funnel-hub` находит `STD-UI-002` в `docs/lessons-local.md` (score 150).

### Сессия: 2026-11-18 | Аудит возвращённого бэкапа Beget (`2026-10-19`) и восстановление недостающих лидов + Telegram-идентичностей (без рассылок)
  1. **Аудит `backup.tar` (`2026-10-19 11:55 МСК`):** извлечён и сверен с продом дамп `opt/funnelhub/backups/funnelhub_backup_20261019_030002.sql.gz` (`358` лидов за `2026-06-05`–`2026-10-18`, `56` TG-идентичностей, `488` `funnel_states`, `363` `email_subscriptions`, `9 731` сообщение). По решению пользователя рассылки и переписка не восстанавливались (`funnel_states`/`email_subscriptions`/`conversations`/`messages` не трогались).
  2. **Безопасное слияние по `SOP-BACKUP-001` (`dry-run` → pre-backup → `COMMIT`):** снят дамп прода `pre_beget1019_restore_20261118.dump` (`1 336 076` Б, `sha256=1d5be317...`, сервер + локально `tmp/backups/`). Исключены `4` тестовых и `1` пустая карточка; маппинг `st_match` с `rn_st = 1` (`STD-DATA-007`) устранил потерю `22` вторичных карточек (`skipped_collision_leads: 22→0`).
  3. **Результат в live-БД на Simplecloud:** добавлен `131` недостающий лид (`leads: 670→801`), дозаполнены пустые поля у `104` совпавших лидов, восстановлены `56` Telegram-идентичностей (`38` subscribed / `18` unsubscribed; `tg_idents: 10→66`, `idents: 443→499`), `+400` контактов (`210 email + 190 phone`), `+175` `lead_external_ids`, `+531` `lead_utm`, `+331` `lead_custom_fields`, `+595` `lead_consents`. `funnel_states=499`, `email_subscriptions=62`, `conversations=443`, `messages=1274` не изменились.
  4. **Пост-аудит дублей и склейка `8` пар (`801 → 793`):** сквозной проверкой по 10/9 цифрам телефона, email (полному и local-part до `@`) и полному ФИО выявлены и после `dry-run` объединены: `1` дубль из новой заливки (`Ирина`: `9052864751` + опечатка `@yandexry` → `148c17ca…`), `1` ВК+лендинг по ФИО (`Марина Хайруллина`: `vk_recovery` → `604165b5…`, `source = landing_consultation + vk`), `5` старых пар `landing_consultation` (`9xxxxxxxxx` без `7`) → `getcourse` (`79xxxxxxxxx`, с переносом `5/5` `bot_link_tokens`), `1` пара по домену (`Губанова`: `.com` оставлен вторичным `is_primary=false` на `f08e2de4…`). Итог БД: `leads=793`, `contacts=1120`, `idents=499` (`tg=66`), `bot_link_tokens=180`, `conversations=443`, `funnel_states=499`.
  5. **Верификация и гигиена (Evidence):** повторные прогоны `check_dupes_live.py` и `check_subtle_dupes.py` — `0` дублей по email/local-part и `0` реальных дублей по 10 цифрам телефона (кроме фейкового `9999999999`); 8 контейнеров Up, 0 ошибок в логах, `/health` → `200`, `/inbox/` → `200`; временные SQL-файлы с PII удалены с сервера и ПК.
### Сессия: 2026-11-18: изоляция Блога от анкеты, дедупликация Шаг 1 → Шаг 2, сортировка базы `GREATEST`, уведомления и оптимизация Docker/Caddy
  1. **Изоляция заявок из Блога (`webhooks.py`, `inbox_database.py`, `inbox-app/src/App.tsx`):** убрана подстановка `or "completed"` по умолчанию для `quiz_status`; в `extract_quiz_detail` добавлена проверка `lead_source` и защита от старых ответов при `draft` или пустом `completed`; секция «Анкета консультации» скрыта на вкладках «Блог»/«Мост ценностей» и у лидов из Блога без анкеты (`inbox-app/dist` пересобран).
  2. **Дедупликация Шаг 1 → Шаг 2 (`lead_post_submit_tasks.py`, `getcourse_webhook.py`):** в `enqueue_getcourse_consultation_submission` добавлена проверка 30-минутного окна по нормализованной сигнатуре контактов (отправка черновика в GetCourse на Шаге 1 сохранена, повтор на Шаге 2 с теми же контактами исключён, смена контактов в `pending`-задаче обновляет `payload`); добавлены дедупликация `LeadUtm`, сброс `is_primary` предыдущих контактов и защита от перезаписи `completed` запоздавшим `draft`.
  3. **Хронологическая сортировка без поломки импортов (`inbox_database.py`, `getcourse_api.py`, `webhooks.py`, `messenger.py`):** внедрена `apply_database_leads_ordering` через `func.greatest(coalesce(getcourse_created_at, created_at), max(landing.application.received), max(getcourse_consultation_submission))`; передано `preserve_updated_at=True` для enrichment и импорта CSV/XLSX; добавлена запись `landing.application.received` на живых точках приёма.
  4. **Уведомления (`lead_post_submit_tasks.py`, `lead_notifications.py`):** добавлена `resolve_application_is_new_lead` для корректной темы «Новая заявка» на Шаге 2 и вывод 4 ответов анкеты + фоллбэк поля `Форма` в тексте письма.
  5. **Docker/Caddy (`Dockerfile`, `docker-compose.prod.yml`, `Caddyfile`, `deploy_files.py`):** вынесен кэшируемый слой зависимостей, настроен единый образ `funnelhub:latest`, в `Caddyfile` добавлен `lb_try_duration 10s` / `lb_try_interval 250ms` против 502 на рестарте; добавлены 5 unit-тестов в `tests/test_blog_segmentation.py`.
### Сессия: 2026-11-16: бэкенд анкеты консультации, админка Inbox (секция №1) и баннер на странице «Спасибо»
  1. **Бэкенд FunnelHub (`src/funnelhub`):**
     - В `api/webhooks.py` (`AisuLandingApplicationRequest`) и `services/getcourse_webhook.py` добавлена поддержка полей анкеты (`quiz_status`, `quiz_messenger`, `quiz_known`, `quiz_goal`, `quiz_training`).
     - Сохранение в Postgres в `LeadCustomField` и `raw_getcourse_data` (JSONB) без деструктивных миграций.
     - Оповещение менеджеров в Telegram (@leadsaisubot) защищено: отправляется только по заполненным анкетам (`notify_admin = quiz_status != "draft"`). Фоновая синхронизация с GetCourse (`TASK_GETCOURSE_PROFILE_ENRICHMENT`, `TASK_GETCOURSE_CONSULTATION_SUBMISSION`) и рассылками сохранена для всех заявок.
     - В `api/inbox.py` и `services/inbox_database.py` структура `quiz` проброшена в API детальной карточки лида.
  2. **Админка FunnelHub (`inbox-app`):**
     - Секция «Анкета консультации» выведена на позицию №1 (над «Ссылки на ботов») и развернута по умолчанию (`defaultOpen={true}`).
     - Все остальные аккордеоны («Профиль GetCourse», «Источник и UTM», «Дополнительные поля», «Воронка» и т.д.) по умолчанию свернуты (`defaultOpen={false}`).
     - Реализован статус: зеленый бейдж `Анкета заполнена — целевой лид (звонить)` или серый `Анкета не заполнена (только контакты — не звонить)` + вывод строк со всеми 4 ответами.
  3. **Страница «Спасибо» (`api/messenger.py`):**
     - На странице `/join/{token}` сразу под заголовком добавлен заметный акцентный блок:
       *«Будьте на связи ближайшие дни, чтобы не пропустить вашу консультацию! Для дальнейшей коммуникации необходимо подписаться на чат-боты»*.
  4. **Верификация и боевой деплой (Evidence):**
     - Тесты `pytest tests/test_join_page.py tests/test_telegram_bot.py` пройдены на 100%.
     - Сборка фронтенда `inbox-app`: `tsc -b && vite build` (dist 292 kB JS, exit 0).
     - Деплой на VPS Beget через `deploy_files.py`: все 6 контейнеров собраны и запущены, Caddy reloaded, `/health` ➔ `{"status":"ok","service":"FunnelHub"}`, `/inbox/` ➔ HTTP 200 OK.
### Сессия: 2026-11-11: надёжный запуск Telegram-ботов по ссылкам из CRM, транзитный редирект и fallback по телефону (STD-FUNNEL-010)
  1. Выявлена первопричина ошибки при переходе по ссылке на бота из базы («Чтобы получить материалы, нажмите кнопку Telegram на странице после заявки»): при открытии прямых ссылок `t.me/bot?start=token` из встроенных браузеров мессенджеров (WhatsApp/VK WebView) или Telegram Web параметр `start` теряется (`command.args is None`), либо пользователь ранее уже открывал диалог с ботом и нажимал меню `/start` без параметров.
  2. В `services/bot_linking.py` добавлены функции построения надёжных ссылок `build_telegram_launch_link` (`/join/{token}/tg`), `build_most_telegram_launch_link` и парсер токенов `extract_bot_link_token` (из ссылок, текста или команд).
  3. В `api/messenger.py` добавлен транзитный маршрут `/join/{token}/tg` (`/join/{token}/telegram`), мгновенно инициирующий протокольный переход `tg://resolve?domain=...&start={token}` со страхующим редиректом на `t.me` и кнопкой ручного перехода при блокировке popup.
  4. В `api/inbox.py` список `bot_links` дополнен тремя точками входа: персональный транзитный запуск Telegram (`/join/{token}/tg`), VK (`/join/{token}/vk`) и веб-страница выдачи материалов (`/join/{token}`).
  5. В `telegram_bot.py` и `most_telegram_bot.py` вынесен хендлер `start_telegram_lead_with_token`, добавлен fallback по номеру телефона `link_telegram_lead_by_phone` (сопоставление с `lead_contacts`), кнопка `📱 Подтвердить заявку по номеру телефона` (Send Contact) при пустом `/start`, а также разбор токенов и номеров телефонов из обычных текстовых сообщений.
  6. Проверки: unit-тесты `test_telegram_bot.py`, `test_join_page.py`, `test_inbox_database.py` (27 passed), `ruff check .` и `mypy src/funnelhub` (54 файла) пройдены без ошибок, фронтенд `inbox-app` успешно собран (`npm run build`). В `AGENTS.md` зафиксирован стандарт STD-FUNNEL-010.
### Сессия: 2026-11-11: устранение таймаутов API экспорта GetCourse и защита от ошибки 903
  1. Выявлена первопричина отображения статуса 'new' вместо 'GC <id>' под именами недавних лидов (Дария, Надежда, Рамиля и др.) в CRM FunnelHub: фоновая задача getcourse_profile_enrichment опрашивала асинхронный экспорт GetCourse (/pl/api/account/users) всего 5 секунд (5 попыток по 1с), тогда как очередь GetCourse формирует файл за 15–45 секунд (error 909 'Файл еще не создан'). По истечении 5с задача падала с profile_not_found.
  2. В config.py и .env FunnelHub таймаут опроса увеличен до 60 секунд (GETCOURSE_API_POLL_ATTEMPTS=30, GETCOURSE_API_POLL_INTERVAL_SECONDS=2.0), контейнеры `app` и `funnel-worker` перезапущены на сервере Simplecloud.
  3. Проверено на лиде Дария: экспорт успешно завершился с первого раза, получен getcourse_user_id: 523808545, внешний ID getcourse: 523808545 записан в БД, статус в CRM обновлен на GC 523808545. Также обогащены Алла, Антонина, Наталья и две Татьяны.
  4. Зафиксирован лимит GetCourse Export API: 100 запросов за 2 часа (код ошибки 903 'Слишком много запросов'). Из-за прежнего зацикливания повторных попыток на 28 упавших лидах лимит был временно исчерпан; фоновый воркер с новыми таймаутами автоматически разберет оставшиеся лиды после сброса счетчика GetCourse.
  5. Проверки: uv run pytest tests/test_getcourse_api.py 8 passed; полный scripts/verify.ps1 -Subproject funnel-hub успешно пройден (ruff, mypy 54 files OK, 18 passed).

> [!NOTE]
> Предыдущие сессии и записи перенесены в архив: [Архив](archive/2026-11-18-033457-bbea96a3-progress.md)

---

## Поток синхронизаций (Recent Sync Stream)

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
- **2026-11-11 20:20** | fix(funnel-hub): increase getcourse export poll timeout to 60s and add rate limit protection
- **2026-11-11 21:00** | fix(funnel-hub): reliable telegram bot deep linking and phone fallback (STD-FUNNEL-010)
- **2026-11-16 19:23** | feat(funnel-hub): consultation quiz backend, join banner, inbox-app quiz section #1
- **2026-11-16 19:53** | fix(inbox): sort database leads by updated_at desc to bump repeat applications to top
- **2026-11-18 01:05** | fix(funnel-hub): blog quiz isolation, step1-2 dedupe, greatest ordering, email quiz answers and docker layer cache
- **2026-11-18 01:53** | ops(funnel-hub): restore 131 missing leads and 56 TG identities from Beget 2026-10-19 backup (no mailings); STD-DATA-007
- **2026-11-18 02:19** | ops(funnel-hub): merge 8 duplicate lead pairs (801->793) and verify 0 email/phone duplicates

- **2026-11-18 03:59** | docs(funnel-hub): progressive disclosure router split (AGENTS.md -> docs/lessons-local.md), progress rotation and v1 archive (STD-033)
