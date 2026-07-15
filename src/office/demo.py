"""
Демо-режим — проигрывает заранее записанный сценарий работы офиса
без обращения к API. Полезно, чтобы увидеть игру без расхода кредитов.

Включается переменной окружения: DEMO_MODE=1

Сценарий повторяет НОВУЮ модель «реальная компания» (см. src/office/loop.py):
CEO (orchestrator) открывает отделы по необходимости → нанимается лидер отдела
(CTO/CMO/Head of Sales) → лидер нанимает работников и ставит им задачи.
Типы событий и префиксы реплик совпадают с реальными (_apply_company_decision,
_hire_leader, _run_leaders): 🧭 — мысль CEO, 👔 — мысль лидера, → — поручение.
"""

import asyncio

from src.saas import context as ctx
from src.office import bus, registry, org, plan as plan_module, office_channel

# Аудит (docs/pre-release-audit-2026-07-15.md), находка Medium #4: демо-сценарий
# рассказывал про кипящую работу, но `plan.set_tasks()` не вызывался ни разу —
# вкладка «Работа» показывала пустую доску одновременно с бурлящей лентой
# событий. Три задачи ниже соответствуют трём "hire" из SCENARIO (developer_1/
# salesman_1/marketer_1) — доска и лента теперь рассказывают одну историю.
DEMO_TASKS = [
    {"id": "demo_t1", "title": "Собрать лендинг и Telegram-бота для квалификации лидов",
     "role": "developer", "done_criterion": "MVP работает, код в рабочей папке"},
    {"id": "demo_t2", "title": "Найти 5 клиентов в нише e-commerce",
     "role": "salesman", "done_criterion": "5 лидов найдены, минимум 1 сделка закрыта"},
    {"id": "demo_t3", "title": "Создать контент-план для Telegram-канала",
     "role": "marketer", "done_criterion": "План на месяц готов, первый пост опубликован"},
]
_TASK_BY_AGENT = {"developer_1": "demo_t1", "salesman_1": "demo_t2", "marketer_1": "demo_t3"}

# Сценарий: список событий с задержками (секунды до следующего события).
# Поддерживаемые шаги:
#   {"delay": n, "event": {...}}                       — произвольное событие в шину
#   {"delay": n, "hire": (id, role, task)}             — наём работника лидером
#   {"delay": n, "open_dept": (dept_id, objective)}    — CEO открывает отдел + лидер
SCENARIO = [
    # --- Стартовая команда: CEO + штаб стратегии (как _hire_initial) ---
    {"delay": 1, "event": {"type": "system", "text": "=== Офис открывается (ДЕМО-режим) ==="}},
    {"delay": 1.2, "hire": ("orchestrator_1", "orchestrator", "Управление компанией и отделами")},
    {"delay": 1.0, "hire": ("researcher_1", "researcher", "Исследование рынка и трендов")},
    {"delay": 1.0, "hire": ("strategist_1", "strategist", "Построение бизнес-стратегии")},
    {"delay": 1.0, "hire": ("architect_1", "architect", "Техническое задание (ТЗ)")},

    # --- BOOTSTRAP: исследование → стратегия → ТЗ ---
    {"delay": 1.5, "event": {"type": "system", "text": "=== BOOTSTRAP: исследуем нишу клиента ==="}},
    {"delay": 1.5, "event": {"type": "thinking", "agent_id": "researcher_1", "text": "Начинаю глубокое исследование рынка AI-агентов 2026..."}},
    {"delay": 3, "event": {"type": "speech", "agent_id": "researcher_1", "text": "Ищу: 'AI automation agency revenue 2026'"}},
    {"delay": 3, "event": {"type": "speech", "agent_id": "researcher_1", "text": "Рынок AI-агентов вырос с $5 млрд до $13 млрд за год!"}},
    {"delay": 2.5, "event": {"type": "speech", "agent_id": "researcher_1", "text": "Маржинальность 70-85%, накладные всего $75-150/мес"}},
    {"delay": 2, "event": {"type": "task_done", "agent_id": "researcher_1", "summary": "Вывод: AI Automation Agency — самый реалистичный путь к 1М руб."}},

    {"delay": 1.5, "event": {"type": "thinking", "agent_id": "strategist_1", "text": "Анализирую отчёт ресёрчера, строю стратегию..."}},
    {"delay": 3, "event": {"type": "speech", "agent_id": "strategist_1", "text": "Юнит-экономика: 4 ретейнера × 30,000₽ = 120,000₽/мес"}},
    {"delay": 2.5, "event": {"type": "speech", "agent_id": "strategist_1", "text": "Ниша: автоматизация для e-commerce и медклиник"}},
    {"delay": 2, "event": {"type": "task_done", "agent_id": "strategist_1", "summary": "Стратегия готова: цель 1М руб., упор в скорость ответов клиентам"}},

    {"delay": 1.5, "event": {"type": "thinking", "agent_id": "architect_1", "text": "Проектирую техническое решение под стратегию..."}},
    {"delay": 2.5, "event": {"type": "speech", "agent_id": "architect_1", "text": "Стек: FastAPI + Claude API + Telegram Bot API, лендинг для лидов"}},
    {"delay": 2, "event": {"type": "task_done", "agent_id": "architect_1", "summary": "ТЗ готово → reports/tech_design.md"}},

    # --- Цикл 1: CEO открывает Технический отдел ---
    {"delay": 2, "event": {"type": "system", "text": "=== Цикл #1: CEO принимает решение ==="}},
    {"delay": 1.5, "event": {"type": "speech", "agent_id": "orchestrator_1", "text": "🧭 Сначала нужен продукт — открываю Технический отдел"}},
    {"delay": 1.0, "open_dept": ("tech", "Собрать MVP: лендинг + Telegram-бот квалификации лидов")},

    # CTO нанимает разработчика и ставит задачу (👔 — мысль лидера, → — поручение)
    {"delay": 2, "event": {"type": "speech", "agent_id": "cto_1", "text": "👔 Беру разработчика — соберём лендинг и бота"}},
    {"delay": 1.5, "hire": ("developer_1", "developer", "Собрать лендинг и Telegram-бота для квалификации лидов")},
    {"delay": 1.5, "event": {"type": "speech", "agent_id": "orchestrator_1", "text": "→ Поручаю developer_1: собрать лендинг и Telegram-бота"}},
    {"delay": 2, "event": {"type": "thinking", "agent_id": "developer_1", "text": "Проектирую структуру проекта..."}},
    {"delay": 2.5, "event": {"type": "file_written", "agent_id": "developer_1", "path": "app/main.py", "text": "📝 developer_1: записан app/main.py"}},
    {"delay": 2.5, "event": {"type": "file_written", "agent_id": "developer_1", "path": "app/bot.py", "text": "📝 developer_1: записан app/bot.py"}},
    {"delay": 2.5, "event": {"type": "file_written", "agent_id": "developer_1", "path": "static/landing.html", "text": "📝 developer_1: записан static/landing.html"}},
    {"delay": 2, "event": {"type": "speech", "agent_id": "developer_1", "text": "Бот квалифицирует лид за 3 сек, лендинг собирает заявки"}},
    {"delay": 2, "event": {"type": "task_done", "agent_id": "developer_1", "summary": "MVP готов: лендинг + Telegram-бот, код в рабочей папке"}},
    {"delay": 1.5, "event": {"type": "speech", "agent_id": "cto_1", "text": "👔 Отдел сдал MVP — докладываю CEO, продукт готов"}},

    # --- Цикл 2: CEO открывает Отдел продаж ---
    {"delay": 2, "event": {"type": "system", "text": "=== Цикл #2: CEO принимает решение ==="}},
    {"delay": 1.5, "event": {"type": "speech", "agent_id": "orchestrator_1", "text": "🧭 Продукт есть — нужны клиенты, открываю Отдел продаж"}},
    {"delay": 1.0, "open_dept": ("sales", "Найти 5 клиентов в нише e-commerce и закрыть сделки")},
    {"delay": 2, "event": {"type": "speech", "agent_id": "sales_lead_1", "text": "👔 Беру продажника на cold outreach"}},
    {"delay": 1.5, "hire": ("salesman_1", "salesman", "Найти 5 клиентов в нише e-commerce")},
    {"delay": 1.5, "event": {"type": "speech", "agent_id": "orchestrator_1", "text": "→ Поручаю salesman_1: найти 5 клиентов в e-commerce"}},
    {"delay": 2, "event": {"type": "thinking", "agent_id": "salesman_1", "text": "Ищу интернет-магазины без автоматизации заявок..."}},
    {"delay": 3, "event": {"type": "speech", "agent_id": "salesman_1", "text": "Нашёл 12 магазинов, готовлю оффер за 40,000₽"}},
    {"delay": 2, "event": {"type": "task_done", "agent_id": "salesman_1", "summary": "5 лидов готовы, 2 ответили положительно"}},

    # --- Цикл 3: CEO открывает Отдел маркетинга ---
    {"delay": 2, "event": {"type": "system", "text": "=== Цикл #3: CEO принимает решение ==="}},
    {"delay": 1.5, "event": {"type": "speech", "agent_id": "orchestrator_1", "text": "🧭 Нужен поток входящих — открываю Отдел маркетинга"}},
    {"delay": 1.0, "open_dept": ("marketing", "Запустить контент-канал для привлечения клиентов")},
    {"delay": 2, "event": {"type": "speech", "agent_id": "cmo_1", "text": "👔 Беру маркетолога на контент-план"}},
    {"delay": 1.5, "hire": ("marketer_1", "marketer", "Создать контент-план для Telegram-канала")},
    {"delay": 1.5, "event": {"type": "speech", "agent_id": "orchestrator_1", "text": "→ Поручаю marketer_1: контент-план Telegram-канала"}},
    {"delay": 2, "event": {"type": "thinking", "agent_id": "marketer_1", "text": "Готовлю контент-стратегию..."}},
    {"delay": 2.5, "event": {"type": "speech", "agent_id": "marketer_1", "text": "10 постов: кейсы автоматизации + цифры ROI клиентов"}},
    {"delay": 2, "event": {"type": "task_done", "agent_id": "marketer_1", "summary": "Контент-план на месяц готов, первый пост опубликован"}},

    # --- Итог ---
    {"delay": 2, "event": {"type": "system", "text": "💰 Прогресс: 2 клиента подписали договор = 80,000₽"}},
    {"delay": 2, "event": {"type": "system", "text": "=== Компания работает: 3 отдела, CEO + штаб + 3 работника ==="}},
    {"delay": 3, "event": {"type": "system", "text": "🔁 Демо завершено. В реальном режиме офис работает бесконечно."}},
]


async def run() -> None:
    """Проигрывает демо-сценарий по кругу (в контексте тенанта 'default').

    Аудит, находки Medium #5/#6: раньше `registry.reset()`/`org.reset()` вызывались
    в начале КАЖДОГО повтора (~каждые 90+8 сек) — вся команда, включая CEO, с
    которым посетитель мог только что переписываться, молча "увольнялась" и
    нанималась заново, а health-скор на секунду скакал вниз из-за пустого состава
    отделов. Теперь сброс — один раз ПЕРЕД циклом, а не в каждом его повторе:
    команда стабильна, health не скачет, а второй и последующие проходы явно
    называются повтором той же истории, а не сбросом.
    """
    ctx.set_tenant("default")
    await bus.publish({"type": "system", "text": "ДЕМО-РЕЖИМ: проигрываю сценарий без API"})

    registry.reset()
    org.reset()
    plan_module.reset()
    plan_module.set_tasks(DEMO_TASKS)

    lap = 0
    while True:
        lap += 1
        if lap > 1:
            await bus.publish({"type": "system",
                               "text": "🔁 Демо повторяется с той же командой — никто никуда не уходил, "
                                       "просто ещё раз показываем, как это работает"})

        for step in SCENARIO:
            await asyncio.sleep(step["delay"])

            if "open_dept" in step:
                dept_id, objective = step["open_dept"]
                org.open_department(dept_id, reason="демо", objective=objective)
                info = org.catalog().get(dept_id, {})
                # Нанимаем лидера отдела (как _hire_leader)
                role = info.get("lead_role", "")
                agent_id = f"{role}_1"
                rec = registry.register(agent_id, role, objective[:100],
                                        department=dept_id, manager="orchestrator_1")
                if rec and lap == 1:
                    await bus.publish({"type": "hired", "agent_id": agent_id, "role": role,
                                       "desk": rec.desk, "task": objective[:100]})
                    gmsg = office_channel.greet(agent_id, role, objective[:100])
                    await bus.publish({"type": "office_chat", "from": agent_id, "role": role,
                                       "text": gmsg["text"], "id": gmsg["id"]})
                if lap == 1:
                    await bus.publish({"type": "system",
                                       "text": f"📂 CEO открыл «{info.get('name', dept_id)}»"})
            elif "hire" in step:
                agent_id, role, task = step["hire"]
                dept = org.department_of_role(role)
                manager = org.lead_id(dept) or "orchestrator_1"
                rec = registry.register(agent_id, role, task,
                                        department=dept, manager=manager)
                if rec and lap == 1:
                    await bus.publish({
                        "type": "hired",
                        "agent_id": agent_id,
                        "role": role,
                        "desk": rec.desk,
                        "task": task,
                    })
                    gmsg = office_channel.greet(agent_id, role, task)
                    await bus.publish({"type": "office_chat", "from": agent_id, "role": role,
                                       "text": gmsg["text"], "id": gmsg["id"]})
                task_id = _TASK_BY_AGENT.get(agent_id)
                if task_id:
                    plan_module.assign(task_id, agent_id)
            elif "event" in step:
                ev = step["event"]
                await bus.publish(ev)
                if ev.get("type") == "task_done":
                    task_id = _TASK_BY_AGENT.get(ev.get("agent_id", ""))
                    if task_id:
                        plan_module.complete(task_id)

        # Пауза перед повтором — команда остаётся на месте
        await asyncio.sleep(8)
