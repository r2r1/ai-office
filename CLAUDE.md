# CLAUDE.md

Руководство для Claude Code (и других агентов) по работе с этим репозиторием.

## Что это за проект

**AI-Office** — автономный офис AI-агентов, визуализированный как изометрическая
(псевдо-3D) браузерная игра. Агенты сами развивают бизнес клиента: исследуют рынок,
строят стратегию, проектируют техническое решение, нанимают специалистов и выполняют
задачи. Пользователь может кликнуть на любого агента и поговорить с ним, а также
писать всему офису в общий чат.

- Backend: **FastAPI** + **SSE** (Server-Sent Events) для реал-тайма.
- Frontend: один HTML + `<canvas>` с изометрическим рендерером на ванильном JS.
- LLM: любой **OpenAI-совместимый** провайдер (через `src/core/llm.py`).
- Веб-поиск: **DuckDuckGo** (бесплатно, без ключа) — не серверные тулзы провайдера,
  поэтому работает с любой моделью.

Язык продукта и комментариев в коде — **русский**. Сохраняй этот стиль.

## Запуск

```bash
pip install -r requirements.txt        # зависимости
python -m uvicorn server:app --reload  # веб-игра на http://localhost:8000
DEMO_MODE=1 python -m uvicorn server:app --reload  # демо без расхода токенов
python main.py                         # CLI: ресёрчер → стратег (без игры)
```

Конфигурация через `.env`:
```
LLM_BASE_URL=https://apinet.cloud/v1
LLM_API_KEY=sk-...
LLM_MODEL=qwen3-vl-plus
DEMO_MODE=0
LOOP_INTERVAL_SECONDS=10
```

## Проверка перед коммитом

Нет тестов и линтера. Минимальная проверка:
```bash
python -m py_compile $(git ls-files '*.py')   # синтаксис Python
node --check static/game.js                    # синтаксис JS
```
Всегда прогоняй обе после правок соответствующих файлов.

## Архитектура

### Иерархия агентов
```
Директор (orchestrator)         — НЕ работает руками; ставит задачи, ведёт этапы, нанимает
  ├── Researcher                — исследование рынка (quick/deep)
  ├── Strategist                — бизнес-стратегия, юнит-экономика, план
  ├── Architect                 — Техническое Задание (ТЗ) → reports/tech_design.md
  ├── HR                        — найм
  └── Рабочие (нанимаются):
        Salesman / Developer / Marketer / Analyst
```

### Поток работы (`src/office/loop.py`)
1. **BOOTSTRAP** (один раз): researcher (deep) → strategist → `reports/strategy.md`,
   затем architect → `reports/tech_design.md`, затем директор разбивает путь на этапы.
   Если `strategy.md` уже есть — bootstrap пропускается.
2. **ЦИКЛЫ**: каждые `LOOP_INTERVAL_SECONDS` директор (`orchestrator.decide`) принимает
   ОДНО решение — `assign` / `hire` / `wait`. ТЗ архитектора подгружается в контекст
   директора и в задачу каждого рабочего (`_task_with_context`).

### Ключевые модули `src/`
| Файл | Назначение |
|------|-----------|
| `core/llm.py` | Единый LLM-клиент (OpenAI-формат), tool-loop, web_search |
| `core/search.py` | Веб-поиск через DuckDuckGo |
| `agents/orchestrator.py` | Директор: `plan_milestones()`, `decide()` |
| `agents/architect.py` | Архитектор: `run_async()` → ТЗ, `load()` |
| `agents/strategist.py`, `researcher.py`, `hr.py` | Руководящие агенты |
| `agents/agent_factory.py` | Создаёт нанятых рабочих + их инструменты |
| `office/loop.py` | Главный автономный цикл |
| `office/registry.py` | Реестр агентов (роли, столы, статусы) |
| `office/bus.py` | Event bus для SSE |
| `office/milestones.py` | Этапы проекта и прогресс |
| `office/questions.py` | Вопросы агентов пользователю (дедуп по тексту → общий future) |
| `office/connections.py` | Хранилище API-ключей/доступов (дедуп по name+values) |
| `office/office_channel.py` | Общий чат офиса (broadcast) |
| `office/chat.py` | Личный диалог пользователя с агентом |
| `office/models.py` | Выбор LLM-модели (глобально / на агента) |
| `office/state.py`, `memory.py`, `brief.py` | Состояние, память, бриф клиента |

### Frontend (`static/`)
- `index.html` — разметка, CSS, навигация по вкладкам (Офис / Команда / Результаты /
  Доступы / События / Вопросы / Этапы / Чат).
- `game.js` — изометрический рендерер canvas.
  - Координаты: `tileToScreen(col, row)` центрирует сетку (учитывает midpoint
    `(col-row)` и `(col+row)`); `updateScale()` автоподгон под размер.
  - Примитивы: `isoFloor()`, `isoBox()`, `drawIsoTile()`, `drawIsoMap()`
    (диагональный рендер back-to-front), `drawIsoCharacter()`.
  - Камера: `camX/camY` (пан мышью), колесо — зум к курсору (`isoScale` 0.25–3.5).
  - При наведении на агента курсор → `pointer`; клик → `openChat(id)`.
  - События приходят по SSE `/events` → `handleEvent()`.
  - Роли описаны в `ROLE_COLORS` / `ROLE_ICONS` / `ROLE_NAMES` / `HAIR_COLORS` —
    **при добавлении новой роли обнови все четыре**.

### Основные HTTP-эндпоинты (`server.py`)
- `GET /events` — SSE-стрим всех событий офиса.
- `GET/POST /api/brief/*` — бриф клиента (старт работы).
- `GET /api/agents`, `/api/agent/{id}`, `/api/deliverables` — состояние.
- `GET /api/milestones`, `/api/progress`, `/api/milestone/{id}` — этапы.
- `GET/POST /api/questions`, `/api/answer`, `/api/ask` — вопросы агентов.
- `GET/POST /api/connections` — доступы/API-ключи.
- `GET/POST /api/chat` — общий чат офиса.
- `GET/POST /api/model`, `/api/models`, `/api/agent/{id}/model` — модели.

## Принципы и инварианты (НЕ ломать)

- **Автономность**: агенты НИКОГДА не просят пользователя делать ручную работу
  (создать таблицу, заполнить колонки). Если нужен внешний сервис — сначала
  `get_connection`, затем `ask_user` с инструкцией как получить API-ключ.
  Правила в `agent_factory.py` (`_AUTONOMY_RULES`).
- **Общие доступы**: любой API-ключ доступен ЛЮБОМУ агенту через `get_connection()`.
  Директор не должен выбирать конкретного агента «потому что у него ключ».
- **Лимит ролей**: не более `MAX_PER_ROLE` (=3) агентов одной роли — защита от
  бесконечного клонирования (`orchestrator.py`).
- **Дедупликация**: одинаковые вопросы агентов делят один future
  (`questions.py`); одинаковые подключения не дублируются (`connections.py`).
- **Кулдаун**: `AGENT_COOLDOWN_SECS` (=60) в `loop.py` — антидребезг, не дедлок.
- **ТЗ архитектора** — источник истины по технике. Рабочие должны следовать ему,
  а не выдумывать собственный стек.

## Стиль

- Python: следуй существующему стилю модулей (docstring на русском вверху файла,
  типы в сигнатурах, небольшие функции). Без сторонних зависимостей сверх
  `requirements.txt`.
- JS: ванильный, без сборки и фреймворков. Шрифт canvas/UI — **Inter** (не пиксельный).
- Не добавляй модель/идентификатор Claude в коммиты, комментарии или артефакты.

## Git

- Ветка разработки: `claude/practical-turing-ctg44y`. Пушить также в `main`
  (обычным fast-forward, без force) — пользователь ожидает обновление обеих веток.
- PR создавать только по явной просьбе.
