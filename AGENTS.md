# Operating Manual: FunnelHub & Infrastructure Security Harness

> **Инвариант нулевого шага (`STD-020`):** Перед взятием любой задачи выполнить `git pull --autostash --rebase origin main` (или `python scripts/sync-ecosystem.py` в корне хаба). Запрещено редактировать код без предварительного `git pull`!  
> **Сквозные стандарты школы:** [`.harness/lessons.md`](file:///./.harness/lessons.md)  
> **Локальный журнал сессий:** [`progress.md`](file:///./projects/funnel-hub/progress.md)  
> **Детальная база локальных кейсов и SOP (On-Demand):** [`docs/lessons-local.md`](file:///./projects/funnel-hub/docs/lessons-local.md)

---

## 1. Контур и инфраструктура

- **Сервер продакшена:** VPS Simplecloud (`85.143.175.148`, домен `bot.aisukam.ru`, путь `/opt/funnelhub`).
- **Стек:** Python 3.12 (`uv`), FastAPI, PostgreSQL 16, Redis 7, Celery / воркеры, aiogram 3 (Telegram) + VK Callback API, React 19 + TypeScript (`inbox-app`), Caddy Reverse Proxy.
- **Контейнеры (`docker-compose.prod.yml`):** 8 сервисов (единый кэшируемый образ `funnelhub:latest`). На VPS вызывать строго `docker compose -f docker-compose.prod.yml ...`.
- **Двойное хранение секретов (`STD-022` / `STD-SEC-004`):** канонический локальный сейф — `C:\Users\circlealgorythm\Documents\Бот воронка\.env.recovery.template` (все ключи, gitignored). Любой новый/изменённый секрет на сервере зеркалируется в сейф и `.env` в ту же сессию; перед правкой боевого `.env` снимать `.env.bak_*` и проверять длины значений (`STD-024`).
- **Трёхъярусный бэкап БД (`SOP-BACKUP-002`):** `03:00` МСК cron Simplecloud (`backup-db.sh`, `pg_dump` ➔ `gzip` ➔ GPG AES256, ротация 7д) ➔ Reg.ru FTP `/backups/` (бессрочный архив) ➔ `17:00` МСК Windows Task `FunnelHub Backup Pull` (`scripts/backup-pull.ps1`, 7д ротация на ПК).

---

## 2. Команды разработки, проверки и эксплуатации

- **Стандартная верификация (обязательно перед сдачей):**
  ```powershell
  pwsh -ExecutionPolicy Bypass -File scripts/verify.ps1 -Subproject funnel-hub
  ```
  Запускает `ruff check .`, `mypy src/funnelhub`, быстрые unit-тесты и глубокие DB-тесты `scripts/verify-deep.ps1` через контейнер `fh-test-pg` с проверкой `$LASTEXITCODE` на каждом этапе (`STD-OPS-010`, `STD-FUNNEL-009`).
- **Сборка админки (`inbox-app`):** `npm run build --prefix inbox-app` (`tsc -b && vite build`).
- **Ручной деплой на прод (СТРОГО по отдельной явной команде пользователя после ревью):**
  ```powershell
  uv run python deploy_files.py
  ```
  После `docker compose up -d` приложение стартует ~30–60 с (Caddy поддерживает `lb_try_duration 10s`). Чистка кэша сборки на VPS: только `docker builder prune -af` — **никогда `--volumes`** (`SOP-OPS-003`).
- **Фиксация сессии и синхронизация с GitHub (по команде «в харнесс» / «фиксируй в харнесс»):**
  ```powershell
  pwsh -ExecutionPolicy Bypass -File scripts/sync-hub.ps1 -Subproject funnel-hub -Message "<type>(funnel-hub): <описание>"
  ```
- **Ручная отписка лида от email-рассылок (`SOP-EMAIL-001`):** `uv run python scripts/unsubscribe-lead.py --email <EMAIL>` (синхронно подавляет в Unisender Go, переводит подписку в `unsubscribed` и ставит `FunnelState` на паузу).

---

## 3. Жёсткие архитектурные инварианты

1. **Изоляция БД и совместимость (Zero-Regression):**
   - Порты `5432` (PostgreSQL) и `6379` (Redis) **никогда не публикуются** в `ports` `docker-compose.prod.yml` (`STD-002`); том `postgres_data` неприкосновенен.
   - Не ломать контракты вебхуков GetCourse (`/webhooks/getcourse`), форм сайтов и фоновых задач (`TASK_GETCOURSE_*`, `TASK_LEAD_APPLICATION_NOTIFICATION`).
2. **Боты Telegram/VK и сетевой прокси:**
   - Любой `aiogram.Bot` (основная воронка и «Мост ценностей») создаётся **строго через фабрику** `create_telegram_bot(token, settings)` с Cloudflare Worker proxy (`STD-FUNNEL-004`, `STD-FUNNEL-006`). Прямой `Bot(token=...)` запрещён; контракт таймаутов: `TELEGRAM_REQUEST_TIMEOUT` (90с) > `TELEGRAM_POLLING_TIMEOUT` (30с).
   - Отсутствие подписанной identity в шаге воронки вызывает `MessengerIdentityNotSubscribedError` ➔ graceful skip без ERROR-спама (`STD-FUNNEL-006`).
   - Секрет и код подтверждения VK брать строго из админки группы; при ручной проверке сверять длины; безопасный зонд — `text: "/stop"` (`STD-FUNNEL-007`). Автостарт VK физически возможен только по `message_allow` / `message_new` (`STD-FUNNEL-003`).
3. **Безопасность периметра и рассылок:**
   - В `get_request_ip()` доверять только **последнему IP** в `X-Forwarded-For` от Caddy; в `InMemoryRateLimiter` чистить устаревшие корзины при >500 ключах; для VK использовать `secrets.compare_digest` + проверку `group_id` (`STD-SEC-001`).
   - В экспорте CSV/XLSX экранировать формульные префиксы `sanitize_spreadsheet_cell()`, не искажая телефоны; в JWT хранить `jti` для отзыва при логауте (`STD-SEC-002`). В `Caddyfile` сохранять строгий `Content-Security-Policy` (`STD-SEC-003`).
   - Тестовые адреса (`is_test_email`, правило по `@gmail.com` для корней `algor...`) супрессируются в Unisender Go и исключаются из рассылок (`STD-EMAIL-002`).
4. **Сегментация, анкета консультации и UI Inbox:**
   - Фильтрация `exclude_source='most-tsennostey,blog'` идёт через `lead_exclude_source_filter` по `Lead.source` и `Event.source` (`STD-FUNNEL-001`, `STD-FUNNEL-002`).
   - Секция «Анкета консультации» — на позиции №1 в карточке лида (`defaultOpen={true}`), скрыта для Блога и Моста; дедуп Шаг 1 ➔ Шаг 2 в 30-минутном окне; сортировка базы — через `GREATEST(...)`, не сбивается при enrichment/импорте.
   - Запросы диалогов/лидов **не джойнят `messenger_identities` напрямую** (риск `MultipleResultsFound` при мульти-аккаунтах) — использовать скалярные подзапросы (`STD-UI-002`). Все входящие ответы (включая кнопки и непривязанных VK) уведомляют `@leadsaisubot`.
   - В колонке КАНАЛ выводить только реализованные каналы (`has_telegram`/`has_vk` без фильтра `is_subscribed`) или честный текст «нет подписок» (`STD-UI-001`).
5. **Воронки, GetCourse и массовые импорты/слияния БД:**
   - `/join/getcourse` работает с `require_secret=False` для браузера; воркер сабмита GC использует `follow_redirects=False` (`STD-FUNNEL-005`). Ссылка для TG из CRM идёт через транзитный `/join/{token}/tg` + fallback по телефону в ботах (`STD-FUNNEL-010`).
   - Таймаут опроса экспорта GetCourse ≥ 60с (`30 × 2с`), запрет параллельных запросов экспорта без паузы (`STD-027`).
   - `PERMANENT_DELIVERY_ERROR_MARKERS` держать префиксами без хвостовой точки (`STD-FUNNEL-009`).
   - Слияние/импорт лидов: приоритет `gc_id → vk → phone (10 digits) → email` (`STD-DATA-003`, `STD-DATA-007`), `dry-run` (`BEGIN…ROLLBACK`) + `pg_dump` до `COMMIT`, guard-ы от гонки с вебхуками и явный `gen_random_uuid()` для `lead_tags.id` (`STD-DATA-004`, `STD-DATA-006`), чужие VK-ID только `is_subscribed=false` (`STD-DATA-005`).
6. **Диагностика:** в `funnelhub-app-1` нет access-логов uvicorn — трафик проверять по БД и HTTP-зондам (`STD-FUNNEL-008`); внешние уведомления через Cloudflare Worker требуют явный User-Agent (`STD-OPS-011`).

---

## 4. Поиск деталей и прецедентов

Перед правкой нетривиальных зон (слияние дампов, ретраи воркеров, права VK/Telegram, бэкапы) ищи готовый разбор с `Evidence`:
```powershell
pwsh -ExecutionPolicy Bypass -File scripts/query-harness.ps1 -Query "<ключевые_слова>" -Subproject funnel-hub
```
Все развёрнутые SOP и истории кейсов хранятся в [`docs/lessons-local.md`](file:///./projects/funnel-hub/docs/lessons-local.md).
