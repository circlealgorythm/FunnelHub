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
