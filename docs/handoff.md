# Handoff — AI-Office

Передача контекста по работе над продуктом. Язык проекта — русский.

---

## 🎯 Цель

**AI-Office** — мультиарендный **SaaS**: автономный офис AI-агентов, который реально
помогает предпринимателю строить/развивать бизнес (исследование рынка → стратегия →
план → реальные артефакты). Не игрушка «компания за 20 минут», а честный итеративный
консультант, который **спрашивает, уточняет, предлагает и только потом делает**.

Параллельная цель этой серии правок — довести **фронтенд (React SPA)** до премиального
SaaS-уровня: лендинг, авторизация, рабочий кабинет, «жидкое стекло» (Apple liquid glass).

---

## 📍 Текущее состояние

### Бэкенд (работает)
- Discovery-first интейк: первый запрос в чат → офис **задаёт уточняющие вопросы**,
  собирает бриф из ответов, потом стартует. (`src/office/intake.py`, `server.py`)
- Планирование **goal-aware**: стратегическая цель → рекомендации + вопрос «что строить»,
  а НЕ лендинг по умолчанию. Лендинг/бот только по явной просьбе. (`src/office/loop.py`,
  `src/agents/orchestrator.py`)
- Честные этапы: убраны фейковые «первые клиенты / масштабирование», завершение не
  помечает невыполненное. (`loop.py`, `orchestrator.py`)
- Менеджер запускает офис и для `default`-тенанта (демо), а не только для воркспейсов.
- Чат-баги исправлены: `api.chatPost`/`api.ask` слали неверные поля (`message` vs `text`) —
  сообщения не доходили; оптимистичные сообщения держатся в `pending` и не стираются.
- Агенты пишут межагентный диалог в общий чат (ask_colleague/request_research/delegate).
- Зацикливание разработчика на `publish_site` пофикшено: авто-детект папки сайта;
  критик больше не велит публиковать; зависший дизайнер/разработчик с готовым сайтом —
  задача принимается, а не переделывается. (`integrations/website.py`, `critic.py`, `loop.py`)
- Свобода стека у разработчика (не только HTML/CSS/JS). (`agent_factory.py`)

### Фронтенд (работает)
- Лендинг + авторизация (GitHub Device Flow + email dev-login), Gate-роутинг.
  (`app/Gate.tsx`, `app/landing/LandingView.tsx`, `app/auth/AuthModal.tsx`)
- Навигация: Офис / Проект / Команда / Чаты / Итоги · Доступы / Аккаунт.
- Карточки агентов, sub-tabs, модалки полной инфы (клик по карточке/результату/этапу).
- Правая панель Офиса: Чат + Журнал. Скачивание логов в Аккаунте. Плашка модели в топбаре.
- Выбор модели: список пресетов + своя модель.
- Живой индикатор «печатает…» с реальной активностью агента.
- **Liquid glass**: сильный blur (30px островки / 18–26 карточки) + сатурация, яркий кант.
  Тёмная тема — **нейтрально-серая** (без синевы), БЕЗ градиента на карточках.
- Фон — лёгкий нейтральный градиент, чтобы передний слой выделялся.
- **TabBridge** — SVG-метабол: liquid-glass «капля» соединяет активную вкладку с панелью
  (две эллипс-капли + вогнутая шейка, пружинная физика, растяжение по скорости).
- **Сайдбар «обнимает» активную вкладку**: `clip-path` сужается сверху/снизу выбранной,
  выпуклость у неё, перетекание через CSS-transition.

### Известные проблемы / не доведено
- Полный сквозной прогон нового офиса (discovery → bootstrap → результат) на живой
  модели НЕ гонялся целиком (дорого по токенам). Проверены части.
- Настоящее рефракционное «жидкое стекло» на самом мосту/метаболе невозможно в вебе
  (`backdrop-filter` ломается под SVG-фильтрами) — мост это сплошной цвет поверхности.
- blur 30px тяжелее прежнего — на слабых машинах вкладка «Команда» (много стеклянных
  карточек) может подлагивать.
- На порту 8000 висит фантомный сокет от старого процесса (не убивается) — для локалки
  использовать другой порт.

---

## 🗂 Файлы, над которыми работали

### Бэкенд (Python)
| Файл | Назначение в этих правках |
|------|---------------------------|
| `src/office/intake.py` | **новый** — состояние discovery-диалога (вопросы/ответы) |
| `server.py` | `/api/chat` → discovery + CEO-триаж; download-logs; agent/model API |
| `src/agents/orchestrator.py` | `interpret_directive`, честные fallback-этапы, запрет «выдумывать продукт» |
| `src/office/loop.py` | goal-aware `_fallback_plan`, честное завершение, `wake_tenant`, антицикл зависших, менеджер для `default` |
| `src/agents/agent_factory.py` | межагентный диалог в общий чат; свобода стека |
| `src/integrations/website.py` | авто-детект папки сайта в `publish_site` |
| `src/office/critic.py` | критик не велит публиковать вручную |

### Фронтенд (React/TS)
| Файл | Назначение |
|------|-----------|
| `webapp/src/app/Gate.tsx` | роутинг splash/landing/office |
| `webapp/src/app/landing/LandingView.tsx` | лендинг |
| `webapp/src/app/auth/AuthModal.tsx` | авторизация (GitHub device flow + email) |
| `webapp/src/app/App.tsx` | каркас, фон-градиент, монтаж TabBridge |
| `webapp/src/app/components/NavRail.tsx` | меню + clip-path «обнимает» активную вкладку |
| `webapp/src/app/components/TabBridge.tsx` | SVG-метабол мост сайдбар↔панель |
| `webapp/src/app/components/Modal.tsx`, `AgentDetailModal.tsx` | модалки полной инфы |
| `webapp/src/app/components/ModelPicker.tsx`, `icons.tsx`, `RightPanel.tsx`, `TopBar.tsx` | пикер моделей, иконки, правпанель, топбар |
| `webapp/src/app/views/*` | ProjectView, ResultsView, ConnectionsView, ChatsView, TeamView, AccountView, ui.tsx |
| `webapp/src/styles/design.css` | дизайн-токены, liquid glass, тени, фон-градиент |
| `webapp/src/data/OfficeProvider.tsx`, `api.ts`, `roles.ts`, `app/hooks.ts` | данные/SSE, API, роли, throttle |

---

## 🔧 Что изменилось (ключевое)

1. **Discovery-first**: офис сначала спрашивает, потом работает (раньше слепо строил лендинг).
2. **Честность**: нет фейковых этапов и преждевременной «победы»; план под цель, а не всегда лендинг.
3. **Чат реально работает**: исправлены payload-баги, оптимистичный рендер, межагентный диалог виден.
4. **Антицикл разработчика**: publish_site не падает зря, зависшие задачи не переделываются вечно.
5. **UI**: лендинг+авторизация, модалки, пикер моделей, живой «печатает…».
6. **Liquid glass**: нейтрально-серое (без синевы), сильное стекло, без градиента на карточках,
   метабол-мост и clip-path «объятие» активной вкладки.

---

## ❌ Что пробовал и НЕ сработало

- **Яркая янтарная капля-мост** (TabBridge v1) — выглядела как наклейка поверх, а не слияние.
  → перешёл на цвет поверхности и рисование ЗА контентом.
- **Тень под мостом** (`feDropShadow`) — давала серость/грязь, «мешала». → убрал.
- **Синеватые серые** в тёмной теме (`rgba(34,34,40)`, `#1c1c21`) — пользователь не хотел синевы.
  → нейтральные `rgba(44,44,44)`, `#242424` (R=G=B).
- **Градиентный глянец на карточках/островках** — пользователь сказал «градиент не нужен».
  → убрал, оставил плоское стекло + кант.
- **Настоящее стекло на метаболе** (gooey + backdrop-blur одновременно) — невозможно на вебе.
- **Верификация скролла/ховера/анимаций в headless-preview** — программный скролл не шлёт
  события, motion-frameloop не флашит, screenshot подвисает на сложном DOM. Верифицировать
  scroll/hover/анимации — глазами в реальном браузере. (см. память `preview-scroll-limitation`)
- **`npx skills find`** — сначала блокировалось песочницей; результаты по «autonomous agents»
  слабые (мало установок, неизвестные авторы) — ничего не ставил.

---


---

## 🩹 Аудит 2026-07-03 — 4 бага исправлены

Сквозной аудит `server.py`, `loop.py`, BOS-модулей (world/projects/acceptance/
specification/objectives/intent/execution_policy), мультиарендности, промпт-билдера
и фронта. Найдено и исправлено:

1. **`/api/site-lead` требовал авторизацию → 401, лиды терялись.** Посетитель
   опубликованного лендинга не авторизован в SaaS, а формы многофайловых сайтов
   обязаны слать заявки именно на этот путь (так требует `critic.check_site`).
   → добавлен в `_PUBLIC_API` (`server.py`).
2. **Зомби-офис после `/api/brief/reset`.** Reset стирал файлы тенанта, но
   запущенная asyncio-задача офиса жила со старым состоянием в RAM (стратегия,
   план), реанимировала данные и жгла токены; новый офис не стартовал, пока
   старая задача не done. → `office.forget_tenant(tid)` (`loop.py`): отменяет
   задачу и чистит per-tenant словари живости, не задевая чужие тенанты; вызывается
   из reset ДО `saas_context.wipe()`.
3. **Watchdog убивал агентов, легитимно ждущих клиента.** `ask_user`/одобрение
   публикации блокируют корутину до 300–600с, а `MAX_THINK_SECS`=240 — задача
   уходила в очередь и получала ВТОРОГО исполнителя, пока первая корутина
   продолжала работать после ответа (класс бага «двойная запись site/», уже
   чинившийся раньше для другого случая). → `_heal_stuck_agents` (`loop.py`)
   продлевает таймеры, пока в тенанте есть открытые вопросы `questions.list_pending()`.
4. **Нативная HTML-форма без контакта видела сырой JSON.** → `_LEAD_NO_CONTACT_HTML`
   в стиле `_LEAD_THANKS_HTML` (`server.py`), отдаётся при `native=True`.

Смоук-протестировано (без реального LLM-вызова, $0 расход): `forget_tenant` отменяет
задачу и чистит только свой тенант; watchdog продлевает/сбрасывает по наличию вопроса.

**Не тронуто, но замечено при аудите** (мёртвый код / микро-утечки, не баги поведения):
- `agent_factory.py`: `_SEND_MESSAGE_TOOL`/`_READ_MESSAGES_TOOL` объявлены, но не
  подключены к `run_agent` — рабочая межагентка идёт через `ask_colleague`/`delegate_task`.
- `_verify_and_fix_if_needed` (`loop.py`) собирает `fix_task["id"]`, который никогда
  не читается — `plan.add_task` генерирует свой id.
- `server.py` `_auth_attempts` (rate-limit по IP) растёт неограниченно между запросами
  разных IP — не чистится TTL-обходом, только при повторном обращении того же IP.

**⚠️ Правило проекта: любая сессия/агент, вносящая нетривиальные правки в бэкенд
или фронт, ДОЛЖНА дописывать сюда раздел с датой** — что изменилось, что не
сработало, что осталось. Это единственный файл, который читают в начале новой
сессии для восстановления контекста; не полагайся на память между сессиями.

---

## 🩹 Аудит бизнес-логики vs BOS 2026-07-03 (вторая волна) — 8 фиксов

Сверка кода с `docs/bos-architecture.md` + разбор жалобы «система зависает на
ресёрчере». Ресёрчер был ни при чём — он просто ПЕРВЫЙ, кто ищет в вебе.

**Корень зависания (исправлено):**
1. `core/search.py`: DDGS без timeout — в РФ DuckDuckGo блокируется, соединение
   висло вечно → передаём `timeout=20` (с фолбэком для старых версий либы).
2. `core/llm.py`: `_search_async` без `wait_for` — корутина агента ждала тред
   бесконечно → `SEARCH_TIMEOUT=45s` (env), по таймауту модель получает «продолжай
   без данных». Бонус-эффект старого бага: зависшие треды исчерпывали общий пул
   `asyncio.to_thread` (~32) и замораживали поиски ВСЕХ агентов всех тенантов.
3. `office/loop.py`: BOOTSTRAP не под watchdog (`_heal_stuck_agents` лечит только
   агентов из `_assign`) → шаги ресёрчера и архитектора обёрнуты в
   `BOOTSTRAP_STEP_TIMEOUT=900s` (env) с честным сообщением и продолжением по брифу.

**Остальные фиксы бизнес-логики:**
4. Свежий офис всегда выглядел «восстановленным»: `_first_cycle_done` считался
   ПОСЛЕ `_hire_initial` (который сам создаёт hired-записи в state) → «Офис
   восстановлен» сразу после онбординга + потерянный первый цикл. Флаг снимается
   до наймов.
5. Watchdog закрывал сайт-задачу БЕЗ приёмки (нарушение BOS §8) → теперь
   детерминированная проверка критических маркеров критика; битый сайт → revert
   с фидбеком вместо «принята».
6. Дедуп fix-задач считал done-задачи: после одной выполненной доработки офис
   объявлял успех с оставшимися критическими проблемами → глушат только
   pending/in_progress/blocked.
7. Event Layer был частично мёртв (BOS §10): `orchestrator.decide()` — единственный
   читатель problem/signal/info — не вызывается никем с перехода на plan-driven
   цикл; blocker-события никогда не помечались processed. → события подмешаны в
   `decide_company` (живой CEO-путь) и детерминированно помечаются после показа;
   `raise_event` получил `task_id`; разблокировка задачи (`/api/task/{id}/unblock`)
   закрывает её blocker через `events.resolve_for_task`.
8. Личный чат (`/api/ask`) шёл мимо Intent Layer (BOS §1 «единый вход намерений») →
   добавлен `intent.capture` + интерпретация scope=personal_chat.

**Найдено, но НЕ исправлено (отчёт для следующих сессий):**
- Мёртвый код: `orchestrator.decide()` (~150 строк, LLM-решатель CEO уровня
  агентов) и `plan.mark_done_by_role` — вызовов нет.
- Orphan-задачи (роль без отдела) помечаются `done`, хотя не выполнялись —
  завышает прогресс; честнее статус `skipped` (нужна поддержка в UI).
- Кросс-контаминация приёмки: `acceptance.check` гоняет `workspace.verify()` по
  ВСЕМУ workspace и site-критику для любых designer/developer задач — битый
  чужой файл валит приёмку несвязанной задачи (3 провала → блок).
- `estimated_cost` пишется в trace, но НЕ сверяется с остатком бюджета до
  исполнения (BOS §6) — есть только глобальный `over_limit` на цикле.
- SSOT-нарушения из спеки (§4): futures вопросов и watchdog-словари в памяти
  процесса — признано в BOS как «после пятёрки ядра».
- Два скорера потребностей (tool_router + skills) вместо одного (BOS §5).
- `agent_id → worker_id` (BOS §12, п.4 порядка разработки) не сделано.
- Acceptance L3 для ботов — статические проверки текста, а не «вызов хендлеров
  с фейковыми Update» (BOS §8).
- Blocked-задача не задаёт владельцу блокирующий вопрос (только событие + кнопка
  unblock в UI) — по §10 blocker должен гарантированно доходить до владельца.

---

## 🩹 2026-07-03 (третья волна) — закрыт долг из списка «НЕ исправлено» выше

Из списка предыдущей волны закрыто 7 пунктов:

1. **Мёртвый код удалён**: `orchestrator.decide()` (~150 строк LLM-решателя уровня
   агентов + `_DECIDE_SYSTEM`/`_ROLE_KEYWORDS`/`_role_hint`/`HIREABLE_ROLES`),
   `plan.mark_done_by_role`, невключённые `_SEND_MESSAGE_TOOL`/`_READ_MESSAGES_TOOL`
   с хендлерами в `agent_factory` (живые копии для чата — в `chat.py`), мёртвый
   dict в `_verify_and_fix_if_needed`. `MAX_PER_ROLE` оставлен как документированный
   инвариант (CLAUDE.md на него ссылается; enforcement — в call-sites).
2. **Orphan-задачи → статус `skipped`** вместо ложного `done`: прогресс не врёт
   (`progress()` отдаёт `{done, skipped}`, percent по done+skipped), deps
   удовлетворяются, `departments_needed`/`for_agent`/`missing_for_plan` учитывают.
   Фронт: колонка «Пропущены» в канбане (видна только при наличии), `board_summary`
   показывает ⏭N.
3. **Кросс-контаминация приёмки устранена**: `workspace.verify(changed_since=)` +
   `acceptance.check(started_ts=)` — Build проверяет только файлы, изменённые ЭТОЙ
   задачей; роль-эвристика сайта требует реального касания site/ в задаче. Сайт-задачи
   ПО ЗАГОЛОВКУ проверяются по сайту всегда (явная ответственность). Финальная
   верификация (`_verify_and_fix_if_needed`) осталась глобальной — это правильно.
4. **Бюджетный гейт ДО исполнения** (BOS §6): `costs.would_exceed(est)` — общий и
   дневной лимиты + порог Конституции (`_effective_total_cap`); `_job` не начинает
   шаг, который заведомо выйдет за лимит (пауза + revert задачи).
5. **Blocker гарантированно доходит до владельца** (BOS §10): при блокировке задачи —
   сообщение в личный чат CEO (бейдж непрочитанного). Намеренно НЕ `questions.ask`:
   незакрытый вопрос отключил бы watchdog (он продлевает таймеры при pending-вопросах).
6. **Единый скорер потребностей** (BOS §5): новый `office/needs.py`
   (`tokens`/`score_keywords` с обработкой «без X»/`overlap`); Skills и Tool Router
   делегируют ему — поведение матчинга больше не расходится.
7. **Утечка `_auth_attempts`** (rate-limit по IP в server.py) — sweep мёртвых IP
   при >1000 записей.

**Осталось отложенным (осознанно, причины):**
- SSOT: futures вопросов и watchdog-словари в памяти процесса — BOS §13 сам
  откладывает («после пятёрки ядра — вынос живости из памяти процесса»).
- `agent_id → worker_id` — миграция схемы + фронта, BOS вяжет её с отдельным этапом.
- Acceptance L3 ботов через фейковые Update — требует песочницы для исполнения
  агентского кода (произвольный bot.py нельзя безопасно импортировать в процесс);
  отдельная фича по BOS §9 (Sandbox).
- `hr.py` — тоже мёртвый модуль (никем не импортируется), НЕ удалён в эту волну:
  роль hr упоминается в roles.SERVICE_ROLES/чате — сначала решить судьбу роли.

Проверено: py_compile всего дерева, tsc фронта, смоук-тесты (skipped-учёт: deps/
progress/board; scoped-приёмка: чужой битый .py не валит задачу, site-titled задача
проверяется всегда; budget-гейт; скорер: «без 3D» штрафуется; полный импорт server
и всех модулей после удалений; world.snapshot со skipped). LLM не вызывался ($0).

---

---

## 🏛 2026-07-03 (архитектурная ревизия) — BOS-аудит + дорожная карта + Engineering Principles

Полная ревизия проекта относительно `docs/bos-architecture.md` в роли Chief
Architect (не код, только анализ). Результат — три артефакта, все в диалоге
с пользователем как техническим директором:

1. **Аудит зрелости по 20 пунктам** (domain model, world model, prompt
   architecture, decision/planning/execution/acceptance, memory, events,
   capability, providers, UI, technical debt, legacy, BOS-mapping,
   readiness-проценты). Итог: **~45% реального соответствия BOS**, честный
   Bootstrapping-режим без замкнутого измерительного полукруга
   (Metrics→Gap→Decision-diff отсутствуют как класс, Sandbox — 0%).
2. **Дорожная карта до идеального результата**, пересмотренная по фидбеку
   CTO — добавлена ось **User Value** (не только архитектурная зависимость),
   реордер фаз: Capability+Artifacts подняты перед Measurement (цепочка
   Task→Capability→Provider→Execution первична), добавлена Phase 0.5
   Observability (сшивка уже существующих trace/prompts/decisions/world.diff
   в одну временную шкалу — НЕ с нуля), Metrics переименован в Measurement
   Layer (шире: события+стоимость+время+KPI), Sandbox переосмыслен как
   универсальный механизм (`clone→check→merge/discard`), а не фича Decision,
   добавлена документируемая (не строящаяся) **Phase X — Learning Engine**
   как явный горизонт за Steady State.
3. **`docs/engineering-principles.md`** — 15 нарушаемых правил для новой
   команды, каждое привязано к реальному найденному в проекте инциденту
   (goal/niche-путаница, скрытый баг маршрутизации бота, память процесса
   вместо мира и т.д.), а не абстрактные пожелания.

**Решение зафиксировано:** архитектурная стадия закрыта, фундаментальные
изменения заморожены до появления конкретной практической причины их
пересматривать — дальше «строим, а не проектируем» (Phase 0 → 0.5 → 1 → …
из roadmap выше).

**Важно для следующей сессии:** это ЧИСТО документационная сессия — код не
менялся (кроме предыдущих волн правок этого же дня, см. разделы выше).
Полный текст аудита (20-пунктовый разбор по разделам BOS + Readiness-таблица)
остался в истории диалога, файлом НЕ сохранён — если понадобится, пересобрать
заново по текущему состоянию кода. Итоговая roadmap (v2, с осью User Value)
сохранена целиком: **`docs/дорожная_карта.md`** — она заменила черновую
версию v1 (которая была в файле раньше, без ревизии CTO). Держать
`дорожная_карта.md` актуальной при следующих архитектурных решениях —
не пересказывать её заново в handoff.

---

## 🏗 2026-07-03 (Phase 0 дорожной карты) — гигиена + скрытый баг маршрутизации

Первая фаза реализации по `docs/дорожная_карта.md` (после закрытия архитектурной
стадии). Phase 0 не имеет зависимостей и содержит реальный прод-баг. Закрыто 5 из 5:

1. **Скрытый баг маршрутизации бота записи ИСПРАВЛЕН** (главный по User Value).
   Правило «бот записи/сбора лидов → ТОЛЬКО integrator, НИКОГДА developer» жило
   лишь в подсказке LLM-пути лидеров (`leaders._DEPT_HINTS`), который работает только
   до генерации плана — почти никогда. Живая детерминированная маршрутизация о нём
   не знала: план мог отдать booking-бота developer. → детерминированное правило
   `plan._route_role(role, title)` в нормализации задачи (`set_tasks`+`add_task`):
   бот (`telegram/бот/aiogram/…`) + запись/лид (`запис/бронир/лид/заяв/…`) без
   кастомной логики (`постинг/парс/групп/…`) → принудительно `integrator`.
   Смоук-тест: booking-боты → integrator, кастомный бот → developer, лендинг →
   developer. `_DEPT_HINTS` оставлен как подсказка почти-мёртвого LLM-пути (не вредит).
2. **`capabilities.py` → `quality_modes.py`** (`git mv`). Имя конфликтовало с термином
   BOS Capability (Phase 2 введёт настоящий `office/capability.py`). Python-импортёры
   обновлены: `models.py` (2), `execution_policy.py`, `server.py`. HTTP-эндпоинт
   `/api/capabilities` и фронт НЕ трогал намеренно — Phase 2 переназначит этот путь
   под реестр Capability, тогда и переименуется (сейчас меньше преждевременной ломки).
   `_FILE="capabilities.json"` оставлен — не терять настройки тенантов.
3. **Дубль ролей в чате устранён** (`chat.ROLE_SYSTEM`). Была вторая, расходящаяся
   копия личностей ролей. Теперь отдельческие роли берут единый источник
   `roles.render()` (builtin_roles/*.md); для штабных ролей CEO (orchestrator/
   researcher/strategist/hr), у которых нет md-файла (их текст — в агент-модулях),
   оставлен явно ограниченный `chat._SERVICE_PERSONA`. `grep ROLE_SYSTEM` по коду пуст.
4. **Мёртвый `src/agents/hr.py` удалён** (`git rm`) — нигде не импортировался (наём
   давно детерминированный). РОЛЬ `hr` (label в roles.SERVICE_ROLES/registry/chat)
   оставлена — её полное удаление трогает UI и требует отдельного решения о судьбе
   роли. `agent_inbox` НЕ удалял — он ещё живой в чате (`send/read` через инструменты).
5. **Индикатор «Понимание» питается сигналом качества цели.** Раньше давал +10 за
   ЛЮБУЮ непустую цель, включая «не знаю». → `brief.is_junk_goal()`/`has_meaningful_goal()`
   (единый сигнал, `effective_goal` тоже переведён на него); `understanding.payload`
   мусорную цель не засчитывает, показывает в «чего не хватает».

Проверено: `py_compile` всего дерева, импорт `server` и всех тронутых модулей,
смоук-тесты маршрутизации бота и `is_junk_goal`. LLM не вызывался ($0). Фронт не
трогал (tsc не нужен).

**Осталось из Phase 0 (осознанно отложено):** судьба РОЛИ `hr` (не модуля) —
удалять ли label целиком из SERVICE_ROLES/registry/UI; остатки `agent_inbox` —
живы в чате, удалять только вместе с решением по межагентке.

**Следующий шаг по карте:** Phase 0.5 (Observability — сшивка trace/prompts/
decisions/world.diff в одну шкалу) или Phase 1 (Prompt Builder полное покрытие +
Acceptance L1). Обе дёшевы и без внешних зависимостей.

---

## 🔭 2026-07-03 (Phase 0.5 дорожной карты) — Observability (сшивка журналов)

Вторая фаза. Не создаёт логирование с нуля — **сшивает** существующие журналы
(trace.jsonl, prompts.jsonl, decisions, world_snapshots.jsonl) в одну шкалу с
перекрёстными ссылками. DoD: по `decision_id` — полная цепочка одним запросом.

**Пломбировка correlation-id:**
- `prompt_builder.log_prompt` теперь генерирует и ВОЗВРАЩАЕТ `prompt_id` (кладёт в
  запись prompts.jsonl и в trace-запись `prompt`); + ридеры `prompt_by_id`,
  `recent_prompts`.
- `decisions.record(prompt_id=…)` хранит ссылку на промпт; новые `decisions.get(did)`,
  `decisions.set_snapshot(did, sid)` (+ поля `prompt_id`/`snapshot_id` в записи).
- `world.save_snapshot` проставляет `snapshot_id`; новые ридеры `snapshot_by_id`,
  `snapshot_before` (соседний срез для diff «до/после»), `snapshots_between`.
- `loop._apply_company_decision`: после применения НЕ-wait решения фиксирует срез
  мира `decision:<did>` и привязывает его к решению → `world.diff(before, after)` =
  «что решение изменило в мире». `prompt_id` решения проставит Phase 1 (когда
  CEO-промпт пойдёт через Builder и залогируется); сейчас цепочка сшивает промпт по
  времени+автору как фолбэк.

**Новый модуль `office/observability.py`:**
- `timeline(since, until, limit)` — 4 источника, слитые по времени (`source ∈
  {trace, prompt, decision, snapshot}`).
- `decision_chain(did)` — {decision, prompt (по prompt_id или ближайший по времени),
  trace (по decision_id/prompt_id или в окне ±45с), world_diff (до/после по
  snapshot_id)}.

**Эндпоинты** (server.py): `GET /api/observability/timeline`,
`GET /api/observability/decision/{id}`.

Проверено: `py_compile` всего дерева, импорт `server`, сквозной смоук-тест
(лог промпта → срез → решение с prompt_id → срез после → `decision_chain`: промпт
слинкован по prompt_id, trace найден, world_diff посчитан; `timeline` сливает все
4 источника). LLM не вызывался ($0).

**Не сделано (осознанно):** фронтовое переиспользование API во вкладках «События»/
«Трейс» (DoD чисто бэкендовый, фаза невидима пользователю — ⭐⭐⭐⭐/❌). Прошивка
`prompt_id` сквозь `llm.run_agent` для worker-трейсов не делалась (слишком
инвазивно; worker-сшивка идёт по времени+agent, а trace-запись `prompt` уже несёт
`prompt_id`). Полная линковка CEO-решение↔промпт зажжётся в Phase 1.

---

## 🧱 2026-07-03 (Phase 1a, шаг 1/N) — Prompt Builder: миграция CEO

Начало Phase 1 (полное покрытие Prompt Builder). Многофайловая миграция —
делается по потребителю. **Шаг 1: orchestrator (CEO), 6 промптов.**

- 6 литералов `orchestrator._*_SYSTEM` (`_COMPANY/_MILESTONES/_DIRECTIVE/_PLAN/
  _BOARD/_INITIATIVE`) вынесены в файлы `office/policies/ceo_*.md`. В `orchestrator.py`
  промпт-литералов больше нет.
- Новый `prompt_builder.company_system(policy_name, agent_id, role, task,
  with_brief=True) -> (system, prompt_id)`: политика (.md) + тот же слот **Brief**,
  что у воркеров (единственный сериализатор goal≠niche — `brief_block`) + полный
  лог в `prompts.jsonl`. Теперь в журнале есть записи `role="orchestrator"` наравне
  с воркерами (раньше решения CEO отлаживались вслепую).
- Хендлерные `user`-сообщения CEO очищены от ручной сериализации goal/niche —
  их теперь несёт слот Brief в system (принцип №11 «один сериализатор»).
- `decide_company` кладёт `_prompt_id` в результат → `loop` пишет его в
  `decisions.record(prompt_id=…)` → **полная линковка Decision↔промпт из Phase 0.5
  зажглась** (раньше сшивка была только по времени).

Проверено: `py_compile`, импорт `server`+`orchestrator`, `company_system` собирает
и логирует промпт (`role=orchestrator`, pid возвращается), все 6 политик грузятся,
grep литералов `_*_SYSTEM` пуст. LLM не вызывался ($0).

**Осталось в Phase 1a (следующие шаги):** `leaders._LEADER_SYSTEM` (нужен fmt-слот:
{title}/{roles_desc}), `researcher/strategist/architect.SYSTEM_PROMPT`,
`onboarding._QUESTIONS_SYSTEM/_BRIEF_SYSTEM`, `critic.review_site_llm`,
`board/initiative` уже сделаны. Затем **Phase 1b — Acceptance L1**
(`specification.checklist()` → сверка в приёмке). DoD Phase 1 (grep без литералов
во всём `src/agents`+`src/office`) закрывается по завершении всех потребителей.

---

## 🧱 2026-07-03 (Phase 1a завершён) — Prompt Builder: остальные потребители

Достроена миграция всех ручных системных промптов (шаг 1 — CEO — был выше):

- **Лидеры** (`leaders._LEADER_SYSTEM`) → `policies/leader_decide.md`.
  `company_system` получил параметры `fmt` (подстановка `{title}/{roles_desc}`,
  JSON-скобки в .md удвоены `{{}}`) и `extra` (dept-хинты дописываются после Brief).
  Лог идёт с реальной ролью лидера (`cto`/`cmo`/`sales_lead`).
- **Сервисные роли**: `researcher._SYSTEM_QUICK/_DEEP` → `researcher_{quick,deep}.md`;
  `strategist.SYSTEM_PROMPT` → `strategist.md`; `architect.SYSTEM_PROMPT` → `architect.md`.
  У strategist/architect включён слот Brief — **закрыт латентный баг**: system стратега
  упоминал «цель клиента», но `goal` в user НЕ передавался; теперь его приносит Brief-слот.
- **Онбординг** (`_QUESTIONS_SYSTEM/_BRIEF_SYSTEM`) → `onboarding_{questions,brief}.md`,
  `with_brief=False` (бриф ещё формируется).
- **Критик** (`critic.review_site_llm` inline-`sys`) → `critic_site_review.md`,
  `with_brief=False` (niche/audience/goal уже сериализуются вручную из аргументов;
  литеральные `{niche}` и JSON `{"fixes":…}` в .md сохранены — `.format` не вызывается).

**Итог Phase 1a:** `grep 'SYSTEM = """'` по `src/agents`+`src/office` пуст; все
промпты (CEO, лидеры, сервисные, онбординг, критик) идут через `prompt_builder.
company_system` и логируются в `prompts.jsonl` с ролью. 14 policy-файлов
`policies/*.md`. Проверено: py_compile, импорт `server`+всех модулей, сборка всех
14 политик, сохранность скобок критика/онбординга. LLM не вызывался ($0).

**Дальше:** Phase 1b — Acceptance L1 (`specification.checklist()` → сверка
`success_criteria` в приёмке).

---

## ✅ 2026-07-03 (Phase 1b) — Acceptance L1 (сверка со спецификацией)

Подключён `specification` к приёмке. DoD: задача, чей `done_criterion` расходится с
контрактом (`success_criteria`), получает предупреждение в вердикте, даже если
build/functional прошли — **мягкий сигнал, не жёсткий гейт** (подтверждение
владельца в v1 опционально).

- Новые `specification.covers(criterion)` (сверка: точное совпадение нормализованного
  текста ИЛИ ≥60% перекрытие токенов через `needs.tokens`) и `specification.status()`.
- `acceptance.check` получил уровень **L1 `specification`** (`ok`/`warn`/`skip`) +
  список `warnings` + поле `confidence` (`high` при confirmed без замечаний, иначе
  `normal`). `passed` по-прежнему считается только по жёстким уровням (build/
  functional/acceptance) — L1 не проваливает задачу.
- `loop`: при пройденной приёмке с замечанием L1 — сообщение «⚠ принята с
  замечанием…», warnings пишутся в trace и в вердикт задачи (виден в UI/History).

Спецификация формируется в bootstrap (`loop.py:256`, `specification.ensure()`),
собирается из done_criterion задач плана — критерии ИСХОДНЫХ задач покрыты по
построению; предупреждение ловит задачи, добавленные ПОЗЖЕ (делегирование/
директива/инициатива/fix) вне согласованного объёма.

Проверено: py_compile, импорт `server`, смоук L1 (совпадение→ok; расхождение→warn
при passed=True; confirmed→confidence high). LLM не вызывался ($0).

**Phase 1 (a+b) закрыт.** Дальше по карте — Phase 2 (Capability + Artifacts).

---

## 🧩 2026-07-03 (Phase 2) — Capability + Artifacts

Начата Phase 2. Сделаны 2a-i (Artifacts) и 2b (Capability); 2a-ii (структурная
тяжесть критика) осознанно отложена внутри фазы.

### 2a-i — Artifacts-декларации (коммит отдельно)
`task.artifacts` (site/bot/integration/doc) — единый источник для мьютекса и
приёмки вместо словесных эвристик в момент потребления. `plan._derive_artifacts`
(единая точка вывода), `artifacts_of()`, `touches_site` читает декларацию; удалён
`_NON_SITE_WORDS`. `acceptance._is_site_task/_is_bot_task` читают декларацию;
удалены `_SITE_WORDS/_BOT_WORDS`. Закрыт QA-баг (developer-задача без site-слов).

### 2b — Capability registry
- Новый `office/capability.py`: реестр «умеем/не хватает под план/можно
  подключить». Каталог способностей (landing_site — платформенная; telegram_bot/
  email/spreadsheet/repo/calendar — за интеграциями). Статус = have/missing/
  available из пересечения `plan` (декларации) ∩ `integrations.registry`. `missing()`
  — нехватка как РЕШЕНИЕ приобрести (метод: connect_integration/ask_user), а не
  строка в ленте.
- `task.required_capabilities` — декларация (явная из LLM-плана или
  `capability.derive_required`, единая точка). `plan._required_caps`.
- `execution_policy.missing_for_plan` теперь тонкий делегат к `capability.missing()`;
  удалены дублирующие `_TASK_CAPABILITY`/`required_capability`. `loop`-гейт обновлён.
- **Эндпоинты**: `/api/capabilities` теперь отдаёт РЕЕСТР способностей (не режимы
  качества); режимы качества переехали на `/api/quality-modes` (GET+POST). Фронт
  (`App.tsx`, `CompanyView.tsx`) перенаправлен + **пересобран** (`static/webapp`,
  bundle `index-BFuTqMk5.js`) — служимое приложение не сломано.

Проверено: py_compile, tsc (0 ошибок), npm build, импорт `server`, смоук реестра
(telegram_bot→missing/connect_integration; landing_site→have) и `missing_for_plan`.
DoD-grep `_NON_SITE_WORDS|_SITE_WORDS|_TASK_CAPABILITY` пуст. LLM не вызывался ($0).

### 2a-ii — структурная тяжесть критика (готово, коммит отдельно)
Проблема критика теперь `{code, severity, text}` — тяжесть объявляется В МЕСТЕ
обнаружения, а не угадывается подстрокой в русской фразе.
- `critic.check_site/check_bot/review_site_visual/review_site_llm` → `list[dict]`;
  каждый append обёрнут `_p(code, severity, text)` (severity ∈ critical|cosmetic),
  severity выставлена так, чтобы сохранить прежнее поведение `_CRITICAL_MARKERS`.
- `is_critical(p)` → `p["severity"]=="critical"`; **константа `_CRITICAL_MARKERS`
  удалена**. Новый `critic.text_of(p)` — текст (устойчив к строковому легаси).
- `critique_text/critique_text_bot` и все потребители (`acceptance`, ~8 мест в
  `loop`) печатают через `text_of`. bot-проблемы все `critical`; llm-ревью и
  overflow/alt/дубли/lang — `cosmetic`.
- Смоук на реальном мини-сайте: no_form/no_viewport→critical, no_styles/no_lang→
  cosmetic; приёмка сайт-задачи с critical → functional fail.

**Phase 2 закрыта полностью.** DoD-grep `_NON_SITE_WORDS|_SITE_WORDS|_BOT_WORDS|
_CRITICAL_MARKERS` — только `plan._BOT_WORDS` (единая точка вывода артефактов/
маршрутизации, НЕ consumption-эвристика) и один комментарий в critic. `/api/
capabilities` = реестр способностей. Дальше по карте — **Phase 3 (Measurement Layer)**.

---

## 📊 2026-07-03 (Phase 3) — Measurement Layer

Замыкает вход измерительного полукруга: числа о бизнесе с пометкой источника
(факт|оценка). Разблокирует Gap Analysis и L4-приёмку (Phase 4).

### 3a — типизированный Brief
- `onboarding._parse_economics(text)` — best-effort разбор ответа про оборот/чек в
  `(budget, avg_check)`: по ключевым словам рядом с числом («чек/средний»→чек,
  «бюджет/оборот/…»→бюджет), затем остаток по убыванию. None, если числа нет.
- `build_brief_structured` пишет `budget_usd`/`avg_check_usd` (сырой ответ остаётся
  в `assets` для совместимости). `brief.avg_check()`/`brief.budget()` — аксессоры.

### 3b — Measurement v1
- Новый `office/metrics.py`: `current()` (чистое чтение leads+brief) — `leads_total`
  и `leads_7d` (факт), `revenue_proxy_7d` = лиды×чек (**оценка**, только если чек
  известен). `record/collect/series/latest` — журнал `metrics.json` (тренд).
- `leads.count_since/count_last_days` — фактическая метрика «заявки/неделю».
- `objectives.ensure_leads_objective()` — авто-создание ИЗМЕРИМОЙ цели «Заявки в
  неделю» (`measured_by="leads.count() за 7 дней"`) при первой публикации сайта,
  идемпотентно. `objectives.measurable()` больше не пуст без владельца.
- `world.snapshot()` получил раздел `metrics` (ts снят — иначе `world.diff` шумел бы
  метриками на каждом срезе).
- `loop._publish_site_auto`: первая публикация → авто-Objective + `metrics.collect()`.
  Лид (`/api/lead`, `/api/site-lead`) → `metrics.collect()` (тренд пополняется фактом).
- Эндпоинт `GET /api/metrics` (current + series).

DoD: `/api/world` содержит непустой `metrics`; `objectives.measurable()` ≥1 без
ручного создания. Смоук: parse (500000/3000), revenue_proxy=оценка (2×15000=30000),
авто-Objective идемпотентен, world.diff по метрикам пуст при неизменных лидах. $0.

**Дальше:** Phase 4 (Gap Analysis + перепланирование + Acceptance L4).

---

## 🎯 2026-07-03 (Phase 4) — Gap Analysis + перепланирование + Acceptance L4

Замыкает измерительный полукруг: система из честного Bootstrapping-режима
переходит к Steady State (сама находит работу к цели).

- Новый `office/gap.py`: `compute()` — для каждой `objectives.measurable()` сравнивает
  текущую метрику (резолвер `measured_by`→`metrics.latest`, пока «заявки/лиды»→
  `leads_7d`) с числом из `desired`. `gap = desired − current`, `met = gap≤0`.
  Всё ВЫЧИСЛИМО, не «ощущение CEO». `unmet()`, `context_block()`, `replan()`.
- `world.context_block()` получил раздел «РАЗРЫВЫ ДО ЦЕЛЕЙ» — CEO видит их наравне
  с блокерами (подмешивается в `decide_company` через world.context_block).
- **Перепланирование (Steady State)**: `loop` при выполненном плане, ДО «жду
  указаний», зовёт `gap.replan()` — детерминированный маппинг разрыва в работу
  («заявки»→задача marketer «усилить привлечение»). Дедуп `requested_by=gap:<oid>`
  (одна авто-задача на цель — не спамит; endless-retry — горизонт Phase X). Есть
  разрыв → офис ставит задачу и продолжает, а не засыпает.
- **Acceptance L4 (Business)**: для задач-поставок (artifacts site/bot) вердикт
  получает уровень `business` (ok|open|skip) + предупреждение «цель ещё не
  достигнута (current/desired) — работа сдана, но разрыв открыт». Информационный,
  НЕ гейт (попадание в цель наполняется метрикой ПОСЛЕ сдачи).
- Эндпоинт `GET /api/gap`.

DoD: тенант с закрытым планом и целью «10 заявок/неделю» при 3 фактических лидах
получает задачу от CEO без владельца; Bootstrapping→Steady State воспроизводится.
Смоук: gap 3/10=7 (не met); replan→1 задача marketer, идемпотентно; world содержит
«Разрывы»; L4 business=open, passed не падает. LLM не вызывался ($0).

**Дальше:** Phase 5 (Decision-as-diff + Sandbox) / Phase 6 (Execution Policy split).

---

## Запуск / проверка
```bash
pip install -r requirements.txt
python -m uvicorn server:app --reload          # http://localhost:8000 → /webapp/
DEMO_MODE=1 python -m uvicorn server:app --reload   # демо без логина-гейта на /api
cd webapp && npm run build                      # сборка фронта в static/webapp
```
Проверка перед коммитом: `python -m py_compile $(git ls-files '*.py')`.
Локально порт 8000 может быть занят фантомным сокетом — бери другой (напр. 8123).
