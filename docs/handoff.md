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

## ⚖️ 2026-07-03 (Phase 5) — Decision Engine как diff + Sandbox

Решение владельца больше НЕ мутирует план напрямую — проходит транзакцию
`propose → check → apply|reject` (BOS §14 п.3). Единственное серьёзное
несоответствие инварианту закрыто.

- Новый `office/sandbox.py` — **универсальный механизм** `run(subject, change,
  checks) -> {ok, checks, vetoed_by}` (BOS §9, engineering-principles §7: механизм,
  не сущность под каждый случай). Sandbox НЕ применяет change к миру — клонирует
  срез, прогоняет проверки, выносит вердикт; merge/discard решает потребитель.
- Новый `office/decision_engine.py` — первый потребитель Sandbox. `PlanDiff`
  {add_tasks, milestone_ops, remove_tasks, dept_ops}; `decide(diff)` =
  propose→check→apply|reject. Три ДЕТЕРМИНИРОВАННЫХ проверки-вето:
  - **бюджет** (`costs.would_exceed` по сумме `estimate_cost` задач),
  - **конфликт артефактов** (site-задача, пока site в работе — мьютекс Phase 2 по
    декларации),
  - **вето Конституции** (платный конструктор Tilda/BotsBox/… без одобрения ИЛИ
    явное правило владельца «не …»). Раньше запрет жил только текстом в промпте
    CEO — LLM могла проигнорировать; теперь код не может.
- `decisions.record` расширен: `status` (applied|rejected), `plan_diff`, `checks`,
  `reject_reason` — отклонённое решение видно в `/api/decisions`.
- `server` (`/api/chat` steer-ветка): директива → PlanDiff → `decision_engine.decide`
  вместо прямой мутации плана/вех. Отклонение показывается владельцу в ленте
  («цену выбора», BOS §2: автономность — торговля, не саботаж).

DoD: директива проходит propose→check→apply|reject, не пишет план напрямую;
отклонённое (бюджет/Tilda) видно в /api/decisions с причиной. Смоук: обычная
директива→applied+задача; Tilda→veto Конституции; крошечный лимит→veto бюджета;
отклонённое в журнале со статусом+причиной; пустой diff — не решение. $0.

**Осталось (осознанно):** `decide_company` меняет ОРГструктуру (open/close/delegate)
напрямую — Phase 5 DoD про директиву владельца (сделано); оргрешения структурны и
ниже риском, кандидат на ту же транзакцию в отдельном шаге. `remove_tasks`/`dept_ops`
в PlanDiff зарезервированы (директивы их пока не порождают).

**Дальше:** Phase 6 (Execution Policy на Capability + расслоение loop.py) — финал карты.

---

## 🧱 2026-07-03 (Phase 6, шаг 1) — расслоение loop.py: Planning Engine

Финальная фаза карты — расслоение бог-модуля `loop.py` (был 1404 строки). Самая
рискованная (механическая экстракция + общее мутабельное состояние живости) и
нижняя по User Value (⭐⭐⭐/❌). Делается безопасными срезами.

**Шаг 1 (сделано):**
- Новый `office/planning_engine.py` — чистые детерминированные функции планирования/
  маршрутизации, вынесенные из loop: `fallback_plan`, `has_actionable_move`,
  `dept_actionable`, `has_orphan_tasks`, `free_worker_of_role` + константа
  `AGENT_COOLDOWN_SECS`. Нет замыканий цикла и мутабельной живости → **покрыт
  unit-тестами без поднятия офис-цикла**.
- Классификаторы ошибок провайдера `_is_quota_error`/`_is_model_unavailable_error`
  → `core/llm.py` (`is_quota_error`/`is_model_unavailable_error`) — знание об ошибках
  LLM живёт в Provider-слое, не в бизнес-цикле (audit #14 закрыт). `loop` импортирует.
- **Первые тесты в проекте**: `tests/test_planning_engine.py` (runnable
  `python tests/test_planning_engine.py`) — fallback детерминизм, orphan-задачи,
  классификаторы. 3/3 проходят, $0.
- `loop.py`: 1404 → 1288 строк. Импорт `server`+`loop` ок, алиас кулдауна сохранён.

**Осталось для DoD `loop.py < 400` (следующие шаги, осознанно отложено):**
- `office/execution.py` — жизненный цикл `_job` (Policy→бюджет→run_agent→приёмка→
  эскалация). **Блокер:** `_job` — ВЛОЖЕННОЕ ЗАМЫКАНИЕ внутри `_assign`, захватывает
  контекст цикла; чистая экстракция требует рефакторинга в объект-состояние, а живой
  цикл нельзя протестировать здесь (нет LLM/прогона) — большой риск, отдельный шаг.
- Остаток маршрутизации (`_run_leaders`/`_hire_leader`/`_orchestrate`/
  `_apply_company_decision`) и bootstrap-оркестрация → `execution.py`/шедулер.
- `agent_id → worker_id` (миграция схемы+фронта с deprecated-алиасом) — не начата.

**Дальше:** довести расслоение (execution.py) отдельными безопасными срезами.

## 🧱 2026-07-03 (Phase 6, шаг 2) — Execution вынесен из loop.py

Продолжение расслоения. Вынесен весь жизненный цикл ИСПОЛНЕНИЯ одной задачи.

- Новый `office/execution.py` — машина состояний исполнения: `assign`, `run_task`
  (Policy→бюджетный гейт→run_agent→приёмка→эскалация), `heal_stuck_agents`
  (watchdog), `review_and_maybe_fix`, `publish_site_auto`, `task_with_context`,
  `attribute_result`, `engagement_needs_bot`. Владеет состоянием живости
  (`_thinking_since`/`_agent_task`/`_model_fail_count`/`_current_ms`) — теперь оно в
  ОДНОМ месте, а не размазано по циклу.
- **Ключевое: `_job` (вложенное замыкание в `_assign`) чисто рефакторено в модульную
  `run_task(agent_id, role, task, …)`** — оно захватывало только параметры `_assign`,
  скрытых локалей не было, поэтому конверсия в функцию с явными параметрами
  безопасна. Привязка `_agent_task` перенесена внутрь `assign` (call-sites цикла
  больше её не трогают).
- `loop` импортирует `execution` (одностороннее направление; `execution` НЕ импортирует
  `loop`). Циклы разорваны: `_goal→brief.effective_goal()` инлайн, `set_cur_ms`/
  `forget_tenant` — вызовы в execution.
- `tests/test_execution.py` — 4 теста (tk-изоляция, current_ms, forget_tenant чистит
  живость, engagement_needs_bot). Оба тест-файла: **7/7 проходят**, $0.
- **`loop.py`: 1288 → 764 строки** (суммарно с шага 1: 1404 → 764, вынесено 640).

**Осталось до DoD `loop.py < 400`:** ещё вынести маршрутизацию лидеров
(`_run_leaders`/`_hire_leader`), CEO-оркестрацию (`_orchestrate`/
`_apply_company_decision`) и bootstrap (`_bootstrap`/`_hire_initial`/`_hire_and_run`)
— в `planning_engine`/отдельный `bootstrap`-модуль. `_run_office` (главный цикл ~180
строк) остаётся ядром шедулера. `agent_id → worker_id` — не начата.

Проверено: py_compile всего дерева, импорт server+loop+execution, оба тест-файла,
смоук помощников execution. Живой офис-цикл здесь не гоняется (нет LLM) — риск
поведенческой регрессии в run_task/assign остаётся, но код перенесён дословно
(diff — только имена: `_job`→`run_task`, `_tk`→`tk`, доступ к состоянию через модуль).

## 🎯 2026-07-03 (Phase 6, шаг 3 — финал) — loop.py < 400: DoD достигнут

Завершение расслоения. Вынесены маршрутизация лидеров, CEO-оркестрация и
единоразовый bootstrap — последние крупные блоки бог-модуля.

- **Новый `office/bootstrap.py`** — единоразовый запуск тенанта: `hire_initial`
  (наём CEO+штаба), `run` (ресёрч→стратегия, был `_bootstrap`), `strategy_text`/
  `save_strategy` (были `_strategy_text`/`_save_strategy`). Собственный
  `BOOTSTRAP_STEP_TIMEOUT` (был в loop.py) — на него по-прежнему ссылается
  архитектор-шаг, оставшийся в `_run_office` (`bootstrap.BOOTSTRAP_STEP_TIMEOUT`).
- **`office/planning_engine.py` расширен** маршрутизацией и CEO-оркестрацией:
  `orchestrate`/`apply_company_decision`/`run_leaders`/`hire_leader`/`hire_and_run`
  (были `_orchestrate`/`_apply_company_decision`/`_run_leaders`/`_hire_leader`/
  `_hire_and_run`) + `verify_and_fix_if_needed` (был `_verify_and_fix_if_needed` —
  попутно убран мёртвый параметр `strategy`, нигде не читался в теле). Модуль
  теперь владеет анти-цикл состоянием `_last_leader_sig`/`_LEADER_REPEAT_LIMIT`
  (было в loop.py) — тот же класс SSOT-долга, что живость исполнения в
  `execution.py` (engineering-principles №2, признано и отложено «после пятёрки
  ядра» согласно BOS §13). Docstring модуля переписан честно: он больше не «только
  чистые функции без побочных эффектов» — теперь два слоя (чистые помощники +
  маршрутизация с publish/LLM), последняя тестируется только живым прогоном.
- `_goal()` (тонкий алиас `brief.effective_goal()`) убран — инлайнен на местах
  вызова (тот же приём, что уже применялся при выносе `execution.py`).
- **`loop.py`: 764 → 324 строки. DoD `< 400` из дорожной карты выполнен.**
  Импорты вычищены: из loop.py ушли `org/lessons/critic/workspace/sites/knowledge/
  trust/decisions/autonomy/initiatives/board/models_module` и agent-модули
  `researcher/strategist/leaders/agent_factory` — они были нужны только
  перенесённому коду и теперь импортируются самими `bootstrap.py`/
  `planning_engine.py`. loop.py импортирует три подсистемы одностороннее
  (bootstrap/planning_engine/execution → ни одна из них не импортирует loop).
- **Внешний потребитель обновлён**: `server.py` (`_steer_from_chat`) звал
  `office_loop._strategy_text()` — переведён на `office_bootstrap.strategy_text()`.
  Комментарии в `orchestrator.py`, ссылавшиеся на `loop._run_leaders`
  (теперь неверно), поправлены на `planning_engine.run_leaders`.
- **Новые тесты** в `tests/test_planning_engine.py`: `verify_and_fix_if_needed`
  (дедуп fix-задачи + критичность через реальный `workspace`/`critic`, без LLM),
  `hire_leader` (регистрация + анти-дубль), `forget_tenant` (чистит только свой
  тенант). `orchestrate`/`run_leaders`/`apply_company_decision` НЕ покрыты юнитами
  осознанно — вызывают `orchestrator.decide_company`/`leaders.decide` (LLM) и/или
  планируют фоновый `execution.assign` (реальный LLM-вызов в фоне) — тестируются
  только живым прогоном офиса.
- **Итог по обоим тест-файлам: 11/11 проходят** (было 7/7 до этого среза).

Проверено: py_compile всего дерева, импорт `server`+`loop`+`execution`+
`planning_engine`+`bootstrap`, repo-wide grep на остаточные ссылки на все
перенесённые приватные имена (`loop._run_leaders`/`_hire_leader`/`_orchestrate`/
`_apply_company_decision`/`_bootstrap`/`_hire_initial`/`_hire_and_run`/
`_verify_and_fix_if_needed`/`_strategy_text`/`_save_strategy`/`_last_leader_sig`) —
только исправленные комментарии, кода не осталось. LLM не вызывался ($0).

**Phase 6 закрыта. Дорожная карта (`docs/дорожная_карта.md`) пройдена целиком:
Phase 0 → 0.5 → 1 → 2 → 3 → 4 → 5 → 6.** Осознанно отложенное (не входило в DoD
ни одной фазы, зафиксировано ранее с обоснованием): `agent_id → worker_id`
(терминологическая миграция схемы+фронта), перевод `decide_company` (структура
отделов) через тот же `decision_engine`, что и директивы владельца (Phase 5 закрыла
только путь директивы, оргрешения остаются прямой мутацией — низкий риск,
кандидат на объединение в отдельном шаге), Phase X (Learning Engine) — по дизайну
не реализуется сейчас.

---

## 🏷 2026-07-03 — agent_id → worker_id (терминологическая миграция)

Последний пункт из списка «осознанно отложено» закрыт. **Важное решение по
объёму:** BOS-глоссарий (`bos-architecture.md` §1) явно пишет про Worker
«внутренний термин "агент" допустим только в коде» — т.е. полное переименование
~40 файлов (`registry.AgentRecord.agent_id`, параметры функций во всех
`office/*.py`/`agents/*.py`, ключи в `agents.json`/`plan.json`/`threads.json` на
диске у существующих тенантов) НЕ требуется спекой и было бы инвазивным
изменением с нулевой добавленной архитектурной пользой (риск регрессии + нужна
миграция данных существующих тенантов — ради переименования того, что спека
прямо разрешает оставить как есть).

**Реальный долг — это утечка термина в контракт** (API/фронт), который видят
внешние потребители. Мигрирован именно контракт, внутренние Python-идентификаторы
не тронуты:

- **`office/bus.py`** — `publish()` зеркалит `worker_id` рядом с `agent_id` в
  ОДНОЙ точке, через которую проходят ~40 мест кода, публикующих события
  (agent_factory/execution/planning_engine/bootstrap/chat/server) — не пришлось
  трогать ни один из них по отдельности. `agent_id` остаётся deprecated-алиасом
  (значения идентичны), решение не мутирует чужие dict на входе.
  `state.record()` (персистентная лента) получает уже смёрженное событие —
  новая история тенантов пишется сразу с `worker_id`.
- **`server.py`** — новый `_with_worker_id()` (dict/список dict) применён в
  местах, которые формируют ответ НАПРЯМУЮ (не через `bus.publish`): SSE-снапшот
  при коннекте, `/api/agents`, `/api/agent/{id}` (+ вложенные `done`/`activity`),
  `/api/agent/{id}/model`, `/api/thread/{id}`, `/api/deliverables`, `/api/costs`.
  `/api/ask` — request body читает `worker_id` с фолбэком на `agent_id`
  (`data.get("worker_id") or data.get("agent_id")`), обе response-ветки тоже
  зеркалят `worker_id`. URL-роуты (`/api/agent/{agent_id}`, path-параметры) НЕ
  переименованы — это был бы breaking change для существующих клиентов, и
  роадмап его не просил.
- **Фронт**: `webapp/src/app/types.ts` — `Agent`→`Worker`, `AgentStatus`→
  `WorkerStatus` (поле `id` уже было терминологически нейтральным, не трогал).
  Три потребителя типа (`OfficeProvider.tsx`, `OfficeView.tsx`, `TeamView.tsx`)
  обновлены. `roles.ts`: `agentDisplayName`→`workerDisplayName`. `OfficeProvider.
  tsx` — все чтения `e.agent_id`/`a.agent_id` из SSE/API заменены на helper
  `wid(o) => o.worker_id ?? o.agent_id` (нужен фолбэк по-настоящему: уже
  сохранённая на диске история старых прогонов, записанная ДО этого фикса,
  содержит только `agent_id`). `api.ts` — `ask()` шлёт `worker_id` первым,
  `thread()` типизирован с обоими полями. Внутренние переменные/пропсы (`agent:
  Worker`, компонент `AgentDetailModal`) НЕ переименованы — это локальные
  идентификаторы кода, не контракт.

Проверено вживую: py_compile + tsc + `npm run build` (0 ошибок); backend-смоук
(`bus.publish` мёржит `worker_id`, не трогает событие без `agent_id`, не
затирает уже выставленный `worker_id`); **реальный прогон в браузере** —
залогинился dev-логином, вручную зарегистрировал воркеров (без LLM), затем
включил реальный офис-цикл на секунды (bootstrap+architect на автомате,
$0.0039, сразу поставлен на паузу) — карточки CEO/Разработчик рендерятся,
Digest показывает работу ресёрчера/стратега, чат открывается по клику, консоль
браузера чистая; curl-проверка `/api/thread/{id}` и `/api/ask` (только
`worker_id`, без `agent_id`, включая проверку на несуществующем id — дошло до
`registry.get()`, а не до валидации отсутствия поля) подтвердила, что бэкенд
реально читает новое поле, а не просто не падает. Тестовый тенант и
пользователь удалены (`ctx.wipe()` + DELETE из users/workspaces), сервер-процесс
остановлен. Расход $0.0039 (7237/1506 токенов, 5 вызовов) — сознательная,
минимальная плата за проверку живым прогоном, а не моком.

**Не переименовано (осознанно, см. рассуждение выше):** внутренние Python-
идентификаторы во всех `office/*.py`/`agents/*.py` (легитимный код-термин по
BOS-глоссарию); ключи `agent_id` в персистентных JSON-схемах тенантов
(`agents.json`, `plan.json.assignee`, `threads.json` — переименование потребовало
бы миграции данных существующих тенантов без внешней пользы); URL-пути `/api/
agent/{id}` (breaking change, не запрошен); имя компонента `AgentDetailModal`
(файл/имя компонента, не контракт).

---

## 🏦 2026-07-03 (Due Diligence, вечер) — переоценка после Phases 0–6

По `docs/анализ_промпт.md` проведён DD-аудит (26 разделов + Code Map, полный текст
в диалоге сессии, файлом не сохранён). Ключевое для следующих сессий:

- **Соответствие BOS: ~70%** (утренняя оценка «~45%» в разделе архитектурной
  ревизии выше — УСТАРЕЛА, она была ДО реализации фаз). Оба полукруга цикла §3
  замкнуты v1: metrics→gap→replan работает, decision-as-diff с детерминированным
  вето работает, observability сшита.
- **Критический security-долг, блокирует внешних клиентов:** `/api/terminal` и
  `execute_code` исполняют произвольный код с правами процесса БЕЗ изоляции —
  аутентифицированный пользователь может читать данные чужих тенантов
  (`cat ../../<tid>/connections.json`), .env и т.д. Изоляция данных образцовая,
  изоляция ИСПОЛНЕНИЯ отсутствует. Фикс v1: фичефлаг оператора на оба эндпоинта.
  Плюс: `APP_SECRET` в .env — дефолтная dev-строка.
- **Новый долг, порождённый самими фазами 4–5** (назван прямо): словесные
  эвристики второго поколения — `decision_engine._FORBIDDEN_CONSTRUCTORS` +
  substring-парсер custom_rules, `gap._work_for_gap` (одна ветка),
  `capability._NEED_WORDS` и захардкоженный `_CATALOG` (не derived из
  integrations.registry). Тот же класс, что выпилен в Phase 2. Правило ревью:
  новый `_WORDS`-список требует обоснования.
- Прочее высокоприоритетное: Artifact-реестр (следующая сущность — блокирует
  мультипроектность), `ctx._cache` без потолка (память при сотнях тенантов),
  синхронные subprocess (node/playwright/py_compile) в event loop, CI на
  существующие проверки (py_compile+tsc+11 тестов) не заведён.
- CTO-шаги «завтра утром»: фичефлаг terminal/execute_code + CI — до обеда;
  тикет Artifact-реестра — после.

---

## 🔒 2026-07-03 — Фикс критического security-долга: execute_code/run_command

Закрыт пункт №1 из «CTO-шагов завтра утром» DD-аудита (§17). Первопричина не
устранена (нет реальной песочницы), но риск заблокирован по умолчанию — v1-фикс,
ровно как рекомендовал аудит.

- **`workspace.py`** — единая точка правды: `code_execution_allowed()` (читает
  `ALLOW_CODE_EXECUTION`, default `"0"` → **выключено**) + `_DISABLED_MSG`. Гейт
  внутри `execute_code()`/`run_command()` — работает и для HTTP, и для LLM-tool
  вызова одним и тем же кодом, поэтому обход через инструмент агента исключён.
- **`server.py`** — `/api/run` и `/api/terminal` возвращают явный **HTTP 403**
  с `{"ok": false, "error": "code_execution_disabled", "output": <причина>}` ДО
  чтения тела запроса, если флаг выключен (не полагаемся только на текст `❌` —
  честный код ответа для внешних потребителей API).
- **`agent_factory.py`** — `_EXECUTE_CODE_TOOL` убирается из каталога инструментов
  ЦЕЛИКОМ при выключенном флаге (не просто блокируется вызов) — LLM не видит
  и не пытается вызвать действие, которое всё равно отклонят: экономия
  токенов/итераций и меньше шума в логах.
- **Фронт** (`FileExplorer.tsx` — вкладка «Код», запуск файла + встроенный
  терминал): новый `api.postJSONReadBody` (в `api.ts`) читает JSON-тело ответа
  даже при `!ok` — раньше `postJSON` подменял 403 generic-фолбэком «Ошибка
  запроса», теряя понятную причину отказа. Обычный `postJSON` НЕ тронут (много
  других мест полагаются на его текущее поведение при ошибке — риск не оправдан).
  Пересобран `static/webapp` (bundle `index-BnKg4jBp.js`).
- **`.env.example`** + **`CLAUDE.md`** (конфиг-блок) — документирован
  `ALLOW_CODE_EXECUTION=0` с явным предупреждением «включай только за реальной
  песочницей». Боевой `.env` НЕ трогал (там нет этой переменной — значит default
  `"0"` уже действует, ничего включать не пришлось).

Проверено: `py_compile` всего дерева, `tsc --noEmit` (0 ошибок), `npm run build`,
11/11 существующих тестов (не сломаны). **Живой прогон в браузере через
`DEMO_MODE=1`** (без реального LLM-вызова, $0): сервер на порту 8123 (флаг
выключен) — `curl /api/run` и `/api/terminal` вернули `HTTP 403` с понятным
текстом причины; второй сервер на 8124 (`ALLOW_CODE_EXECUTION=1`) — та же
команда через `/api/terminal` выполнилась как раньше (`HTTP 200`, реальный
вывод) — подтверждено отсутствие регрессии при явном opt-in. Оба тестовых
процесса найдены по занятым портам (`Get-NetTCPConnection`) и остановлены
именно по PID — `pkill` в git-bash их не поймал, т.к. это Windows-процессы вне
дерева bash-джобов (см. `MEMORY.md`: kill по PID, не полагаться на pkill).

**Не в объёме этого фикса (осознанно, отдельные задачи):** реальная песочница
исполнения (контейнер/gVisor) — устраняет первопричину, а не только блокирует
по умолчанию; `APP_SECRET` — дефолтная dev-строка в закоммиченном `.env`
(отдельная находка аудита, не трогал); `.env` уже отслеживается git с реальными
секретами (`LLM_API_KEY`, OAuth-секреты) — требует отдельного решения
(BFG/history rewrite + ротация ключей), не входит в «фикс терминала».

---

## 🐛 2026-07-03 — Баг «офис молча замирает»: подстрока «бот» ловила «работать»

Разбор прод-лога (`ai-office-log-20260703_192029.txt`, ниша натяжных потолков):
после ~26 минут работы офис перестал публиковать что-либо в ленту (полная
тишина с 19:16:49 до дампа лога в 19:20:28, без единого сообщения) — то, что
пользователь увидел как «всё зависло».

**Корневая причина.** `_BOT_WORDS`/аналогичные списки в 4 местах матчили «бот»
как ГОЛУЮ подстроку — а «бот» является корнем слов «раБОТать», «доработать»,
«обработать», «заработать», «отработать» и т.д. Gap-driven авто-задача
(`gap._work_for_gap`, Phase 4) сама генерирует заголовок «Усилить привлечение
заявок: **дораБОТать** оффер и CTA лендинга…» — то есть система создала себе
задачу, которая ЛОЖНО матчилась на собственное правило: `plan._derive_artifacts`
пометил её `artifact=bot`, `acceptance.check` потребовал `bot.py` с
aiogram/BOT_TOKEN у чисто маркетинговой задачи (доработать текст оффера), 3
провала приёмки подряд → задача **заблокирована**. К этому моменту у обоих
открытых отделов не осталось PENDING-задач (только эта, blocked) →
`planning_engine.has_actionable_move()` вернул `False` **навсегда** — а
`orchestrate()` (CEO-гейт, event-обработка, gap-replan) вызывается ТОЛЬКО когда
`has_actionable_move()` истинен, поэтому цикл просто спал по 10с бесконечно, не
публикуя вообще ничего. `gap.replan()` тоже не спасал: он вызывается только
внутри `_engagement_complete()`, а blocked-задача (не done/skipped) держит
engagement «незавершённым», так что ни одна из двух веток прогресса не срабатывала.
Отдельно этот же баг заставлял `execution.engagement_needs_bot()` (сканирует
ВСЕ заголовки плана) ложно включать бот-проверку и для last designer'а задач
(видно в логе: «🔁 Бот проверен — нужны правки» на чисто сайтовой правке).

**Фикс.** Единая точка `needs.is_bot_reference(text)` (`office/needs.py`) —
регэксп с негативным lookbehind: `бот` матчится, только если ему НЕ предшествует
кириллическая буква (ловит «бот», «бота», «боту», «чат-бот», «телеграм-бот»;
НЕ ловит «работать/доработать/обработать», где «бот» — середина корня).
`telegram`/`aiogram`/`chatbot`/`чат-бот`/`телеграм` остались обычными
подстроками (они не пересекаются с частыми русскими словами). Заменены 4 места:
`plan._route_role`/`plan._derive_artifacts` (было `_BOT_WORDS`),
`execution.engagement_needs_bot`/`execution.review_and_maybe_fix` (было
`("бот","bot","telegram","телеграм")`), `capability.derive_required` (было
`"бот"` в `_NEED_WORDS["telegram_bot"]`, вынесено в отдельный вызов
`needs.is_bot_reference`).

**Новый тест** `tests/test_needs.py` (3 теста, воспроизводит РЕАЛЬНЫЙ заголовок
из инцидента + проверяет, что настоящие бот-упоминания по-прежнему детектятся).
Все тест-файлы: **14/14 проходят** (было 11/11). Проверено: `py_compile`, импорт
`server`, ручной прогон точного заголовка из лога.

**Не в объёме этого фикса (отдельный архитектурный вопрос, не баг):** даже без
substring-бага легитимно заблокированная задача при отсутствии другой pending-
работы у отделов всё ещё оставит `has_actionable_move()` вечно `False` —
офис корректно ждёт действия владельца (BOS §10), но делает это ПОЛНОСТЬЮ
молча (ни одного периодического «жду разблокировки X» после первого
уведомления). Пользователю в этом самом логе не помогло и то, что личный чат
с CEO трижды переспрашивал «а зачем нам бот», получая уклончивые ответы —
`interpret_directive` не знает, что есть открытый blocker, и не связывает
вопрос владельца с конкретной заблокированной задачей. Кандидат на отдельное
улучшение: периодический heartbeat при `blocked`+`not has_actionable_move()`,
и/или прокидывание списка активных blocker-ов в контекст `interpret_directive`.

---

## 💬 2026-07-03 — Кандидат из предыдущего пункта реализован: heartbeat + blocked-контекст в чате

Оба «кандидата на отдельное улучшение» из предыдущей записи сделаны.

**1. Heartbeat при простое из-за блокера** (`loop.py`):
- Новый `plan.blocked_tasks()` — единая точка чтения заблокированных задач
  (использует и цикл, и CEO-чат ниже).
- `loop._heartbeat_if_blocked(publish)`: когда `planning_engine.has_actionable_move()`
  ложно (офису реально нечего делать) и есть `blocked`-задачи — публикует
  напоминание с заголовками задач раз в `BLOCKED_HEARTBEAT_SECS` (env, default 600с),
  а не молчит навсегда. Троттлинг по `_last_blocked_heartbeat[tid]` — не спамит на
  каждом 10-секундном цикле. Не зовёт LLM (чтение доски + сравнение времени), $0.
  Подключён в главном цикле сразу после `has_actionable_move()==False`.
  `forget_tenant` чистит новый словарь вместе с остальной per-tenant живостью.

**2. Личный чат CEO видит причину блокера** (`orchestrator.interpret_directive`):
- Раньше CEO получал только счётчик `⛔N` из `board_summary` — не мог связать
  вопрос владельца («а зачем нам бот?») с конкретной задачей и причиной, отвечал
  уклончиво (ровно это видно в разобранном логе: 3 переспроса подряд без ответа
  по существу). Теперь `interpret_directive` сам читает `plan.blocked_tasks()` и
  добавляет в user-промпт секцию «ЗАБЛОКИРОВАННЫЕ ЗАДАЧИ» с заголовком+причиной
  каждой (макс. 5) + явную инструкцию модели называть задачу и причину, если
  вопрос владельца касается блокера. Сигнатура функции не менялась — `plan`
  импортируется внутри неё.

**Новый тест** `tests/test_loop_heartbeat.py` (3 теста: без блокеров тихо; при
блокере — одно сообщение с заголовком задачи + троттлинг на повторный вызов;
`forget_tenant` чистит heartbeat-состояние). **Все тест-файлы: 17/17 проходят**
(было 14/14). Проверено: `py_compile`, импорт `server`, смоук обоих сценариев
(heartbeat молчит/шлёт/троттлит; `blocked_tasks()` отдаёт причину). LLM не
вызывался ($0).

---

## 🎨 2026-07-03 — Все сайты выглядят одинаково: каталог стилей + вариативность стека

Жалоба пользователя: сайты разных тенантов визуально почти неотличимы.
Скиллы дизайна (`static_landing_site.md`, `framer_motion_3d_site.md`) УЖЕ
содержали сильный анти-шаблонный текст (даже список из трёх «AI-дефолтов»,
которых нельзя брать) — проблема не в отсутствии предупреждений, а в двух
конкретных вещах:

**Находка 1 (эмпирическая, по прод-логу):** `use_skill` designer/developer/
marketer **7 из 7 раз** матчился на `landing_conversion`, `static_landing_site`
(с его дизайн-токенами, каталогом, чек-листом качества) **не был выбран НИ РАЗУ**
за весь прогон — реальные формулировки потребности агентов ближе к словам
"лендинг/оффер/CTA" (ключевые слова landing_conversion), чем к "премиальн/стильн"
(ключевые слова static_landing_site). Проверено `skills.match()` на текстах из
лога — воспроизводится детерминированно.

**Находка 2 (корневая):** «Стиль: …» раньше был вольным полем — marketer сам
придумывал «2-3 прилагательных настроения» БЕЗ опоры, и без конкретики любая
модель для любой ниши сходится к одному и тому же («современный, чистый,
премиальный» — ровно это видно в разобранном ранее логе). Дизайнер из мутного
вайба восстанавливал один и тот же дефолтный вид.

**Фикс:**
- **Каталог из 12 именованных направлений** (палитра в hex, шрифтовая пара,
  ОДИН сигнатурный приём, подходящие ниши) перенесён в `landing_conversion.md`
  (правильное место — именно его реально читают, находка 1). Marketer выбирает
  НАЗВАНИЕ из каталога (не придумывает вольно), designer/developer декодируют
  ТО ЖЕ название в те же hex — единый источник, дрейфа нет.
- **Шаг ресёрча** перед выбором: 1 `web_search`-запрос на актуальные визуальные
  тренды под нишу — сознательно оговорено, что инструмент отдаёт ТОЛЬКО текстовые
  сниппеты (title/description/url), открыть страницу или GitHub-репозиторий из
  результатов НЕЛЬЗЯ (нет fetch/browse-инструмента у воркеров) — цель находки не
  «скопировать сайт», а поймать конкретные слова тренда для корректировки выбора.
- **Явный cross-reference** в `landing_conversion.md` → `static_landing_site.md`
  за дизайн-токенами/технической реализацией — компенсирует находку 1: даже когда
  matching выбирает только один скилл, designer/developer теперь ЗНАЮТ, что нужно
  запросить и второй явно.
- **Вариативность стека** в `static_landing_site.md`: чистый vanilla JS объявлен
  НЕобязательным — опционально одна esm.sh-библиотека без шага сборки (GSAP+
  ScrollTrigger, Motion One, Lenis, Splide) под сигнатурный приём направления, не
  «для украшения». Отвечает на прямой запрос пользователя «не делать на
  стандартном html/css/js».
- Порядок секций в `landing_conversion.md` явно назван «смысловым чек-листом, не
  шаблоном для копирования 1:1» — раньше буквально одинаковый 7-блочный порядок
  на каждом сайте усиливал ощущение шаблонности независимо от палитры.
- 🚫 Явный запрет брать «тёмный фон + один акцент» (направления 2/11 каталога)
  «для чего угодно, потому что дорого выглядит» — ровно так получился прошлый
  прод-баг («тёмно-синий+cyan/violet под любую нишу»).

**Новый тест** `tests/test_design_skills.py` (3 теста: каталог присутствует в
`landing_conversion`, реалистичный запрос designer матчится на `landing_conversion`
эмпирически, явный запрос за дизайн-токенами достаёт `static_landing_site`).
**Все тест-файлы: 20/20 проходят** (было 17/17). Проверено: `py_compile`, импорт
`server`, парсинг всех 18 .md-скиллов без ошибок, `skills.match()` на реальных
текстах из лога. LLM не вызывался ($0) — это контентная правка плейбуков,
реальный эффект на разнообразие сайтов проверяется только живым прогоном офиса
(не делался в этой сессии — дорого по токенам, эффект отложенно наблюдаемый).

**Не в объёме этой правки:** буквальный «go read this GitHub repo and copy it» —
физически невозможно без fetch/browse-инструмента у воркеров (есть только
DuckDuckGo текстовые сниппеты). Если нужна настоящая работа с визуальными
референсами (не только текстовые описания трендов) — понадобится новый
инструмент (например `fetch_url` с извлечением текста страницы), это отдельная
фича, не правка существующего скилла.

---

## 🎨 2026-07-03 (продолжение) — «сайт такой же»: LLM пропустила инструкцию, нужен self-heal

Пользователь прогнал офис ПОСЛЕ предыдущего фикса — сайт снова вышел без
видимой разницы. Разобрал новый лог: сам МЕХАНИЗМ подключения скилла сработал
(`static_landing_site` реально выбрался у designer'а — маршрутизация из прошлой
находки исправна), но по логу **слово «Стиль» не встречается вообще ни разу**.

**Что произошло:** marketer вызвал `landing_conversion` (получил каталог
направлений), но при генерации `docs/site_content.md` пропустил шаг «выбери
направление и запиши строку «Стиль: …»» — написал оффер/CTA/FAQ/квиз, строку
стиля нет. Designer прочитал файл, строки не нашёл — и per инструкции ДОЛЖЕН
был спросить `ask_colleague("marketer", ...)`, но тоже пропустил этот шаг и
сразу начал писать `site/index.html` по собственным дефолтам модели.

**Вывод:** инструкция глубоко в тексте плейбука — это СОВЕТ модели, не
гарантия; под давлением токенов/задачи необязательный шаг (тем более требующий
доп. tool-call к коллеге) реально пропускается. Текстовые правки скиллов одни
не могут закрыть проблему — нужна детерминированная подстраховка (engineering-
principles: LLM предлагает, код решает), которая срабатывает НЕЗАВИСИМО от
того, выполнит ли модель шаг.

**Фикс: `office/design_style.py`** — machine-readable зеркало 12 направлений
из каталога `landing_conversion.md` (имена совпадают 1:1, проверено тестом):
- `pick_for(niche, audience)` — стабильный выбор направления по нише через
  `hashlib.md5` (НЕ встроенный Python `hash()` — он рандомизирован по
  `PYTHONHASHSEED` между рестартами процесса, дал бы разные направления для
  той же ниши после каждого перезапуска сервера). Одна ниша → всегда одно
  направление; смоук на 6 разных нишах — 6 разных направлений (реальный разброс).
- `ensure_style_line(niche, audience)` — идемпотентный self-heal: если строка
  «Стиль: …» уже в `docs/site_content.md` (marketer справился сам) — контент не
  трогаем; если нет — детерминированно проставляем ПЕРВОЙ строкой, без LLM, $0.
- **Подключено в `execution.run_task`**: вызывается ДО старта агента для ролей
  `designer`/`developer` — гарантирует конкретное направление в файле раньше,
  чем модель вообще начнёт читать/писать сайт, независимо от того, что сделал
  или не сделал marketer.

**Новый тест** `tests/test_design_style.py` (5 тестов: детерминизм, разброс по
разным нишам, имена совпадают со скиллом, self-heal при отсутствии строки,
идемпотентность при наличии). **Все тест-файлы: 25/25 проходят** (было 20/20).
Проверено: `py_compile`, импорт `server`, смоук (6 ниш → 6 разных направлений,
self-heal и идемпотентность отдельно). LLM не вызывался ($0).

**Урок для будущих правок скиллов:** любая инструкция плейбука, критичная для
результата (не косметика), должна иметь детерминированный self-heal/проверку
на стороне кода — сам факт «модель прочитала инструкцию» не значит «модель ей
последует» под давлением токенов/итераций. Кандидат на ревью: другие «мягкие»
шаги в скиллах (например явный запрос ask_colleague при отсутствии данных) —
стоит проверить, не пропускаются ли они так же систематически.

---

## 🏗 2026-07-03 (продолжение) — Архитектор диктовал стек в обход скиллов

Пользователь указал на третий источник шаблонности (после маршрутизации скилла
и пропуска «Стиль: …»): **архитектор жёстко предписывал стек всей цепочке**.

**Аудит** (по сути — «инструмент vs обязанность», не по буквальному совпадению
строки): прошёлся по всем `builtin_roles/*.md`, `roles.py` ROLE_META, всем
`policies/*.md`. Большинство уже чисто (роли пишут обязанности/границы: «не
строй бэкенд», «не используй конструкторы», явное «КАК строить — не выдумывай,
вызови use_skill»). Найдено 2 реальных нарушения:

1. **`policies/architect.md`** — прямо предписывал «Сайт = HTML5 + CSS3 +
   Vanilla JS» как обязательный стек для типового артефакта. Механизм
   распространения: это ТЗ (`tech_design.md`) подмешивается в контекст
   КАЖДОЙ задачи воркера через `prompt_builder.task_context` («ТЗ архитектора
   [:3000]») — designer/developer видели стек как «уже решено сверху» и не шли
   в `use_skill` за реальным разнообразием приёмов (framer_motion_3d_site и
   др.). То же ТЗ ещё и попадает в `orchestrator.plan_tasks` (генерация графа
   задач) — стек архитектора неявно давил и на формулировки самих задач.
2. **`policies/ceo_plan.md`** — описание роли designer для CEO-генератора плана
   несло «(HTML/CSS/JS)» в скобках — тот же класс нарушения на уровне
   планирования, до того как вообще появляется ТЗ.

**Фикс:** архитектор теперь называет стек ТОЛЬКО для кастомной логики без
готового скилла (нестандартная интеграция, собственный сервис); для типовых
артефактов (сайт/бот) явно пишет «определяет designer/developer/integrator
через use_skill» — не диктует HTML/CSS/JS/React/Vanilla сам. Легитимные
платформенные ограничения (не строить свой бэкенд для лидов — эндпоинт уже
хостится, не использовать Tilda/Webflow, не тянуть лишние CRM/аналитику без
просьбы клиента) остались — это про ОБЪЁМ работы, не про технику вёрстки.

**Новый тест** `tests/test_no_stack_lockin.py` (2 теста: `architect.md` и
`ceo_plan.md` не содержат литералов диктата стека, архитектор явно делегирует
`use_skill`). **Все тест-файлы: 27/27 проходят** (было 25/25). Проверено:
`py_compile`, импорт `server`, точечная проверка текста обеих policy. LLM не
вызывался ($0) — контентная правка промптов, эффект проверяется живым
прогоном (не делался — дорого по токенам).

**Принцип для будущих правок (закреплён тестом):** ТЗ архитектора и
CEO-генератор плана описывают ЧТО нужно построить и КАКИЕ у этого границы
(бизнес/платформенные ограничения) — но не КАК технически это делать для
артефактов, у которых уже есть скилл. Стек/техника — только в скиллах.

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
