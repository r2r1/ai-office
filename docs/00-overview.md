# AI-Office — сводная архитектура (все слои, один файл)

*Написан заново по состоянию кода на 2026-07-08, а не по старым `docs/*.md` —
часть из них (`arhitecture.md`, `SAAS_ARCHITECTURE.md`, `новый_аудит_архитектуры.md`,
безымянные `1.md`/`2.md`/`3.md`) описывают реализацию, которая с тех пор изменилась,
и не пересобирались вместе с кодом. Этот файл — единственный источник правды
верхнего уровня; при расхождении с любым другим `docs/*.md`, кроме исключений
ниже, верить этому файлу и перепроверять код.*

*Что остаётся отдельными файлами и почему: `bos-architecture.md` — глубокая
спецификация домена (глоссарий, инварианты, mapping-таблица по каждому модулю,
обновлена 2026-07-08) — раздел 3 здесь её конспектирует, а не дублирует;
`engineering-principles.md` — правила с разбором конкретных инцидентов, раздел 7
здесь даёт компакт-список без потери ссылки на первоисточник.*

---

## 1. Vision — зачем существует продукт

**AI-Office — Business Operating System (BOS): не набор AI-агентов и не
конструктор сайтов, а операционная система бизнеса**, которая непрерывно
сравнивает желаемое состояние компании с текущим и сама выполняет работу,
которая сокращает разрыв.

Цифровой офис — CEO, отделы, персонажи, изометрическая визуализация — это
**проекция** ядра, не само ядро. Тест архитектуры (из `bos-architecture.md` §0):
уберите через 5 лет офис, столы и персонажей — ядро (World Model, Objectives,
Gap, Plan, Decision, Acceptance) должно остаться таким же сильным. Второй тест:
завтра LLM исчезнут — переписать придётся только Providers (`core/llm.py`,
`integrations/*`), а не World Model, планы, решения, историю.

Что подтверждено кодом, а не только декларацией:
- **Автономность как архитектурное решение, не лозунг.** Онбординг
  (`src/agents/onboarding.py::build_brief_structured`) детерминирован — работает
  без единого вызова LLM, значит офис стартует даже при нулевом балансе
  провайдера. Первый LLM-вызов — только в `loop.py` BOOTSTRAP.
- **Приоритет владельца встроен в память, а не в промпт-этикет** —
  `office/memory.py::all_entries()` подмешивается в контекст каждого работника
  и CEO с более высоким приоритетом, чем стратегия/ТЗ (`prompt_builder.py`).
- **Реальный результат, не пересказ** — `office/acceptance.py` физически не
  даёт задаче закрыться на «сдал непустую строку»: обязателен build/functional
  контроль (см. §3, §6).

Долгосрочное видение и «зачем это миру» подробнее разобраны в
`docs/product-vision.md` §0 (продано не «агенты», а измеримое понимание
бизнеса клиента) — тот документ актуален и не нуждался в переписывании.

---

## 2. Product — что видит пользователь

**Жизненный цикл клиента** (проверено по `server.py` + `webapp/src/app/`):

```
лендинг (LandingView.tsx)
  → авторизация: GitHub OAuth device-flow ИЛИ dev-login (auth/dev-login)
  → онбординг: 3 сценария (ScenarioView.tsx → OnboardingFlow.tsx)
       "business" (есть бизнес) | "launch" (открываю компанию) | "idea" (есть идея)
       — 5 одинаковых по форме измерений на любой сценарий:
         product→niche, client→audience, revenue→assets/budget_usd/avg_check_usd,
         goal→research_question (детерминированный), constraints (+ company_scan URL)
  → бриф готов (build_brief_structured — regex/string-конкатенация, БЕЗ LLM)
  → офис-цикл стартует (BOOTSTRAP → циклы CEO, см. §3)
  → результат: лендинг/бот/код в workspace + лиды + отчёты
```

**Вкладки продукта** (`webapp/src/app/views/*.tsx`, реальные файлы):

| Вкладка | Файл | Что показывает |
|---|---|---|
| Дашборд | `DashboardView.tsx` | основной вид рабочего пространства (сегодня — не 3D-офис по умолчанию) |
| Изо-офис | `components/OfficeView.tsx` | изометрическая сцена (проекция, см. §1) |
| Проект | `ProjectView.tsx` (982 строки) | параллельные проекты, граф задач, спецификации приёмки |
| Команда | `TeamView.tsx` | оргструктура: отделы, лидеры, наём |
| Компания | `CompanyView.tsx` (687 строк) | 8 под-вкладок: профиль/цели/роли/скиллы/лимиты/хранилище/доступ |
| Чаты | `ChatsView.tsx` | личные чаты + лента сообщений в реальном времени |
| Лиды | `LeadsView.tsx` | CRM-вид заявок с форм лендингов |
| Доступы | `ConnectionsView.tsx` | сохранённые интеграции |
| Код | `FileExplorer.tsx` | дерево файлов workspace, превью, терминал |
| Бизнес | `BusinessDashboard.tsx` | KPI, health-индекс, разрыв до цели |
| Сценарий | `ScenarioView.tsx` | выбор онбординг-сценария |
| Аккаунт | `AccountView.tsx` | настройки пользователя |

Общие компоненты: `TopBar.tsx` (статус + расход), `NavRail.tsx` (левая навигация),
`RightPanel.tsx`/`AgentDetailModal.tsx` (карточка агента и его сдачи),
`ModelPicker.tsx` (выбор LLM), `data/roles.ts` (имена/иконки/описания ролей —
единственный источник истины для UI, см. правило в `CLAUDE.md` §3.10).

**Публичная поверхность** (не требует авторизации): `GET /site/{tenant}/{slug}`
— опубликованный лендинг, `POST /api/lead/{tenant}/{slug}` — форма лида
(rate-limited), `POST /api/site-lead` — лид с multi-file сайта (тенант/слаг
резолвится по Referer).

---

## 3. Business Architecture — как устроена компания внутри системы

Полная спецификация — `docs/bos-architecture.md` (глоссарий, инварианты,
таблица mapping по каждому модулю; обновлена 2026-07-08, сверена с кодом).
Конспект кибернетического цикла:

```
Objectives (desired, measured_by)
        ↓
Gap Analysis (office/gap.py::compute) ←── Business State (office/world.py::snapshot)
        ↓
Planning Engine (office/planning_engine.py) — Work, не голая задача
        ↓
Decision (office/decision_engine.py — PlanDiff, прошедший Sandbox office/sandbox.py)
        ↓
Execution (office/execution_policy.py → Worker)
        ↓
Acceptance (office/acceptance.py — 5 уровней, см. §6)
        ↓
Measurement → обратно в Gap Analysis
```

Ключевое из спецификации, что нужно держать в голове при любой правке бизнес-логики:
- **Work — не всегда Project.** `office/projects.py::create(type=...)` порождает
  `project` (разовое, лимит параллельности), `process` (никогда не завершается,
  `office/process_instances.py` — обобщение `leads.py`) или `initiative`
  (идея до решения, `office/initiatives.py`).
- **Владелец не получает отказ — получает цену выбора.** Конфликт intent с
  Objectives не молча саботируется — CEO показывает варианты.
- **Constitution — вето только по безопасности** (`office/constitution.py`),
  бизнес-решения всегда за владельцем.

---

## 4. Domain Model — сущности предметной области

Не код, а понятия, которыми оперирует вся система (полные определения —
`bos-architecture.md` §1; здесь — сущность → где живёт → реальные поля):

| Сущность | Модуль | Ключевые поля (по коду) |
|---|---|---|
| **Objective** | `office/objectives.py` | `id, title, measured_by, current, desired, project_id(опц.)` — пустой `measured_by` = не участвует в Gap |
| **Gap** | `office/gap.py::compute()` | `{objective, current, desired, gap, met}` — вычислимо, не «ощущение CEO» |
| **Work / Project** | `office/projects.py` | `id, title, goal, type(project\|process\|initiative), status, owner` |
| **Stage (Milestone)** | `office/milestones.py` | привязан к `project_id`; для Process — определение шага конвейера, не прогресс |
| **Instance** | `office/process_instances.py` | `process_id, stage, history[]` — обобщение лида (`leads.json`) |
| **Task** | `office/plan.py` | `id, role, deps, done_criterion, parent_id(вложенность), status, attempts, acceptance` |
| **Decision** | `office/decision_engine.py` | `PlanDiff {add_tasks, milestone_ops, remove_tasks, dept_ops}` + вердикт Sandbox |
| **Event** | `office/events.py` | kind ∈ `blocker\|problem\|opportunity\|signal\|info` |
| **Fact / Knowledge** | `office/knowledge.py` | `{source, entity, confidence, ts}` — retrieval top-N по задаче |
| **Intent** | `office/intent.py` | `capture()` + `set_interpretation()` — журнал намерений владельца |
| **Capability** | `office/capability.py`, `tool_router.py`, `skills.py` | есть/нет/можно приобрести — отсутствие = отдельный Gap |
| **Artifact** | реестр в `office/world.py` через sites/leads/workspace | владелец-проект, ревизии |
| **Specification** | `office/specification.py` | функции, стек, критерии успеха — контракт Acceptance L1 |
| **History** | `office/trace.py` + `office/state.py` | append-only: решения, сдачи, публикации |

---

## 5. System Architecture — из чего состоит система технически

```
Browser (React SPA, webapp/)
      │  HTTP + SSE
      ▼
FastAPI (server.py, 139 route-обработчиков)
      │
      ├── saas/context.py — ContextVar tenant_id, read_json/write_json (атомарно)
      ├── saas/db.py — sqlite: users, workspaces (только auth-метаданные)
      ├── office/loop.py — асинхронный менеджер: по задаче на тенанта с готовым брифом
      │        │
      │        ├── BOOTSTRAP (один раз): researcher → strategist → architect → milestones/plan
      │        └── цикл каждые LOOP_INTERVAL=10s (office/loop.py:31):
      │                world.invalidate_cache → control.is_paused →
      │                leads.check_stale_events → processes.tick →
      │                costs.over_limit (auto-pause) → _close_finished_projects →
      │                _engagement_complete/_stuck → planning_engine.orchestrate
      │                  (CEO decide → leader routing → execution.execute_task)
      │
      ├── core/llm.py — единый провайдер: run_agent(system, user, model, ...)
      │        tool-loop до 8 итераций, observation masking, анти-дубликат вызовов,
      │        DuckDuckGo web_search (≤5/прогон), costs.record ПОСЛЕ каждого ответа
      │        API (инкрементально — не в конце), фолбэк модели при 503/model_not_found
      │
      └── integrations/* — Telegram/GitHub/Google/Website: Action+CredField,
               вызываются через tool_router.use_capability (роутер по намерению)
```

**Хранилище — файлы, не БД** (кроме auth): `data/tenants/<tid>/*.json` —
атомарная запись (`context.write_json`: tmp-файл + `os.replace`, ретрай на
Windows `PermissionError`). Обнаруженные в коде имена файлов (не исчерпывающе):
`plan.json`, `state.json`, `brief.json`, `milestones.json`, `objectives.json`,
`intents.json`, `sites.json`, `leads.json`, `connections.json`, `costs.json`,
`bot_config.json`, `decisions.json`, `lessons.json`, `knowledge.json`,
`specification.json`, `skills.json`, `world_snapshots.jsonl` (кольцевой буфер,
последние 100), `trace.jsonl` (append-only, без ротации — см. §8), `strategy.md`,
`tech_design.md` (текстовые артефакты bootstrap).

**HTTP API** (139 обработчиков в `server.py`, сгруппировано по назначению):
auth (`/api/me`, `/auth/dev-login`, `/auth/github/*`, `/auth/google/*`) ·
brief/onboarding (`/api/brief/*`, `/api/onboarding/*`) ·
агенты/команда (`/api/agents`, `/api/agent/{id}`) ·
план (`/api/plan`, `/api/milestone/{id}`, `/api/milestones`) ·
события (`GET /events` — SSE: hired/speech/thinking/task_done/lead_captured/…) ·
доступы (`/api/connections`, `/api/integrations*`) ·
сайты/лиды (`/site/{tenant}/{slug}`, `/api/lead/{tenant}/{slug}`, `/api/site-lead`) ·
код/терминал (`/api/files`, `/api/file`, `/api/run`, `/api/terminal` — за
`ALLOW_CODE_EXECUTION`) · мир (`/api/world`, `/api/objectives`, `/api/intents`) ·
приёмка (`/api/specification`, `/api/task/{id}/unblock`) ·
наблюдаемость (`/api/trace`, `/api/observability/timeline`, `/api/observability/decision/{id}`) ·
офис (`/api/office/status`, `/pause`, `/resume`) · модели (`/api/model*`) ·
дайджест (`/api/digest`).

---

## 6. Technical Documentation — модули по областям

*Полный список файлов: `src/office/` — 74 модуля, `src/agents/` — 13 модулей.
Ниже — группировка по назначению (детальная mapping-таблица по BOS-компонентам
— `bos-architecture.md` §13; здесь — то, что в неё не входит).*

| Область | Модули | Назначение |
|---|---|---|
| Ядро цикла | `loop.py`, `planning_engine.py`, `decision_engine.py`, `execution.py`, `execution_policy.py` | см. §5 |
| Мир/бизнес-состояние | `world.py`, `objectives.py`, `gap.py`, `intent.py`, `metrics.py`, `progress.py`, `understanding.py` | SSOT, разрыв, измеримость, «понимание компании» (UX-индикатор) |
| Work-модель | `projects.py`, `milestones.py`, `process_instances.py`, `initiatives.py`, `initiative_research.py`, `plan.py` | Project/Process/Initiative, Task-дерево с `parent_id` |
| Приёмка | `acceptance.py`, `specification.py`, `critic.py`, `sandbox.py` | 5 уровней, критик сайтов/ботов, универсальный clone→check→merge |
| Мышление/промпт | `prompt_builder.py`, `roles.py`, `builtin_roles/*.md`, `policies/*.md`, `skills.py`, `builtin_skills/*.md` (18 файлов), `skill_store.py`, `self_awareness.py` | единая сборка промпта; роль=«кто», скилл=«как» |
| Способности | `tool_router.py`, `capability.py`, `needs.py` | `use_capability` → подбор интеграции |
| Знания/история | `knowledge.py`, `lessons.py`, `project_map.py`, `trace.py`, `state.py`, `digest.py` | retrieval, уроки между прогонами, Morning Digest |
| Коммуникация/проекция | `office_channel.py`, `threads.py`, `chat.py`, `questions.py`, `bus.py`, `board.py`, `agent_inbox.py` | чаты, блокирующие вопросы, SSE-шина, доска отдела |
| Оргструктура | `org.py`, `org_graph.py`, `registry.py`, `hr` (в `src/agents/`) | отделы, кто кому подчинён, реестр нанятых |
| Боты/сайты | `bot_engine.py`, `bot_runtime.py`, `bot_config.py`, `telegram_login.py`, `site_builder.py`, `sites.py`, `leads.py`, `processes.py`, `design_style.py`, `company_scan.py` | шаблонный движок бота, публикация лендинга, мини-CRM |
| SaaS/безопасность | `connections.py`, `llm_settings.py`, `models.py`, `autonomy.py`, `constitution.py`, `philosophy.py`, `control.py`, `costs.py`, `exec_sandbox.py`, `health.py`, `observability.py`, `quality_modes.py`, `trust.py`, `dashboard.py`, `digital_infrastructure.py`, `demo.py`, `onboarding_result.py`, `workspace.py`, `intake.py` | креды, пауза, вето, расход, песочница исполнения кода |
| `src/agents/` | `agent_factory.py`, `architect.py`, `leaders.py`, `orchestrator.py`, `researcher.py`, `strategist.py`, `onboarding.py`, `portfolio_tool_handlers.py`, `comms_tool_handlers.py`, `file_tool_handlers.py`, `integration_tool_handlers.py`, `tool_schemas.py` | конкретные роли-исполнители + инструменты, которые им выданы |

Для детального «что делает каждая функция» — источник правды docstring в самом
файле (правило §7.1 ниже: бизнес-логика документируется рядом с кодом, не в
отдельном реестре, который расходится с реальностью через 2 месяца).

---

## 7. Engineering — правила разработки (компакт; разбор инцидентов — `engineering-principles.md`)

1. **Бизнес-логика не живёт в промптах и if-словах** — запись в мире (Objective,
   Capability, Constitution), не строка в системном промпте.
2. **Роль = «кто», скилл = «как».** Смена стека/приёма → правь `.md` скилла,
   не текст роли.
3. **Задача закрывается только Acceptance.** «Done = непустая строка» запрещено.
4. **Один сериализатор на сущность мира** в промпт (пример: `goal` vs `niche`
   — см. инвариант в `CLAUDE.md` §4, единственное место различения).
5. **Учёт расхода — инкрементально**, внутри `llm.run_agent`, не в конце прогона.
6. **Multi-tenancy без глобального состояния** — всё через `saas/context.read_json/write_json`.
7. **Детерминированный код первичнее LLM** везде, где возможен (маршрутизация
   задач, онбординг-бриф, fallback-план).
8. **Минимальная проверка перед коммитом** (нет линтера — прогонять руками):
   `py_compile` всех `.py`, `npx tsc --noEmit` в `webapp/`, `tests/run_all.py`
   (11 файлов юнит-тестов, $0, без LLM).
9. **Не разрабатывать**: микросервисы, Kafka, полную симуляцию мира, собственный
   мультипровайдерный LLM-слой, LLM-решателей там, где хватает детерминированного кода.

---

## 8. Operations — как это работает и чем реально не защищено

**Запуск и dev-безопасность.** `scripts/run.py` — bootstrap + SPA на
`:8000`, reload исключает `data/tenants/<tid>/workspace/` абсолютными путями
(глубокое исключение; раньше `reload_excludes="data/*"` не ловил вложенные пути
— падал реальный офис-цикл при каждой записи файла агентом, исправлено
2026-07-07). Убивать процесс за собой обязательно — на Windows это `python3.13`,
не `python`.

**Переменные окружения**, критичные для эксплуатации (полный список — `CLAUDE.md`
§2): `APP_SECRET` (Fernet-шифрование секретов тенанта), `ALLOW_CODE_EXECUTION`
(по умолчанию `0` — без него `/api/run`/`/api/terminal` недоступны),
`SANDBOX_MODE=direct|docker` (`direct` — без изоляции, осознанный security-долг,
см. ниже), `APINET_ACCESS_TOKEN`/`APINET_USER_ID` (opt-in автогенерация
per-tenant LLM-ключа), `TELEGRAM_API_ID/HASH` (ключи приложения, не пользователя).

**Открытый security-долг** (не решено, по `docs/audit-dd-2026-07-06.md`, свежее
двух других audit-файлов — `audit-dd-2026-07.md` и `audit-architecture-2026-07.md`
частично устарели относительно этого):
- **§17 Code Execution** — `/api/run`/`/api/terminal` исполняют команды на
  хосте без изоляции при `SANDBOX_MODE=direct` (значение по умолчанию); защита
  только флагом `ALLOW_CODE_EXECUTION`. `docker`-режим (`exec_sandbox.py`,
  `docker/sandbox.Dockerfile`) существует, но требует собранного образа и не
  включён по умолчанию.
- **Rate limiting** публичных эндпоинтов (`/api/lead/{tenant}/{slug}`, `/api/run`)
  — по состоянию последнего аудита был не защищён от спама/DoS; проверить
  актуальность при следующей security-правке `server.py`.
- **`trace.jsonl` не ротируется** — append-only без лимита, растёт неограниченно
  для долгоживущих тенантов.
- **Явного prompt-caching (`cache_control`) нет** — полагается на неявное
  префиксное кеширование OpenAI-совместимого провайдера.

**Мониторинг/наблюдаемость, что уже есть:** `office/health.py`, `office/observability.py`
(единая лента `trace + prompts + decisions`), `office/digest.py` (Morning Digest),
`GET /api/trace`, `GET /api/observability/timeline` — это фактические
инструменты эксплуатации, не только для разработчиков.

**Резервное копирование/бэкап** — не реализовано отдельным механизмом:
персистентность — файлы `data/tenants/<tid>/*.json`, снятие бэкапа сегодня
means копирование директории целиком; специального инструмента ротации/архивации
в коде нет.

---

## 9. Статус этого документа и что дальше

Это компиляция по коду на 2026-07-08 (проверено через прямое чтение файлов, не
переписано со старых доков). Рекомендация по расчистке `docs/` (не выполнено,
ждёт решения владельца): `arhitecture.md`, `SAAS_ARCHITECTURE.md`,
`новый_аудит_архитектуры.md`, `1.md`, `2.md`, `3.md` — кандидаты на удаление
или архивирование, содержание разошлось с кодом и дублирует этот файл и
`bos-architecture.md`. `product-vision.md`, `engineering-principles.md`,
`bos-architecture.md`, `handoff.md`, `дорожная_карта.md` — оставлены отдельно
осознанно (см. врезки в начале каждого раздела).
