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
from src.office import state
from src.office import connections
from src.office import memory as memory_module
from src.office import models as models_module

_INTER_AGENT_SUFFIX = (
    "\nТы можешь отправлять сообщения другим агентам через send_message и читать входящие через read_messages."
    "\nЕсли нужны данные для подключения к платформе — сначала проверь get_connection, затем если нет — спроси через ask_user."
    "\nЕсли подключение не работает (ошибка API, неверный ключ) — опиши ошибку конкретно: что пробовал, какой ответ получил."
)

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

# Инструмент: получить доступ/учётные данные к внешней платформе
_GET_CONNECTION_TOOL = {
    "type": "function",
    "function": {
        "name": "get_connection",
        "description": (
            "Получает сохранённые доступы к внешней платформе (API-ключ, логин/пароль, токен) "
            "по названию. Используй когда нужно подключиться к сервису. "
            "Если подключения нет — спроси пользователя через ask_user, чтобы он его добавил."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Название платформы (например: Instagram, OpenAI, Telegram)"},
            },
            "required": ["name"],
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


_CRED_KEYWORDS = {
    "api", "key", "ключ", "token", "токен", "secret", "пароль", "password",
    "логин", "login", "access", "доступ", "credentials", "учётные", "oauth",
    "telegram", "instagram", "vk", "вконтакте", "openai", "anthropic",
    "notion", "airtable", "google", "youtube", "tiktok", "facebook",
}

_PLATFORM_WORDS = {
    "telegram", "instagram", "vk", "вконтакте", "openai", "anthropic",
    "google", "youtube", "tiktok", "facebook", "notion", "airtable",
    "twitter", "linkedin", "whatsapp", "viber", "discord", "slack",
    "github", "gitlab", "stripe", "yandex", "яндекс", "авито", "avito",
    "wildberries", "wb", "ozon", "озон", "bitrix", "bitrix24",
}

_CRED_TYPES = {"key", "ключ", "token", "токен", "secret"} | {"password", "пароль"} | {"login", "логин"}


def _try_extract_connection(question: str, answer: str) -> dict | None:
    """
    Если вопрос звучит как запрос учётных данных — собираем структуру подключения.
    Возвращает dict для connections.save() или None если не похоже на учётные данные.
    """
    if not answer.strip():
        return None
    q_lower = question.lower()
    words = set(q_lower.replace(":", " ").replace("?", " ").replace(".", " ").split())

    # Нужен хотя бы один кред-ключевик
    if not (words & _CRED_KEYWORDS):
        return None

    # Определяем название платформы (первое совпадение из известных)
    platform = next((w.capitalize() for w in words if w in _PLATFORM_WORDS), None)
    if not platform:
        # Ищем слово после "для" / "к" / "of" / "for"
        import re
        m = re.search(r'(?:для|к|for|of)\s+([a-zа-я0-9_\-]+)', q_lower)
        platform = m.group(1).capitalize() if m else "Сервис"

    # Тип подключения
    if words & {"password", "пароль", "login", "логин"}:
        conn_type = "login"
        # Пробуем разобрать "login: X password: Y" или "логин: X пароль: Y"
        import re
        l = re.search(r'(?:login|логин)[:\s]+([^\s,]+)', answer, re.I)
        p = re.search(r'(?:password|пароль)[:\s]+([^\s,]+)', answer, re.I)
        if l and p:
            fields = {"login": l.group(1), "password": p.group(1)}
        else:
            fields = {"value": answer.strip()}
    else:
        conn_type = "api"
        fields = {"key": answer.strip()}

    # Не дублируем уже существующее подключение с тем же именем и тем же значением
    existing = connections.get_by_name(platform)
    if existing:
        ev = existing.get("fields", {})
        if ev.get("key") == answer.strip() or ev.get("value") == answer.strip():
            return None  # уже есть, не создаём дубль

    return {"name": platform, "type": conn_type, "fields": fields,
            "note": f"Автосохранено от агента {role} при ответе на вопрос"}


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
    # Собираем системный промпт: роль + бриф + память (ответы пользователя) + межагентный суффикс
    system = base + _brief_context() + memory_module.context_block() + _INTER_AGENT_SUFFIX

    async def _handle_request_research(args: dict) -> str:
        question = args.get("question", "")
        depth = args.get("depth", "quick")
        await publish({"type": "speech", "agent_id": agent_id,
                       "text": f"📡 Запрашиваю ресёрчера [{depth}]: {question[:60]}"})
        return await researcher_agent.run_async(
            question=question, depth=depth, publish=publish, agent_id="researcher_1",
        )

    async def _handle_ask_user(args: dict) -> str:
        import asyncio
        question_text = args.get("question", "")
        # Проверяем память — вдруг на этот вопрос уже отвечали
        cached = memory_module.lookup(question_text)
        if cached:
            await publish({"type": "speech", "agent_id": agent_id,
                           "text": f"💭 (из памяти): {question_text[:50]} → {cached[:60]}"})
            return cached
        qid, fut = questions_module.ask(question_text, publish, agent_id=agent_id)
        await publish({"type": "question", "agent_id": agent_id, "question_id": qid, "text": question_text})
        try:
            answer = await asyncio.wait_for(fut, timeout=300)  # 5 мин макс
        except asyncio.TimeoutError:
            questions_module.answer(qid, "")
            return "Пользователь не ответил — продолжай без этих данных."
        if answer:
            memory_module.remember(question_text, answer)
            # Автосохранение в подключения если вопрос про учётные данные
            conn = _try_extract_connection(question_text, answer)
            if conn:
                saved = connections.save(conn)
                await publish({"type": "connection_added", "connection": saved,
                               "agent_id": agent_id,
                               "text": f"🔌 Доступ '{saved['name']}' сохранён в подключения"})
                await publish({"type": "speech", "agent_id": agent_id,
                               "text": f"✅ Доступ к {saved['name']} сохранён — буду использовать в следующий раз автоматически"})
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

    async def _handle_get_connection(args: dict) -> str:
        name = args.get("name", "")
        conn = connections.get_by_name(name)
        if not conn:
            available = ", ".join(connections.names()) or "нет сохранённых"
            return (
                f"Подключение '{name}' не найдено. Доступные: {available}. "
                f"Используй ask_user чтобы запросить у пользователя API-ключ или логин/пароль — "
                f"они автоматически сохранятся в подключения."
            )
        return json.dumps({"name": conn["name"], "type": conn["type"], "fields": conn["fields"]},
                          ensure_ascii=False)

    async def _report_connection_error(platform: str, error: str) -> None:
        """Публикует событие ошибки подключения чтобы пользователь видел в интерфейсе."""
        await publish({"type": "connection_error", "agent_id": agent_id,
                       "platform": platform, "error": error,
                       "text": f"❌ Ошибка подключения к {platform}: {error}"})
        await publish({"type": "speech", "agent_id": agent_id,
                       "text": f"❌ Не могу подключиться к {platform}: {error[:100]}"})

    async def run() -> str:
        model = models_module.for_agent(agent_id)
        await publish({"type": "thinking", "agent_id": agent_id,
                       "text": f"Начинаю работу: {task[:80]}..."})

        result = await llm.run_agent(
            system=system,
            user=task,
            model=model,
            max_tokens=3000,
            max_iterations=8,
            use_search=True,
            publish=publish,
            agent_id=agent_id,
            extra_tools=[_REQUEST_RESEARCH_TOOL, _ASK_USER_TOOL, _SEND_MESSAGE_TOOL,
                         _READ_MESSAGES_TOOL, _GET_CONNECTION_TOOL],
            tool_handlers={
                "request_research": _handle_request_research,
                "ask_user": _handle_ask_user,
                "send_message": _handle_send_message,
                "read_messages": _handle_read_messages,
                "get_connection": _handle_get_connection,
            },
        )

        state.save_deliverable(agent_id, role, task, result)
        await publish({"type": "task_done", "agent_id": agent_id, "summary": result[:300]})
        return result

    return run
