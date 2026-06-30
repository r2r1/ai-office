"""
Чат с агентами — пользователь может кликнуть на агента и поговорить с ним.
Каждый агент помнит контекст диалога. Использует web_search при необходимости.
"""

import json
from pathlib import Path
from typing import Optional, Callable, Awaitable

from src.core import llm
from src.office import registry, agent_inbox
from src.office import brief as brief_module
from src.office import models as models_module
from src.saas import context as ctx

_HIST_FILE = "chat_histories.json"

# Системные промпты по ролям — задают характер и компетенции агента
ROLE_SYSTEM = {
    "orchestrator": (
        "Ты — директор AI-офиса. Ты управляешь всей командой агентов, разбиваешь путь "
        "к цели на этапы, ставишь задачи и контролируешь прогресс. Знаешь стратегию и "
        "текущее состояние дел. Отвечай как руководитель — по делу, с приоритетами и планом."
    ),
    "researcher": (
        "Ты — агент-исследователь AI-офиса. Ты эксперт по поиску трендов, рынков, "
        "кейсов и данных. Отвечай по делу, опирайся на факты. Можешь искать в интернете "
        "через web_search. Отвечай дружелюбно, как коллега по офису."
    ),
    "strategist": (
        "Ты — агент-стратег AI-офиса. Ты строишь бизнес-планы, считаешь юнит-экономику, "
        "декомпозируешь цели на задачи. Отвечай структурно и конкретно, как коллега."
    ),
    "hr": (
        "Ты — HR-директор AI-офиса. Ты решаешь кого нанять, управляешь командой агентов. "
        "Отвечай по-деловому, но дружелюбно."
    ),
    "salesman": (
        "Ты — агент продаж AI-офиса. Ты ищешь клиентов, пишешь офферы и cold outreach. "
        "Энергичный, ориентированный на результат. Отвечай как коллега."
    ),
    "developer": (
        "Ты — технический агент AI-офиса. Ты строишь автоматизации и AI-продукты. "
        "Объясняешь технически, но понятно. Отвечай как коллега."
    ),
    "marketer": (
        "Ты — маркетинговый агент AI-офиса. Ты создаёшь контент и стратегии продвижения. "
        "Креативный, в курсе трендов. Отвечай как коллега."
    ),
    "analyst": (
        "Ты — аналитик AI-офиса. Ты работаешь с данными, метриками, цифрами. "
        "Отвечай точно и с числами. Отвечай как коллега."
    ),
}

MAX_HISTORY = 12  # храним последние N реплик, чтобы не раздувать токены


def _all_histories() -> dict:
    return ctx.read_json(_HIST_FILE, {})


def _save_all(h: dict) -> None:
    ctx.write_json(_HIST_FILE, h)


_SEND_MESSAGE_TOOL = {
    "type": "function",
    "function": {
        "name": "send_message",
        "description": "Отправляет сообщение другому агенту-коллеге по его agent_id. Используй чтобы делегировать задачу или запросить информацию у коллеги.",
        "parameters": {
            "type": "object",
            "properties": {
                "to_agent_id": {"type": "string", "description": "ID агента-получателя (например: marketer_1, analyst_1)"},
                "message": {"type": "string", "description": "Текст сообщения коллеге"},
            },
            "required": ["to_agent_id", "message"],
        },
    },
}

_READ_MESSAGES_TOOL = {
    "type": "function",
    "function": {
        "name": "read_messages",
        "description": "Читает входящие сообщения от других агентов-коллег.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


def _build_system(agent_id: str, rec) -> str:
    role = rec.role if rec else "researcher"
    system = ROLE_SYSTEM.get(role, f"Ты — {role} агент AI-офиса. Отвечай как дружелюбный коллега.")

    if rec and rec.task:
        system += f"\n\nТвоя текущая задача в офисе: {rec.task}"

    # Добавляем бриф клиента — агент знает всё что клиент рассказал при онбординге
    b = brief_module.get()
    if b:
        parts = []
        if b.get("niche"):
            parts.append(f"Ниша: {b['niche']}")
        if b.get("goal"):
            parts.append(f"Цель: {b['goal']}")
        if b.get("audience"):
            parts.append(f"Аудитория: {b['audience']}")
        if b.get("assets"):
            parts.append(f"Что есть у клиента: {b['assets']}")
        if b.get("summary"):
            parts.append(f"Резюме брифа: {b['summary']}")
        if parts:
            system += "\n\n=== БРИФ КЛИЕНТА ===\n" + "\n".join(parts)

    system += "\n\nТы можешь общаться с коллегами: send_message — отправить сообщение агенту, read_messages — прочитать входящие."
    system += (
        "\n\n=== КАК ОТВЕЧАТЬ В ЧАТЕ ===\n"
        "Пиши КОРОТКО и по делу — 2–5 предложений, живым языком. Это чат, а не отчёт. "
        "Не вываливай простыни, списки на пол-экрана и сырой код в чат. Если результат "
        "большой (тексты, код, таблица) — сохрани его в рабочую папку/документ и в чате "
        "коротко скажи ЧТО сделал и ГДЕ смотреть (вкладка «Итоги»/«Код»). "
        "Сначала ответь на вопрос, потом, если нужно, предложи следующий шаг одной строкой."
    )
    return system


async def ask(
    agent_id: str,
    message: str,
    publish: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> str:
    """Задаёт вопрос конкретному агенту и возвращает его ответ."""
    rec = registry.get(agent_id)
    system = _build_system(agent_id, rec)
    histories = _all_histories()
    history = histories.get(agent_id, [])

    if publish:
        await publish({"type": "thinking", "agent_id": agent_id,
                       "text": "печатает ответ..."})

    async def _handle_send_message(args: dict) -> str:
        to_id = args.get("to_agent_id", "")
        msg = args.get("message", "")
        agent_inbox.send(to_id, agent_id, msg)
        if publish:
            await publish({"type": "speech", "agent_id": agent_id,
                           "text": f"→ {to_id}: {msg[:60]}"})
        return f"Сообщение отправлено агенту {to_id}"

    async def _handle_read_messages(_: dict) -> str:
        msgs = agent_inbox.read(agent_id)
        return json.dumps(msgs, ensure_ascii=False)

    reply = await llm.run_agent(
        system=system,
        user=message,
        model=models_module.for_agent(agent_id),
        history=history,
        max_tokens=3000,  # не режем ответ на полуслове; краткость — через инструкцию в system
        max_iterations=5,
        use_search=True,
        publish=None,
        agent_id=agent_id,
        extra_tools=[_SEND_MESSAGE_TOOL, _READ_MESSAGES_TOOL],
        tool_handlers={"send_message": _handle_send_message, "read_messages": _handle_read_messages},
    )

    # Обновляем историю
    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": reply})
    if len(history) > MAX_HISTORY:
        del history[:len(history) - MAX_HISTORY]
    histories[agent_id] = history
    _save_all(histories)

    # Ответ агента доставляется в личный чат вызывающей стороной (server /api/ask
    # публикует agent_message). Здесь намеренно НЕ публикуем speech/chat_reply,
    # чтобы личная переписка не утекала в общий канал офиса.
    return reply


def clear_history(agent_id: str) -> None:
    h = _all_histories()
    h.pop(agent_id, None)
    _save_all(h)


def clear_all() -> None:
    ctx.delete_file(_HIST_FILE)
