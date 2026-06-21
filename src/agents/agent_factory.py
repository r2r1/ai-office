"""
Фабрика агентов — создаёт нового агента по роли и задаче.
Работает через единое ядро llm.py.

Любой агент может запросить ресёрчера через инструмент request_research.
"""

import json
import re
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
from src.office import office_channel
from src.office import threads as threads_module
from src.office import workspace as workspace_module
from src.integrations import registry as integrations_registry

_AUTONOMY_RULES = """
=== АВТОНОМНОСТЬ (ОБЯЗАТЕЛЬНО) ===
Никогда не проси пользователя делать что-то руками — делай через API сам.
Нужен сервис: 1) get_connection, 2) если нет — ask_user за API-ключом с инструкцией где взять.
Выдавай РЕАЛЬНЫЙ результат: лендинг — publish через website, пост — через интеграцию.
Сначала вызови list_integrations, чтобы узнать что доступно."""

_INTER_AGENT_SUFFIX = (
    "\nМожешь писать агентам через send_message / read_messages."
    "\nЕсли подключение не работает — опиши ошибку конкретно."
)

ROLE_PROMPTS = {
    "salesman": (
        "Ты — агент продаж AI-агентства. Найди потенциальных клиентов, придумай "
        "оффер и напиши холодное сообщение. Конкретно: компании, каналы, текст. "
        "Используй web_search для актуальных данных."
    ),
    "developer": (
        "Ты — разработчик AI-агентства. Ты ПИШЕШЬ РЕАЛЬНЫЙ КОД, а не описываешь его. "
        "Рабочий цикл:\n"
        "1. list_files — посмотри, что уже написано (не дублируй).\n"
        "2. write_file — пиши код: бот/сайт на Python (aiogram/FastAPI), requirements.txt, README.md "
        "с инструкцией запуска. Платные конструкторы (BotsBox/Tilda) не используй без одобрения клиента.\n"
        "3. verify_code — проверь компиляцию. Есть ошибки → исправь через write_file и проверь снова, "
        "пока не станет ✅.\n"
        "4. Когда код готов и проверен — СПРОСИ пользователя через ask_user: всё ли устраивает и можно ли "
        "запушить в GitHub (укажи имя репозитория). Без явного одобрения НЕ пушь.\n"
        "5. После одобрения — use_integration('github','create_repo',{name}) затем "
        "use_integration('github','push',{repo}).\n"
        "Используй web_search для актуального синтаксиса библиотек."
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
    "integrator": (
        "Ты — агент-интегратор AI-агентства. Ты отвечаешь за реальные подключения "
        "офиса к внешним сервисам (Telegram, и т.д.). Алгоритм работы:\n"
        "1. Вызови list_integrations — посмотри, что доступно и что уже подключено.\n"
        "2. Если для задачи нужен сервис без учётных данных — запроси их через ask_user "
        "с конкретной инструкцией как получить (она есть в описании интеграции).\n"
        "3. Как только учётка появилась — проверь подключение реальным действием "
        "(например telegram.get_me через use_integration) и доложи статус.\n"
        "4. Выполняй реальные действия в сервисах через use_integration по запросу команды.\n"
        "Никогда не проси пользователя делать ручную работу в сервисе — делай через API сам."
    ),
}

# Инструмент: задать вопрос пользователю
_ASK_USER_TOOL = {
    "type": "function",
    "function": {
        "name": "ask_user",
        "description": "Задаёт вопрос пользователю (только для API-ключей или бизнес-уточнений).",
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
        "description": "Возвращает сохранённые учётные данные платформы (API-ключ/токен). Если нет — запроси через ask_user.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Название платформы (например: Instagram, OpenAI, Telegram)"},
            },
            "required": ["name"],
        },
    },
}

# Инструмент: читать общий чат офиса
_READ_OFFICE_CHAT_TOOL = {
    "type": "function",
    "function": {
        "name": "read_office_chat",
        "description": "Читает общий чат офиса. Проверяй перед ask_user — ключ мог получить другой агент.",
        "parameters": {
            "type": "object",
            "properties": {
                "n": {"type": "integer", "description": "Количество последних сообщений (по умолчанию 20)", "default": 20},
            },
            "required": [],
        },
    },
}

# Инструмент: список доступных интеграций
_LIST_INTEGRATIONS_TOOL = {
    "type": "function",
    "function": {
        "name": "list_integrations",
        "description": "Список интеграций с внешними сервисами: доступные действия и статус подключения. Вызови перед use_integration.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

# Инструмент: выполнить реальное действие во внешнем сервисе
_USE_INTEGRATION_TOOL = {
    "type": "function",
    "function": {
        "name": "use_integration",
        "description": "Выполняет действие во внешнем сервисе. Учётные данные подтягиваются автоматически. Перед вызовом смотри list_integrations.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Имя интеграции (например 'telegram')"},
                "action": {"type": "string", "description": "Имя действия (например 'send_message')"},
                "params": {"type": "object", "description": "Аргументы действия (см. list_integrations)"},
            },
            "required": ["name", "action"],
        },
    },
}

# Инструменты: писать реальный код в рабочую папку проекта
_WRITE_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "write_file",
        "description": "Создаёт/перезаписывает файл в рабочей папке проекта. Пиши реальный код, а не описание.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Путь файла внутри проекта (относительный)"},
                "content": {"type": "string", "description": "Полное содержимое файла"},
            },
            "required": ["path", "content"],
        },
    },
}

_READ_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Читает файл из рабочей папки проекта по относительному пути.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Путь файла"}},
            "required": ["path"],
        },
    },
}

_LIST_FILES_TOOL = {
    "type": "function",
    "function": {
        "name": "list_files",
        "description": "Показывает все файлы проекта в рабочей папке (что уже написано).",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

_VERIFY_CODE_TOOL = {
    "type": "function",
    "function": {
        "name": "verify_code",
        "description": "Проверяет компиляцию .py файлов. Вызывай после write_file и до предложения пушить в GitHub.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

# Инструмент: запросить ресёрчера
_REQUEST_RESEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "request_research",
        "description": "Запрашивает ресёрчера. depth='quick' (по умолчанию) или 'deep'.",
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
        m = re.search(r'(?:для|к|for|of)\s+([a-zа-я0-9_\-]+)', q_lower)
        platform = m.group(1).capitalize() if m else "Сервис"

    # Тип подключения
    if words & {"password", "пароль", "login", "логин"}:
        conn_type = "login"
        # Пробуем разобрать "login: X password: Y" или "логин: X пароль: Y"
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
            "note": "Автосохранено агентом при ответе на вопрос"}


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


def create(role: str, task: str, agent_id: str, publish: Callable[[dict], Awaitable[None]], skill: str = ""):
    """Возвращает async-функцию, запускающую агента."""
    base = ROLE_PROMPTS.get(role, f"Ты — {role} агент AI-агентства. Выполни задачу профессионально.")
    skill_line = f"\n\nТвоя специализация в этом проекте: {skill}" if skill else ""
    # Собираем системный промпт: роль + специализация + бриф + память + правила автономности + межагентный суффикс
    system = base + skill_line + _brief_context() + memory_module.context_block() + _AUTONOMY_RULES + _INTER_AGENT_SUFFIX

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
        # Вопрос попадает в личный чат с агентом — пользователь ответит прямо там
        threads_module.post(agent_id, "agent", question_text, kind="question", question_id=qid)
        await publish({"type": "agent_message", "agent_id": agent_id, "from": "agent",
                       "kind": "question", "question_id": qid, "text": question_text})
        try:
            answer = await asyncio.wait_for(fut, timeout=300)  # 5 мин макс
        except asyncio.TimeoutError:
            questions_module.answer(qid, "")
            threads_module.mark_answered(qid)
            await publish({"type": "question_answered", "question_id": qid, "agent_id": agent_id})
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
                # Оповещаем всех агентов через общий канал
                office_channel.post(
                    "system", "system",
                    f"🔑 API-ключ для '{saved['name']}' получен и сохранён. "
                    f"Все агенты могут использовать get_connection('{saved['name']}') — "
                    f"не спрашивайте пользователя повторно."
                )
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

    async def _handle_read_office_chat(args: dict) -> str:
        n = args.get("n", 20)
        msgs = office_channel.recent(n)
        if not msgs:
            return "Общий чат пуст."
        lines = [f"[{m['from']}]: {m['text']}" for m in msgs]
        return "\n".join(lines)

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

    async def _handle_write_file(args: dict) -> str:
        path = args.get("path", "")
        content = args.get("content", "")
        res = workspace_module.write_file(path, content)
        await _publish_and_log({"type": "speech", "agent_id": agent_id, "text": f"📝 {res}"})
        await publish({"type": "file_written", "agent_id": agent_id, "path": path,
                       "text": f"📝 {agent_id}: {res}"})
        return res

    async def _handle_read_file(args: dict) -> str:
        return workspace_module.read_file(args.get("path", ""))

    async def _handle_list_files(args: dict) -> str:
        return workspace_module.tree_text()

    async def _handle_verify_code(args: dict) -> str:
        res = workspace_module.verify_text()
        await _publish_and_log({"type": "speech", "agent_id": agent_id, "text": f"🧪 {res[:120]}"})
        return res

    async def _handle_list_integrations(args: dict) -> str:
        lines = []
        for integ in integrations_registry.all_integrations():
            status = "✅ подключено" if integrations_registry.is_connected(integ) else "⚪ не подключено"
            acts = ", ".join(
                f"{a.name}({', '.join(a.required) or '—'})" for a in integ.actions.values()
            )
            lines.append(f"• {integ.name} [{status}] — {integ.description}\n    действия: {acts}")
        if not lines:
            return "Пока нет доступных интеграций."
        return "Доступные интеграции:\n" + "\n".join(lines)

    async def _handle_use_integration(args: dict) -> str:
        name = (args.get("name") or "").strip()
        action_name = (args.get("action") or "").strip()
        params = args.get("params") or {}
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                params = {}

        integ = integrations_registry.get(name)
        if not integ:
            avail = ", ".join(i.name for i in integrations_registry.all_integrations()) or "нет"
            return f"Интеграция '{name}' не найдена. Доступные: {avail}."
        action = integ.actions.get(action_name)
        if not action:
            acts = ", ".join(integ.actions.keys())
            return f"У '{integ.name}' нет действия '{action_name}'. Доступные действия: {acts}."

        creds = integrations_registry.credentials_for(integ)
        if not integrations_registry.is_connected(integ):
            if getattr(integ, "oauth_url", ""):
                return (
                    f"Сервис '{integ.title}' не подключён. НЕ проси API-ключ. "
                    f"Попроси пользователя через ask_user нажать кнопку «Подключить {integ.title}» "
                    f"в разделе «Доступы» (вход по аккаунту, OAuth). После подключения повтори действие."
                )
            return (
                f"Сервис '{integ.title}' ещё не подключён — нет учётных данных. "
                f"Запроси их у пользователя через ask_user. Как получить:\n{integ.how_to}"
            )

        await _publish_and_log({"type": "speech", "agent_id": agent_id,
                                "text": f"⚙️ {integ.title}.{action_name}…"})
        try:
            result = await action.handler(creds, params)
        except Exception as e:
            err = str(e)[:200]
            await _report_connection_error(integ.title, err)
            return f"Ошибка при вызове {integ.name}.{action_name}: {err}"

        await _publish_and_log({"type": "speech", "agent_id": agent_id,
                                "text": f"✅ {integ.title}.{action_name}: {result[:80]}"})
        await publish({"type": "integration_used", "agent_id": agent_id,
                       "integration": integ.name, "action": action_name,
                       "text": f"⚙️ {integ.title}.{action_name} → {result[:120]}"})
        return result

    async def _report_connection_error(platform: str, error: str) -> None:
        """Публикует событие ошибки подключения чтобы пользователь видел в интерфейсе."""
        await publish({"type": "connection_error", "agent_id": agent_id,
                       "platform": platform, "error": error,
                       "text": f"❌ Ошибка подключения к {platform}: {error}"})
        await publish({"type": "speech", "agent_id": agent_id,
                       "text": f"❌ Не могу подключиться к {platform}: {error[:100]}"})

    async def _publish_and_log(event: dict) -> None:
        """Обёртка над publish: speech-события агентов дублируются в общий канал."""
        await publish(event)
        if event.get("type") == "speech" and event.get("agent_id") == agent_id:
            office_channel.post(agent_id, role, event.get("text", ""))

    async def run() -> str:
        model = models_module.for_agent(agent_id)
        await _publish_and_log({"type": "thinking", "agent_id": agent_id,
                                 "text": f"Начинаю работу: {task[:80]}..."})

        result = await llm.run_agent(
            system=system,
            user=task,
            model=model,
            max_tokens=2000,
            max_iterations=6,
            max_searches=4,
            use_search=True,
            publish=_publish_and_log,
            agent_id=agent_id,
            extra_tools=[_REQUEST_RESEARCH_TOOL, _ASK_USER_TOOL, _SEND_MESSAGE_TOOL,
                         _READ_MESSAGES_TOOL, _GET_CONNECTION_TOOL, _READ_OFFICE_CHAT_TOOL,
                         _LIST_INTEGRATIONS_TOOL, _USE_INTEGRATION_TOOL,
                         _WRITE_FILE_TOOL, _READ_FILE_TOOL, _LIST_FILES_TOOL, _VERIFY_CODE_TOOL],
            tool_handlers={
                "request_research": _handle_request_research,
                "ask_user": _handle_ask_user,
                "send_message": _handle_send_message,
                "read_messages": _handle_read_messages,
                "read_office_chat": _handle_read_office_chat,
                "get_connection": _handle_get_connection,
                "list_integrations": _handle_list_integrations,
                "use_integration": _handle_use_integration,
                "write_file": _handle_write_file,
                "read_file": _handle_read_file,
                "list_files": _handle_list_files,
                "verify_code": _handle_verify_code,
            },
        )

        state.save_deliverable(agent_id, role, task, result)
        await publish({"type": "task_done", "agent_id": agent_id, "summary": result[:300]})
        return result

    return run
