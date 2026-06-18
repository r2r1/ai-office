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

HISTORY_FILE = Path("reports/chat_histories.json")

# Системные промпты по ролям — задают характер и компетенции агента
ROLE_SYSTEM = {
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

# История диалогов: agent_id -> [{role, content}]
_histories: dict[str, list[dict[str, str]]] = {}

MAX_HISTORY = 12  # храним последние N реплик, чтобы не раздувать токены


def _load_histories() -> None:
    if HISTORY_FILE.exists():
        try:
            data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                _histories.update(data)
        except Exception:
            pass


def _save_histories() -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(_histories, ensure_ascii=False, indent=2), encoding="utf-8")


_load_histories()


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
    return system


async def ask(
    agent_id: str,
    message: str,
    publish: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> str:
    """Задаёт вопрос конкретному агенту и возвращает его ответ."""
    rec = registry.get(agent_id)
    system = _build_system(agent_id, rec)
    history = _histories.setdefault(agent_id, [])

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
        history=history,
        max_tokens=1500,
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
    _save_histories()

    if publish:
        # Показываем ответ пузырём над агентом
        await publish({"type": "speech", "agent_id": agent_id, "text": reply[:120]})
        await publish({"type": "chat_reply", "agent_id": agent_id, "text": reply})

    return reply


def clear_history(agent_id: str) -> None:
    _histories.pop(agent_id, None)
