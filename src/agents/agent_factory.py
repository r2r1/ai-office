"""
Фабрика агентов — создаёт нового агента по роли и задаче.
Работает через единое ядро llm.py.

Любой агент может запросить ресёрчера через инструмент request_research.
"""

import json
from typing import Callable, Awaitable

from src.core import llm
from src.agents import researcher as researcher_agent
from src.office import questions as questions_module
from src.office import agent_inbox
from src.office import brief as brief_module

_INTER_AGENT_SUFFIX = "\nТы можешь отправлять сообщения другим агентам через send_message и читать входящие через read_messages."

ROLE_PROMPTS = {
    "salesman": (
        "Ты — агент продаж AI-агентства. Найди потенциальных клиентов, придумай "
        "оффер и напиши холодное сообщение. Конкретно: компании, каналы, текст. "
        "Используй web_search для актуальных данных."
    ),
    "developer": (
        "Ты — технический агент AI-агентства. Спроектируй автоматизацию для клиента: "
        "стек, архитектура, шаги. Используй web_search для актуальных инструментов."
    ),
    "marketer": (
        "Ты — маркетинговый агент AI-агентства. Создай контент-план и посты для "
        "Telegram/LinkedIn. Когда контент-план заканчивается или нужны свежие тренды — "
        "вызывай request_research с кратким вопросом. Опирайся на реальные тренды."
    ),
    "analyst": (
        "Ты — аналитик AI-агентства. Собери и проанализируй данные по рынку, "
        "конкурентам или клиентам. Выводы с цифрами. Используй web_search."
    ),
}

# Инструмент: задать вопрос пользователю
_ASK_USER_TOOL = {
    "type": "function",
    "function": {
        "name": "ask_user",
        "description": "Задаёт вопрос пользователю и ждёт ответа. Используй когда нужна уточняющая информация от клиента.",
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "Вопрос пользователю"},
            },
            "required": ["question"],
        },
    },
}

# Инструмент: отправить сообщение другому агенту
_SEND_MESSAGE_TOOL = {
    "type": "function",
    "function": {
        "name": "send_message",
        "description": "Отправляет сообщение другому агенту по его agent_id.",
        "parameters": {
            "type": "object",
            "properties": {
                "to_agent_id": {"type": "string", "description": "ID агента-получателя"},
                "message": {"type": "string", "description": "Текст сообщения"},
            },
            "required": ["to_agent_id", "message"],
        },
    },
}

# Инструмент: прочитать входящие сообщения
_READ_MESSAGES_TOOL = {
    "type": "function",
    "function": {
        "name": "read_messages",
        "description": "Читает входящие сообщения от других агентов.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}

# Инструмент: запросить ресёрчера
_REQUEST_RESEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "request_research",
        "description": (
            "Запрашивает ресёрчера для поиска информации. Используй для свежих трендов, "
            "данных рынка, идей контента. depth='quick' — быстро и дёшево (по умолчанию), "
            "depth='deep' — полное исследование."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "Вопрос для исследования"},
                "depth": {"type": "string", "enum": ["quick", "deep"]},
            },
            "required": ["question"],
        },
    },
}


def _brief_context() -> str:
    """Формирует блок с брифом клиента для вставки в системный промпт."""
    b = brief_module.get()
    if not b:
        return ""
    parts = []
    if b.get("niche"):
        parts.append(f"Ниша: {b['niche']}")
    if b.get("goal"):
        parts.append(f"Цель клиента: {b['goal']}")
    if b.get("audience"):
        parts.append(f"Аудитория: {b['audience']}")
    if b.get("assets"):
        parts.append(f"Что есть: {b['assets']}")
    if b.get("summary"):
        parts.append(f"Резюме: {b['summary']}")
    if not parts:
        return ""
    return "\n\n=== БРИФ КЛИЕНТА (всегда держи в контексте) ===\n" + "\n".join(parts)


def create(role: str, task: str, agent_id: str, publish: Callable[[dict], Awaitable[None]]):
    """Возвращает async-функцию, запускающую агента."""
    base = ROLE_PROMPTS.get(role, f"Ты — {role} агент AI-агентства. Выполни задачу профессионально.")
    system = base + _brief_context() + _INTER_AGENT_SUFFIX

    async def _handle_request_research(args: dict) -> str:
        question = args.get("question", "")
        depth = args.get("depth", "quick")
        await publish({"type": "speech", "agent_id": agent_id,
                       "text": f"📡 Запрашиваю ресёрчера [{depth}]: {question[:60]}"})
        return await researcher_agent.run_async(
            question=question, depth=depth, publish=publish, agent_id="researcher_1",
        )

    async def _handle_ask_user(args: dict) -> str:
        question_text = args.get("question", "")
        qid, fut = questions_module.ask(question_text, publish)
        await publish({"type": "question", "agent_id": agent_id, "question_id": qid, "text": question_text})
        answer = await fut
        return answer

    async def _handle_send_message(args: dict) -> str:
        to_agent_id = args.get("to_agent_id", "")
        message = args.get("message", "")
        agent_inbox.send(to_agent_id, agent_id, message)
        await publish({"type": "speech", "agent_id": agent_id,
                       "text": f"→ {to_agent_id}: {message[:60]}"})
        return f"Сообщение отправлено агенту {to_agent_id}"

    async def _handle_read_messages(args: dict) -> str:
        msgs = agent_inbox.read(agent_id)
        return json.dumps(msgs, ensure_ascii=False)

    async def run() -> str:
        await publish({"type": "thinking", "agent_id": agent_id,
                       "text": f"Начинаю работу: {task[:80]}..."})

        result = await llm.run_agent(
            system=system,
            user=task,
            max_tokens=3000,
            max_iterations=8,
            use_search=True,
            publish=publish,
            agent_id=agent_id,
            extra_tools=[_REQUEST_RESEARCH_TOOL, _ASK_USER_TOOL, _SEND_MESSAGE_TOOL, _READ_MESSAGES_TOOL],
            tool_handlers={
                "request_research": _handle_request_research,
                "ask_user": _handle_ask_user,
                "send_message": _handle_send_message,
                "read_messages": _handle_read_messages,
            },
        )

        await publish({"type": "task_done", "agent_id": agent_id, "summary": result[:300]})
        return result

    return run
