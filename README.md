# AI-Office 🏢

Мультиарендный SaaS: у каждого клиента появляется автономный AI-офис — несколько
агентов разных ролей самостоятельно ведут его бизнес (исследование рынка →
стратегия → план → реальные артефакты), а сам офис визуализирован как
изометрическая (псевдо-3D) сцена в браузере.

Клиент не ставит задачи поштучно — формулирует **цель** через онбординг или в
чате, а офис сам исследует рынок, строит стратегию и ТЗ, разбивает путь на
этапы и задачи, нанимает нужных специалистов и выполняет работу реальными
инструментами: пишет код в рабочую папку, публикует лендинги, шлёт сообщения
через интеграции, собирает живых лидов.

Подробная архитектура и правила разработки — в [CLAUDE.md](CLAUDE.md) (для
агентов/разработчиков) и [docs/bos-architecture.md](docs/bos-architecture.md)
(главная спецификация — Business Operating System).

## Возможности

- 🏢 **Изометрический офис** — живая сцена компании с агентами по столам
- 🤖 **Автономная организация** — CEO открывает отделы (tech/marketing/sales),
  нанимает специалистов, ставит им цели, а не задачи поштучно
- 🧩 **Реальные интеграции** — Telegram, Gmail, Google Sheets/Calendar, GitHub,
  Figma, Bitrix24 (вебхук и OAuth), 1С, TEST-режимы платежей/рекламы/CRM
- 🌐 **Публикация сайтов** — React+Vite сборка, хостится платформой, форма
  собирает лидов
- 💬 **Личные чаты с агентами** — кликни на любого сотрудника и поговори
- 📊 **Результаты** — реестр того, что команда произвела (лиды, сайты, дальше
  ещё типы) с персональной видимостью/порядком вкладок
- 🔍 **Веб-поиск** — через DuckDuckGo (бесплатно, без ключа)
- 🔌 **Любой OpenAI-совместимый LLM** — apinet.cloud и другие провайдеры
- 🎬 **Демо-режим** — посмотреть офис без расхода токенов

## Оргструктура офиса

```
CEO (orchestrator)        — структура компании: открывает/закрывает отделы, ставит цели
  ├── tech (CTO)          — продукт, код, боты, сайты
  │     ├── developer     — код (Python/JS)
  │     ├── integrator    — внешние API, запуск ботов
  │     └── designer      — UI/UX, вёрстка
  ├── marketing (CMO)     — контент, реклама, бренд
  │     ├── marketer
  │     └── analyst
  └── sales (Head of Sales) — клиенты, переговоры, CRM
        └── salesman

Сервисные роли (вне отделов): researcher, strategist, architect, hr
```

## Установка

```bash
pip install -r requirements.txt
cd webapp && npm install && npm run build && cd ..
cp .env.example .env
```

Заполни `.env` как минимум:
```
LLM_BASE_URL=https://apinet.cloud/v1
LLM_API_KEY=sk-your-key
LLM_MODEL=glm-4.5-flash    # ≈бесплатно; любая модель провайдера (apinet.cloud/pricing)
DEMO_MODE=0                # 1 = демо без расхода токенов
APP_SECRET=                # обязателен на проде — python -c "import secrets; print(secrets.token_hex(32))"
```
Полный список переменных (OAuth-приложения, песочница исполнения кода,
per-tenant LLM-ключи) — см. `.env.example`.

## Запуск

```bash
python scripts/run.py                    # бэкенд + SPA на http://localhost:8000
DEMO_MODE=1 python scripts/run.py        # демо-режим без расхода токенов
```

⚠️ Не запускай `uvicorn server:app --reload` напрямую — `reload` следит за всем
деревом, включая папки тенантов, куда агенты пишут файлы; любая их запись
перезапускала бы сервер. `scripts/run.py` исключает данные тенантов из reload.

Для активной фронтенд-разработки:
```bash
cd webapp && npm run dev
```

## Прод-деплой

```bash
cp .env.example .env   # заполнить APP_SECRET, LLM_API_KEY, APP_BASE_URL (https://ваш-домен)
export DOMAIN=ваш-домен.ru
docker compose up -d --build
```

`Dockerfile` — двухстейджевая сборка (Node собирает фронт → Python-рантайм без Node/исходников webapp).
`docker-compose.yml` поднимает приложение + `Caddyfile`-прокси с автоматическим TLS (Let's Encrypt).
Без домена (`DOMAIN=localhost`) Caddy отдаёт self-signed сертификат — годится для локальной проверки.
`data/` — единственное состояние, которое обязано пережить пересборку образа (volume, не слой).

Это НЕ то же самое, что `docker/sandbox.Dockerfile` — та песочница исполняет код агентов
(`SANDBOX_MODE=docker`), а этот `Dockerfile` — сам сервер.

## CLI (без веб-интерфейса)

```bash
python main.py                    # ресёрчер → стратег
python main.py research "вопрос"  # только ресёрчер
```

## Проверка перед коммитом

```bash
python -m py_compile $(git ls-files '*.py')   # синтаксис Python
cd webapp && npx tsc --noEmit                  # типы React-приложения
python tests/run_all.py                        # юнит-тесты (без LLM, $0)
```

## Структура

```
ai-office/
├── server.py               # FastAPI: SSE-стрим, чат, OAuth, REST API, отдача SPA
├── scripts/run.py          # точка входа (см. «Запуск» — не uvicorn напрямую)
├── src/
│   ├── core/
│   │   ├── llm.py          # Единый LLM-клиент (OpenAI-формат), tool-loop
│   │   └── search.py       # Веб-поиск через DuckDuckGo
│   ├── agents/              # Роли: orchestrator (CEO), architect, leaders, researcher…
│   ├── office/               # Ядро: loop.py (автономный цикл), plan.py, world.py,
│   │                          # tool_router.py, skills.py, results.py, connections.py…
│   ├── integrations/         # Реальные вызовы внешних API (Telegram/Google/GitHub/
│   │                          # Figma/Bitrix24/1С…)
│   └── saas/                 # Мультиарендность: auth, per-tenant контекст, шифрование
├── webapp/                  # React + Vite + TypeScript SPA (билдится в static/webapp/)
├── data/tenants/<id>/       # Данные каждого тенанта (per-tenant, stateless-модули)
├── docs/                    # bos-architecture.md (спецификация), handoff.md (журнал)
└── tests/                   # Юнит-тесты (run_all.py — единый раннер)
```
