# AGENTS.md - FunnelHub

> Карта проекта для AI coding agent по методологии Harness-engineering. Это оглавление, не энциклопедия. Детали - в `.harness/docs/`.

## 1. Методология

Проект ведется согласно Harness-engineering:

- repo is source of truth;
- WIP = 1;
- перед работой читать `.harness/init.md`;
- работа идет через Planner -> Implementer -> Verifier;
- в конце сессии обновлять `.harness/progress.md` и `.harness/session-handoff.md`;
- нельзя писать "done" без результатов применимой верификации;
- архитектурные решения фиксировать в `.harness/progress.md` в разделе Decisions.

## 2. Цель и домен

Сделать MVP серверной системы, которая принимает лидов из GetCourse webhook, хранит собственную базу, ведет Telegram/VK-ботов, email-рассылки и простой inbox, чтобы коммуникации не зависели от GetCourse.

Домен: кастомная автоворонка для онлайн-курсов.
Платформа: web.
Стек: Python 3.12+ + FastAPI + PostgreSQL + Redis + SQLAlchemy/Alembic + aiogram + VK API + Jinja2/HTMX.

## 3. Repo как source of truth

Все, что агенту нужно знать, должно быть в этом репозитории. Если знание не записано - для агента оно не существует.
Cold start test: новая сессия должна отвечать на 5 вопросов из `.harness/README.md` + `.harness/AGENTS.md` + `.harness/docs/`.

## 4. Команды верификации

Запускать одной строкой, когда соответствующая часть проекта уже создана:

- Lint: `ruff check .`
- Type check: `mypy src`
- Unit tests: `pytest -x`
- E2E smoke: `pytest tests/e2e -x`

## 5. Scope и WIP

- WIP = 1. В работе одновременно ровно одна фича.
- Текущая фича: <нет>.
- Источник истины по фичам - `.harness/feature-list.json`. Не редактируй параллельно.

## 6. Lifecycle

- Перед работой - прогон `.harness/init.md` (Bootstrap Contract).
- В конце сессии - обновить `.harness/progress.md` и собрать `.harness/session-handoff.md`.
- Каждое архитектурное решение писать в `.harness/progress.md` в раздел Decisions.

## 7. Архитектурное решение

GetCourse остается платформой для курсов, оплат, рассрочек, доступов, личного кабинета и временной ручной работы с лидами.

Наш сервер становится source of truth для коммуникаций:

- постоянная база лидов;
- Telegram/VK-боты;
- будущий Max channel adapter;
- email-рассылки;
- inbox для входящих сообщений;
- история касаний;
- статусы воронки;
- сегменты и аналитика.
- будущий knowledge/RAG слой для сценариев, переписок, документов, возражений и подсказок агенту.

Целевой поток:

```text
GetCourse form
-> GetCourse creates/updates user and issues login/password
-> GetCourse calls our webhook
-> Our server saves lead data, starts email logic, and generates bot-start token
-> User is redirected to the thank-you / bot choice page
-> Bot receives token and links messenger user to the saved lead
-> Custom server controls the sales funnel, email sequences, reminders, lessons, and analytics
```

Удаление некупившего пользователя из GetCourse не должно ломать Telegram/VK/Max/email-коммуникацию, если пользователь остается подписанным и разрешенным к коммуникации в нашей базе.

## 8. Функциональные границы MVP

В MVP нужны:

- GetCourse webhook с сохранением/обновлением лида;
- дедубликация по GetCourse ID, email и телефону;
- Telegram и VK deep links для привязки пользователя к лиду;
- x-дневная цепочка сообщений;
- email-рассылки из нашей базы через внешний email provider;
- мобильный inbox для просмотра входящих и ответа пользователю;
- импорт CSV/XLSX из GetCourse;
- ручные рассылки из админки;
- архитектурная готовность к автопостингу и Max.
- архитектурная готовность к будущему knowledge/RAG слою на PostgreSQL + pgvector.

## 9. Development Stack

- Python 3.12+, FastAPI, Pydantic v2, pydantic-settings.
- PostgreSQL, SQLAlchemy 2.x async, Alembic.
- Redis, RQ или Dramatiq для MVP.
- Telegram: aiogram 3.x.
- VK: VK API / Callback API через adapter layer.
- Max: позже как отдельный channel adapter.
- Email: provider API/SMTP через internal email adapter.
- Admin: FastAPI + Jinja2 + HTMX + Alpine.js where needed.
- Infrastructure: Ubuntu 22.04/24.04, Docker Compose, HTTPS, backups, log rotation.

## 10. Definition of Done

- Есть рабочий FastAPI backend.
- Настроена PostgreSQL-схема для лидов, каналов, email, сообщений и событий.
- GetCourse webhook сохраняет/обновляет лида с дедубликацией.
- Telegram и VK deep links привязывают пользователя к лиду.
- Работает базовая x-дневная цепочка сообщений.
- Email-рассылки идут из нашей базы через внешний email provider.
- Есть мобильный inbox для просмотра входящих и ответа пользователю.
- Есть импорт CSV/XLSX из GetCourse.
- Есть базовые тесты webhook, дедубликации, отправки и отписок.
- Проект запускается через Docker Compose.

## 11. Запрещено

- Не переносить курсы, оплаты, рассрочки и доступы из GetCourse.
- Не делать GetCourse источником правды для бота/email.
- Не хранить пароли GetCourse на нашем сервере.
- Не добавлять React в MVP без отдельного решения.
- Не усложнять inbox до полноценной CRM.
- Не использовать RAG как основной способ чтения структурированной операционной базы лидов; для лидов, контактов, согласий, статусов, сообщений и подписок использовать SQL, read-only tools, админские API, отчеты и фильтры.
- Не редактировать `.harness/feature-list.json` параллельно с другой фичей.

## 12. Известные риски

- Лимиты Telegram/VK на рассылки и ответы.
- Надежность webhook из GetCourse и дубли событий.
- Доставляемость email: SPF/DKIM/DMARC, отписки, спам-лимиты.
- Дедубликация лидов по GetCourse ID/email/телефону.
- Удаление лидов из GetCourse не должно ломать коммуникации с нашей стороны.
- Max подключать позже, если доступ к bot API будет подтвержден.
- Импорты CSV/XLSX из GetCourse могут содержать неполные или неодинаковые поля.
- Автопостинг из YouTube/Telegram/VK требует защиты от дублей и учета API-ограничений.

## 13. Anti-patterns

- Не строить большую CRM вместо простого inbox.
- Не делать жестко прошитую логику для каждого канала; использовать ядро воронки + channel adapters.
- Не хранить базу лидов только во внешнем email-сервисе.
- Не отправлять массовые письма напрямую через личный Gmail.
- Не смешивать временное хранение лидов в GetCourse с постоянной коммуникационной базой.

## 14. Режим работы

Multi-agent: Planner -> Implementer -> Verifier. Контракты ролей - в `.harness/tools.md`.

Если multi-agent режим недоступен, один агент обязан явно пройти те же роли.

## 15. Отчетность

- Никаких "done", пока не выведены результаты всех применимых команд верификации.
- Если команда верификации еще невозможна, явно написать почему.
- При остатке контекста <20% - запрещено закрывать фичу, только honest handoff.
- Каждое архитектурное решение писать в `.harness/progress.md` в раздел Decisions.

## 16. Implementation Roadmap

1. Server and base infrastructure.
2. Core data model and admin foundation.
3. GetCourse webhook integration.
4. Bot choice and messenger linking.
5. Funnel engine and first bot scenarios.
6. Email communication outside GetCourse.
7. Simple inbox for manual replies.
8. Import/export from GetCourse.
9. Manual broadcasts.
10. Knowledge/RAG layer for unstructured knowledge on PostgreSQL + pgvector.
11. Autoposting.
12. Stabilization and production hardening.
