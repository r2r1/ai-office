"""
Демо-режим — проигрывает заранее записанный сценарий работы офиса
без обращения к API. Полезно, чтобы увидеть игру без расхода кредитов.

Включается переменной окружения: DEMO_MODE=1
"""

import asyncio

from src.office import bus, registry

# Сценарий: список событий с задержками (секунды до следующего события)
SCENARIO = [
    # --- Стартовая команда ---
    {"delay": 1, "event": {"type": "system", "text": "=== Офис открывается (ДЕМО-режим) ==="}},
    {"delay": 1.5, "hire": ("researcher_1", "researcher", "Исследование рынка AI-агентств")},
    {"delay": 1.0, "hire": ("strategist_1", "strategist", "Построение бизнес-стратегии")},
    {"delay": 1.0, "hire": ("hr_1", "hr", "Найм новых агентов")},

    # --- Цикл 1: исследование ---
    {"delay": 2, "event": {"type": "system", "text": "=== Цикл #1 начался ==="}},
    {"delay": 1.5, "event": {"type": "thinking", "agent_id": "researcher_1", "text": "Начинаю исследование рынка AI-агентов 2026..."}},
    {"delay": 3, "event": {"type": "speech", "agent_id": "researcher_1", "text": "Ищу: 'AI automation agency revenue 2026'"}},
    {"delay": 3, "event": {"type": "speech", "agent_id": "researcher_1", "text": "Рынок AI-агентов вырос с $5 млрд до $13 млрд за год!"}},
    {"delay": 3, "event": {"type": "speech", "agent_id": "researcher_1", "text": "Соло-основатели выходят на $25K MRR — узкое место не работа, а ответы клиентов"}},
    {"delay": 2.5, "event": {"type": "speech", "agent_id": "researcher_1", "text": "Маржинальность 70-85%, накладные всего $75-150/мес"}},
    {"delay": 2, "event": {"type": "task_done", "agent_id": "researcher_1", "summary": "Вывод: AI Automation Agency — самый реалистичный путь к 1М руб."}},

    # --- Стратег строит план ---
    {"delay": 2, "event": {"type": "thinking", "agent_id": "strategist_1", "text": "Анализирую отчёт ресёрчера, строю план..."}},
    {"delay": 3, "event": {"type": "speech", "agent_id": "strategist_1", "text": "Юнит-экономика: 4 ретейнера × 30,000₽ = 120,000₽/мес"}},
    {"delay": 3, "event": {"type": "speech", "agent_id": "strategist_1", "text": "Ниша: автоматизация для e-commerce и медклиник"}},
    {"delay": 2.5, "event": {"type": "speech", "agent_id": "strategist_1", "text": "Этапы 24/7: фундамент (часы) → первые лиды (1-2 дня) → сделки → масштаб"}},
    {"delay": 2, "event": {"type": "task_done", "agent_id": "strategist_1", "summary": "План готов: первый результат ~сутки, цель 1М руб. — недели (упор в скорость ответов клиентов)"}},

    # --- HR нанимает ---
    {"delay": 2, "event": {"type": "thinking", "agent_id": "hr_1", "text": "Анализирую команду, решаю кого нанять..."}},
    {"delay": 2.5, "event": {"type": "speech", "agent_id": "hr_1", "text": "Нужен продажник — некому искать клиентов!"}},
    {"delay": 1.5, "hire": ("salesman_1", "salesman", "Найти 5 клиентов в нише e-commerce")},
    {"delay": 2, "event": {"type": "thinking", "agent_id": "salesman_1", "text": "Начинаю поиск клиентов..."}},
    {"delay": 3, "event": {"type": "speech", "agent_id": "salesman_1", "text": "Нашёл 12 интернет-магазинов без автоматизации заявок"}},
    {"delay": 3, "event": {"type": "speech", "agent_id": "salesman_1", "text": "Готовлю cold outreach в Telegram: оффер за 40,000₽"}},
    {"delay": 2.5, "event": {"type": "task_done", "agent_id": "salesman_1", "summary": "5 лидов готовы к контакту, 2 ответили положительно"}},

    # --- HR нанимает разработчика ---
    {"delay": 2, "event": {"type": "thinking", "agent_id": "hr_1", "text": "Клиенты есть — нужен тот, кто построит автоматизации"}},
    {"delay": 1.5, "event": {"type": "speech", "agent_id": "hr_1", "text": "Нанимаю разработчика!"}},
    {"delay": 1.5, "hire": ("developer_1", "developer", "Построить AI-чатбот для первого клиента")},
    {"delay": 2, "event": {"type": "thinking", "agent_id": "developer_1", "text": "Проектирую автоматизацию заявок на n8n + Claude..."}},
    {"delay": 3, "event": {"type": "speech", "agent_id": "developer_1", "text": "Стек: n8n + Claude API + Telegram Bot API"}},
    {"delay": 3, "event": {"type": "speech", "agent_id": "developer_1", "text": "Бот обрабатывает заявку и квалифицирует лид за 3 сек"}},
    {"delay": 2.5, "event": {"type": "task_done", "agent_id": "developer_1", "summary": "MVP чатбота готов, демо для клиента собрано"}},

    # --- HR нанимает маркетолога ---
    {"delay": 2, "event": {"type": "speech", "agent_id": "hr_1", "text": "Нужен маркетолог для потока входящих клиентов"}},
    {"delay": 1.5, "hire": ("marketer_1", "marketer", "Создать контент-план для Telegram-канала")},
    {"delay": 2, "event": {"type": "thinking", "agent_id": "marketer_1", "text": "Готовлю контент-стратегию..."}},
    {"delay": 3, "event": {"type": "speech", "agent_id": "marketer_1", "text": "10 постов: кейсы автоматизации + цифры ROI клиентов"}},
    {"delay": 2.5, "event": {"type": "task_done", "agent_id": "marketer_1", "summary": "Контент-план на месяц готов, первый пост опубликован"}},

    # --- Итог цикла ---
    {"delay": 2, "event": {"type": "system", "text": "💰 Прогресс: 2 клиента подписали договор = 80,000₽"}},
    {"delay": 2, "event": {"type": "system", "text": "=== Цикл #1 завершён. Команда из 6 агентов работает ==="}},
    {"delay": 3, "event": {"type": "system", "text": "🔁 Демо завершено. В реальном режиме офис работает бесконечно."}},
]


async def run() -> None:
    """Проигрывает демо-сценарий по кругу."""
    await bus.publish({"type": "system", "text": "ДЕМО-РЕЖИМ: проигрываю сценарий без API"})

    while True:
        # Сбрасываем реестр для нового прогона
        registry._agents.clear()
        registry._used_desks.clear()

        for step in SCENARIO:
            await asyncio.sleep(step["delay"])

            if "hire" in step:
                agent_id, role, task = step["hire"]
                rec = registry.register(agent_id, role, task)
                if rec:
                    await bus.publish({
                        "type": "hired",
                        "agent_id": agent_id,
                        "role": role,
                        "desk": rec.desk,
                        "task": task,
                    })
            elif "event" in step:
                await bus.publish(step["event"])

        # Пауза перед повтором
        await asyncio.sleep(8)
