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

