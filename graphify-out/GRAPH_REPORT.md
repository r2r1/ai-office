# Graph Report - .  (2026-06-21)

## Corpus Check
- Corpus is ~36,012 words - fits in a single context window. You may not need a graph.

## Summary
- 696 nodes · 1142 edges · 80 communities (39 shown, 41 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 15 edges (avg confidence: 0.7)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Frontend Canvas & UI|Frontend Canvas & UI]]
- [[_COMMUNITY_HTTP Integrations Layer|HTTP Integrations Layer]]
- [[_COMMUNITY_Architect Agent|Architect Agent]]
- [[_COMMUNITY_HR Agent|HR Agent]]
- [[_COMMUNITY_Researcher Agent|Researcher Agent]]
- [[_COMMUNITY_Core Concepts & Tech Stack|Core Concepts & Tech Stack]]
- [[_COMMUNITY_Autonomy & Integrations Design|Autonomy & Integrations Design]]
- [[_COMMUNITY_SaaS Database Layer|SaaS Database Layer]]
- [[_COMMUNITY_Integrations Registry|Integrations Registry]]
- [[_COMMUNITY_API Endpoints (FastAPI)|API Endpoints (FastAPI)]]
- [[_COMMUNITY_Server Routes|Server Routes]]
- [[_COMMUNITY_Chat & Threads UI|Chat & Threads UI]]
- [[_COMMUNITY_Module Group 12|Module Group 12]]
- [[_COMMUNITY_Module Group 13|Module Group 13]]
- [[_COMMUNITY_Module Group 14|Module Group 14]]
- [[_COMMUNITY_Module Group 15|Module Group 15]]
- [[_COMMUNITY_Module Group 16|Module Group 16]]
- [[_COMMUNITY_Module Group 17|Module Group 17]]
- [[_COMMUNITY_Module Group 18|Module Group 18]]
- [[_COMMUNITY_Module Group 19|Module Group 19]]
- [[_COMMUNITY_Module Group 20|Module Group 20]]
- [[_COMMUNITY_Module Group 21|Module Group 21]]
- [[_COMMUNITY_Module Group 22|Module Group 22]]
- [[_COMMUNITY_Module Group 23|Module Group 23]]
- [[_COMMUNITY_Module Group 24|Module Group 24]]
- [[_COMMUNITY_Module Group 25|Module Group 25]]
- [[_COMMUNITY_Module Group 26|Module Group 26]]
- [[_COMMUNITY_Module Group 27|Module Group 27]]
- [[_COMMUNITY_Module Group 28|Module Group 28]]
- [[_COMMUNITY_Module Group 29|Module Group 29]]
- [[_COMMUNITY_Module Group 30|Module Group 30]]
- [[_COMMUNITY_Module Group 31|Module Group 31]]
- [[_COMMUNITY_Module Group 32|Module Group 32]]
- [[_COMMUNITY_Module Group 33|Module Group 33]]
- [[_COMMUNITY_Module Group 34|Module Group 34]]
- [[_COMMUNITY_Module Group 35|Module Group 35]]
- [[_COMMUNITY_Module Group 36|Module Group 36]]
- [[_COMMUNITY_Module Group 37|Module Group 37]]
- [[_COMMUNITY_Module Group 38|Module Group 38]]
- [[_COMMUNITY_Module Group 39|Module Group 39]]
- [[_COMMUNITY_Module Group 40|Module Group 40]]
- [[_COMMUNITY_Module Group 41|Module Group 41]]
- [[_COMMUNITY_Module Group 42|Module Group 42]]
- [[_COMMUNITY_Module Group 43|Module Group 43]]
- [[_COMMUNITY_Module Group 44|Module Group 44]]
- [[_COMMUNITY_Module Group 45|Module Group 45]]
- [[_COMMUNITY_Module Group 46|Module Group 46]]
- [[_COMMUNITY_Module Group 47|Module Group 47]]
- [[_COMMUNITY_Module Group 48|Module Group 48]]
- [[_COMMUNITY_Module Group 49|Module Group 49]]
- [[_COMMUNITY_Module Group 50|Module Group 50]]
- [[_COMMUNITY_Module Group 51|Module Group 51]]
- [[_COMMUNITY_Module Group 52|Module Group 52]]
- [[_COMMUNITY_Module Group 53|Module Group 53]]
- [[_COMMUNITY_Module Group 54|Module Group 54]]
- [[_COMMUNITY_Module Group 55|Module Group 55]]
- [[_COMMUNITY_Module Group 56|Module Group 56]]
- [[_COMMUNITY_Module Group 57|Module Group 57]]
- [[_COMMUNITY_Module Group 58|Module Group 58]]
- [[_COMMUNITY_Module Group 59|Module Group 59]]
- [[_COMMUNITY_Module Group 60|Module Group 60]]
- [[_COMMUNITY_Module Group 61|Module Group 61]]
- [[_COMMUNITY_Module Group 62|Module Group 62]]
- [[_COMMUNITY_Module Group 63|Module Group 63]]
- [[_COMMUNITY_Module Group 66|Module Group 66]]
- [[_COMMUNITY_Module Group 67|Module Group 67]]
- [[_COMMUNITY_Module Group 68|Module Group 68]]
- [[_COMMUNITY_Module Group 69|Module Group 69]]
- [[_COMMUNITY_Module Group 70|Module Group 70]]
- [[_COMMUNITY_Module Group 71|Module Group 71]]
- [[_COMMUNITY_Module Group 72|Module Group 72]]
- [[_COMMUNITY_Module Group 73|Module Group 73]]
- [[_COMMUNITY_Module Group 74|Module Group 74]]
- [[_COMMUNITY_Module Group 76|Module Group 76]]
- [[_COMMUNITY_Module Group 77|Module Group 77]]
- [[_COMMUNITY_Module Group 79|Module Group 79]]

## God Nodes (most connected - your core abstractions)
1. `publish()` - 18 edges
2. `Request` - 16 edges
3. `handleEvent()` - 16 edges
4. `_load()` - 12 edges
5. `escapeHtml()` - 12 edges
6. `_load()` - 11 edges
7. `Integration` - 10 edges
8. `_run_office()` - 10 edges
9. `Orchestrator (Директор)` - 10 edges
10. `switchView()` - 9 edges

## Surprising Connections (you probably didn't know these)
- `AI-Office` --uses as backend--> `FastAPI`  [EXTRACTED]
  CLAUDE.md → server.py
- `server.py` --built with--> `FastAPI`  [EXTRACTED]
  CLAUDE.md → server.py
- `decide()` --calls--> `publish()`  [INFERRED]
  src/agents/hr.py → src/office/bus.py
- `make_questions()` --calls--> `publish()`  [INFERRED]
  src/agents/onboarding.py → src/office/bus.py
- `build_brief()` --calls--> `publish()`  [INFERRED]
  src/agents/onboarding.py → src/office/bus.py

## Import Cycles
- 1-file cycle: `server.py -> server.py`

## Communities (80 total, 41 thin omitted)

### Community 0 - "Frontend Canvas & UI"
Cohesion: 0.04
Nodes (42): addFieldRow(), agents, bubbles, canvas, checkBriefStatus(), connectIntegration(), connectionsCache, ctx (+34 more)

### Community 1 - "HTTP Integrations Layer"
Cohesion: 0.06
Nodes (37): AsyncClient, httpx, Action, CredField, Integration, Базовые структуры для описания интеграции.  Интеграция — это декларативное описа, Одно поле учётных данных, которое нужно интеграции., Одно действие интеграции — реальный вызов внешнего API. (+29 more)

### Community 2 - "Architect Agent"
Cohesion: 0.09
Nodes (34): load(), Architect Agent — технический архитектор офиса.  Получает бизнес-стратегию и ф, Загружает ТЗ текущего тенанта (пустая строка если нет)., run_async(), _save(), decide(), _parse_json(), plan_milestones() (+26 more)

### Community 3 - "HR Agent"
Cohesion: 0.08
Nodes (30): decide(), _parse_json(), HR Agent — решает, кого нанять в офис следующим., build_brief(), make_questions(), _parse_json(), Onboarding Agent — встречает клиента.  Читает любой ввод клиента (идея / соцсе, Возвращает список уточняющих вопросов к клиенту. (+22 more)

### Community 4 - "Researcher Agent"
Cohesion: 0.09
Nodes (28): deep(), quick(), Researcher Agent — универсальный исследователь AI-офиса.  Два режима:   quick, Синхронный запуск для CLI., run(), run_async(), _save_report(), Strategist Agent — превращает отчёт ресёрчера в исполнимый план. Работает через (+20 more)

### Community 5 - "Core Concepts & Tech Stack"
Cohesion: 0.08
Nodes (28): AI-Office, apinet.cloud, Isometric Canvas Renderer, cryptography (Fernet), DuckDuckGo Web Search, FastAPI, static/game.js, GitHub OAuth (+20 more)

### Community 6 - "Autonomy & Integrations Design"
Cohesion: 0.11
Nodes (26): Agent Autonomy Principle, Bootstrap Workflow, integrations/base.py, integrations/github.py, integrations/registry.py, integrations/telegram.py, integrations/website.py, agents/agent_factory.py (+18 more)

### Community 7 - "SaaS Database Layer"
Cohesion: 0.14
Nodes (22): Connection, Cursor, conn(), _connect(), execute(), init_db(), query_all(), query_one() (+14 more)

### Community 8 - "Integrations Registry"
Cohesion: 0.13
Nodes (21): Integration, all_integrations(), catalog_payload(), credentials_for(), get(), is_connected(), Каталог доступных интеграций + связка с хранилищем учётных данных.  Здесь регист, Возвращает поля учётных данных из сохранённого подключения (или {}). (+13 more)

### Community 9 - "API Endpoints (FastAPI)"
Cohesion: 0.11
Nodes (23): Request, answer_question(), ask_agent(), brief_questions(), capture_lead(), current_user(), dev_login(), get_me() (+15 more)

### Community 10 - "Server Routes"
Cohesion: 0.10
Nodes (13): get_files(), get_memory(), get_progress(), get_threads(), github_device_start(), github_login_redirect(), FastAPI сервер — SSE-стрим событий + статика игры., Device Flow шаг 1: получить код для ввода на github.com/login/device. (+5 more)

### Community 11 - "Chat & Threads UI"
Cohesion: 0.17
Nodes (19): agentDisplayName(), bumpUnread(), _feedEl(), loadAgentThread(), loadOfficeFeed(), loadThreadList(), onAgentMessage(), onOfficeMessage() (+11 more)

### Community 12 - "Module Group 12"
Cohesion: 0.24
Nodes (15): Демо-режим — проигрывает заранее записанный сценарий работы офиса без обращения, Проигрывает демо-сценарий по кругу., run(), AgentRecord, all_agents(), count(), get(), has_role() (+7 more)

### Community 13 - "Module Group 13"
Cohesion: 0.17
Nodes (15): _cfg(), clear_key(), credentials(), has_own_key(), public(), Персональные настройки доступа к LLM у каждого тенанта: свой API-ключ, base_url, (base_url, api_key) для вызова LLM. Свои настройки тенанта или fallback на .env., Для UI: без открытого ключа. (+7 more)

### Community 14 - "Module Group 14"
Cohesion: 0.13
Nodes (17): addBubble(), getRole(), handleEvent(), loadDeliverables(), loadFiles(), loadLeads(), loadProgress(), openChat() (+9 more)

### Community 15 - "Module Group 15"
Cohesion: 0.28
Nodes (14): add_item(), all_business_done(), all_stages(), current_index(), get(), has_business_stages(), _load(), mark_active() (+6 more)

### Community 16 - "Module Group 16"
Cohesion: 0.31
Nodes (12): _base(), list_files(), Рабочая папка проекта — агенты пишут реальный код. По тенанту: data/tenants/<tid, Статическая проверка работоспособности: компиляция всех .py файлов проекта., read_file(), reset(), _safe(), tree_text() (+4 more)

### Community 17 - "Module Group 17"
Cohesion: 0.18
Nodes (8): _brief_context(), create(), Фабрика агентов — создаёт нового агента по роли и задаче. Работает через единое, Если вопрос звучит как запрос учётных данных — собираем структуру подключения., Формирует блок с брифом клиента для вставки в системный промпт., Возвращает async-функцию, запускающую агента., _try_extract_connection(), Сообщения между агентами — по тенанту (в памяти).

### Community 18 - "Module Group 18"
Cohesion: 0.31
Nodes (8): _all(), by_agent(), for_agent(), payload(), price_for(), Учёт расхода токенов и стоимости работы офиса — по тенанту. Стоимость считается, record(), totals()

### Community 19 - "Module Group 19"
Cohesion: 0.27
Nodes (9): delete_file(), get_tenant(), Контекст тенанта + персистентность по тенанту.  Текущий тенант хранится в Contex, Полностью удаляет данные текущего тенанта (reset «новый клиент»)., read_json(), tenant_dir(), wipe(), write_json() (+1 more)

### Community 20 - "Module Group 20"
Cohesion: 0.33
Nodes (7): _all(), all_sites(), delete(), get(), make_slug(), Опубликованные лендинги офиса — по тенанту (data/tenants/<tid>/sites.json).  Хос, save()

### Community 21 - "Module Group 21"
Cohesion: 0.20
Nodes (10): drawBubble(), drawIsoCharacter(), drawIsoMap(), drawIsoTile(), gameLoop(), isoBox(), isoFloor(), render() (+2 more)

### Community 22 - "Module Group 22"
Cohesion: 0.33
Nodes (6): get(), is_ready(), load(), Бриф клиента — то, что превращает универсальный офис в офис «под клиента».  Хран, research_question(), summary()

### Community 23 - "Module Group 23"
Cohesion: 0.36
Nodes (7): _all_histories(), ask(), _build_system(), clear_history(), Чат с агентами — пользователь может кликнуть на агента и поговорить с ним. Кажд, Задаёт вопрос конкретному агенту и возвращает его ответ., _save_all()

### Community 24 - "Module Group 24"
Cohesion: 0.33
Nodes (6): add(), _all(), all_leads(), count(), for_site(), Лиды, собранные формами лендингов — по тенанту. Реальные данные от посетителей.

### Community 25 - "Module Group 25"
Cohesion: 0.33
Nodes (6): _all(), all_entries(), context_block(), lookup(), Постоянная память офиса — ответы пользователя на вопросы агентов (по тенанту)., remember()

### Community 26 - "Module Group 26"
Cohesion: 0.33
Nodes (6): _all(), mark_answered(), post(), Персональные чаты пользователя с агентами (отображаемая переписка). По тенанту., recent(), summaries()

### Community 27 - "Module Group 27"
Cohesion: 0.22
Nodes (9): addLog(), buildChatItem(), checkAuth(), escapeHtml(), logOnly(), openFullText(), openFullTextRaw(), openMilestone() (+1 more)

### Community 28 - "Module Group 28"
Cohesion: 0.28
Nodes (9): fillModelSelect(), fmtCost(), fmtTokens(), loadCosts(), loadModelsConfig(), openAgentDrawer(), setupAgentModelSelector(), setupIntakeModel() (+1 more)

### Community 29 - "Module Group 29"
Cohesion: 0.32
Nodes (5): Future, answer(), ask(), _normalize(), Блокирующие вопросы агентов пользователю — по тенанту.  Futures живут в памяти (

### Community 30 - "Module Group 30"
Cohesion: 0.39
Nodes (5): bump_to(), get(), Прогресс офиса (линейные этапы) — по тенанту., set_stage(), _state()

### Community 31 - "Module Group 31"
Cohesion: 0.33
Nodes (3): clear(), Общий канал офиса — лента сообщений всех агентов и пользователя. По тенанту., reset()

### Community 32 - "Module Group 32"
Cohesion: 0.29
Nodes (7): closeConnForm(), deleteConnection(), loadConnections(), loadIntegrations(), renderConnections(), renderIntegrations(), saveConnection()

### Community 33 - "Module Group 33"
Cohesion: 0.40
Nodes (6): getDeskPosition(), spawnAgent(), syncAgentTargets(), tileToScreen(), updateAgentStatus(), updateSidebar()

### Community 34 - "Module Group 34"
Cohesion: 0.33
Nodes (6): intakeGetQuestions(), intakeStartOffice(), readModelSelect(), renderIntakeQuestions(), saveIntakeModel(), showIntakeLoading()

## Knowledge Gaps
- **67 isolated node(s):** `Path`, `Path`, `AsyncOpenAI`, `Any`, `Future` (+62 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **41 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `FastAPI` connect `Core Concepts & Tech Stack` to `Server Routes`?**
  _High betweenness centrality (0.104) - this node is a cross-community bridge._
- **Are the 10 inferred relationships involving `publish()` (e.g. with `run_async()` and `decide()`) actually correct?**
  _`publish()` has 10 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Точка входа AI-офиса.  Использование:   python main.py                      #`, `FastAPI сервер — SSE-стрим событий + статика игры.`, `Ставит контекст тенанта из сессии (аноним → 'default').` to the rest of the system?**
  _194 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Frontend Canvas & UI` be split into smaller, more focused modules?**
  _Cohesion score 0.039473684210526314 - nodes in this community are weakly interconnected._
- **Should `HTTP Integrations Layer` be split into smaller, more focused modules?**
  _Cohesion score 0.061224489795918366 - nodes in this community are weakly interconnected._
- **Should `Architect Agent` be split into smaller, more focused modules?**
  _Cohesion score 0.09388335704125178 - nodes in this community are weakly interconnected._
- **Should `HR Agent` be split into smaller, more focused modules?**
  _Cohesion score 0.0761904761904762 - nodes in this community are weakly interconnected._