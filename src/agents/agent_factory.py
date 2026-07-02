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
from src.office import state
from src.office import connections
from src.office import memory as memory_module
from src.office import models as models_module
from src.office import office_channel
from src.office import threads as threads_module
from src.office import workspace as workspace_module
from src.office import registry as registry_module
from src.office import tool_router
from src.office import skills as skills_module
from src.office import events as events_module
from src.integrations import registry as integrations_registry

# Тексты ролей и командные политики переехали в файлы (Prompt Builder — единая
# сборка): роли — src/office/builtin_roles/<role>.md (читает roles.py), политики
# (автономность, «артефакты только через инструменты», межагентность, правила
# лидера) — src/office/policies/*.md (читает prompt_builder.policy). Здесь остались
# только инструменты агентов и их обработчики.

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

# Инструмент: СПРОСИТЬ коллегу и сразу получить ответ (синхронная консультация)
_ASK_COLLEAGUE_TOOL = {
    "type": "function",
    "function": {
        "name": "ask_colleague",
        "description": "Задать КОНКРЕТНЫЙ вопрос коллеге нужной роли и СРАЗУ получить ответ "
                       "(он отвечает на основе своей работы и контекста). Используй, когда тебе "
                       "нужен вход другого специалиста: текст/оффер у marketer, данные у analyst, "
                       "оценка дизайна у designer, тех-проверка у developer, проектное решение у architect. "
                       "Это не передача задачи — это короткая консультация по делу.",
        "parameters": {
            "type": "object",
            "properties": {
                "role": {"type": "string", "description": "Роль коллеги: marketer, designer, developer, "
                         "analyst, architect, integrator, salesman, researcher"},
                "question": {"type": "string", "description": "Конкретный вопрос (одно-два предложения)"},
            },
            "required": ["role", "question"],
        },
    },
}

# Инструмент: поднять СОБЫТИЕ в компанию (Event Layer) — не конкретному коллеге, а CEO
_RAISE_EVENT_TOOL = {
    "type": "function",
    "function": {
        "name": "raise_event",
        "description": "Сообщить КОМПАНИИ важный сигнал, не дёргая конкретного коллегу: "
                       "проблему, блокер, найденную возможность или наблюдение, которое "
                       "касается других отделов. CEO увидит это, интерпретирует и решит, "
                       "что делать (поставит задачу нужному отделу). Используй, когда "
                       "обнаружил что-то выходящее за рамки твоей задачи: «конверсия лендинга "
                       "низкая», «нашёл прибыльный канал», «нет данных от аналитика».",
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["problem", "blocker", "opportunity", "signal", "info"],
                         "description": "Тип сигнала"},
                "summary": {"type": "string", "description": "Суть одной фразой"},
                "detail": {"type": "string", "description": "Детали и рекомендация (опционально)"},
            },
            "required": ["kind", "summary"],
        },
    },
}

# Инструмент: поставить задачу коллеге на общую доску (видна в его to-do и у его лидера)
_DELEGATE_TASK_TOOL = {
    "type": "function",
    "function": {
        "name": "delegate_task",
        "description": "Поставить ЗАДАЧУ коллеге другой роли на общую доску задач. В отличие от "
                       "ask_colleague (быстрый вопрос-ответ) это полноценная задача: попадёт в "
                       "to-do исполнителя нужной роли и будет отслеживаться его лидером. Используй, "
                       "когда тебе нужно, чтобы коллега ЧТО-ТО СДЕЛАЛ (а не просто ответил).",
        "parameters": {
            "type": "object",
            "properties": {
                "role": {"type": "string", "description": "Роль исполнителя (developer, designer, "
                         "marketer, analyst, integrator, salesman)"},
                "title": {"type": "string", "description": "Что нужно сделать (конкретно)"},
                "done_criterion": {"type": "string", "description": "Когда задача считается выполненной"},
            },
            "required": ["role", "title"],
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

# Инструмент: Tool Router — опиши потребность словами, инструмент подберётся сам
_USE_CAPABILITY_TOOL = {
    "type": "function",
    "function": {
        "name": "use_capability",
        "description": "Опиши ПОТРЕБНОСТЬ обычными словами («опубликовать лендинг», "
                       "«отправить сообщение в telegram», «создать репозиторий»), а система "
                       "сама подберёт нужный внешний инструмент и выполнит. Не нужно знать "
                       "точные имена интеграций/действий — это делает роутер. Если нужен "
                       "конкретный сервис с параметрами — используй use_integration.",
        "parameters": {
            "type": "object",
            "properties": {
                "need": {"type": "string", "description": "Что нужно сделать, своими словами"},
                "params": {"type": "object", "description": "Параметры для действия (если знаешь): "
                           "например {chat_id, text} для сообщения, {slug, html} для лендинга"},
            },
            "required": ["need"],
        },
    },
}

# Инструмент: Skills — получить экспертный плейбук «как делать» под тип работы.
# Роль больше не держит «как» в промпте: воркер описывает потребность и берёт скилл.
_USE_SKILL_TOOL = {
    "type": "function",
    "function": {
        "name": "use_skill",
        "description": "Когда задача требует специального подхода (например «3D-сайт с "
                       "анимациями», «лендинг на framer motion»), опиши потребность словами — "
                       "система подберёт готовый СКИЛЛ и вернёт экспертный плейбук: структуру "
                       "файлов, приёмы и проверки. Дальше выполняй плейбук своими инструментами "
                       "(write_file и т.д.). Вызывай ПЕРЕД тем как писать код, если сомневаешься «как».",
        "parameters": {
            "type": "object",
            "properties": {
                "need": {"type": "string", "description": "Что нужно сделать, своими словами"},
            },
            "required": ["need"],
        },
    },
}

# Инструмент: ПОСМОТРЕТЬ каталог скиллов (дискавери, внутренний find-skills).
# В отличие от use_skill (сразу берёт один плейбук) — показывает СПИСОК доступных
# способов под запрос, чтобы лидер/воркер понял, что вообще умеет офис, и выбрал.
_FIND_SKILLS_TOOL = {
    "type": "function",
    "function": {
        "name": "find_skills",
        "description": "Ищет по каталогу готовых скиллов офиса и возвращает СПИСОК подходящих "
                       "(название + что делает). Используй для разведки: понять, какие способы "
                       "есть под задачу, прежде чем брать конкретный через use_skill. Пустой "
                       "запрос → покажет все доступные тебе скиллы.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Что ищешь, своими словами (можно пусто — покажет весь каталог)"},
            },
            "required": [],
        },
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
                "path": {"type": "string", "description": "Путь файла внутри проекта (относительный, НЕ пустой). Примеры: index.html, bot.py, styles.css, src/app.js"},
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

_EXECUTE_CODE_TOOL = {
    "type": "function",
    "function": {
        "name": "execute_code",
        "description": "Запускает файл из рабочей папки (ТОЛЬКО .py, .js, .sh) и возвращает вывод. "
                       "НЕ вызывай на .html/.css — их запустить нельзя, для сайта это всегда «Неизвестный "
                       "тип файла»; для проверки HTML используй verify_code или просто перечитай файл. "
                       "НЕ вызывай на site/*.js — это браузерный скрипт (document/window), Node выдаст "
                       "«document is not defined», это НЕ значит, что код сломан — просто перечитай файл.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Путь файла (например 'main.py', 'scripts/calc.py')"},
                "stdin": {"type": "string", "description": "Входные данные для скрипта (опционально)"},
            },
            "required": ["path"],
        },
    },
}

_DELETE_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "delete_file",
        "description": "Удаляет файл из рабочей папки проекта.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Путь файла для удаления"}},
            "required": ["path"],
        },
    },
}

# Инструмент: настроить встроенного бота записи (услуги/приветствие) перед launch_bot
_CONFIGURE_BOT_TOOL = {
    "type": "function",
    "function": {
        "name": "configure_bot",
        "description": "Настраивает встроенного Telegram-бота записи ПЕРЕД launch_bot: список услуг "
                       "(кнопки), какие поля собирать, приветствие. Бери значения из разговора с "
                       "пользователем, НЕ из брифа. Без вызова бот спрашивает имя+телефон по умолчанию.",
        "parameters": {
            "type": "object",
            "properties": {
                "services": {"type": "array", "items": {"type": "string"},
                             "description": "Список услуг для кнопок (например: ['Кухня','Шкаф-купе'])"},
                "ask_fields": {"type": "array", "items": {"type": "string"},
                               "description": "Какие поля собрать (по умолчанию ['Имя','Телефон'])"},
                "greeting": {"type": "string", "description": "Приветствие бота"},
                "success_message": {"type": "string", "description": "Сообщение после оформления заявки"},
            },
            "required": [],
        },
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


def create(role: str, task: str, agent_id: str, publish: Callable[[dict], Awaitable[None]], skill: str = ""):
    """Возвращает async-функцию, запускающую агента."""
    # Системный промпт собирает Prompt Builder (роли/политики — .md-файлы,
    # сборка централизована, см. docs/bos-architecture.md §7). Полный промпт
    # логируется в prompts.jsonl тенанта — отладка мышления зрячая.
    from src.office import prompt_builder
    system = prompt_builder.build(role, task, agent_id, skill=skill)
    prompt_builder.log_prompt(agent_id, role, system, task)

    async def _handle_request_research(args: dict) -> str:
        question = args.get("question", "")
        depth = args.get("depth", "quick")
        await publish({"type": "speech", "agent_id": agent_id,
                       "text": f"📡 Запрашиваю ресёрчера [{depth}]: {question[:60]}"})
        # видно в общем чате: кто у кого что запросил
        office_channel.post(agent_id, role, f"@ресёрчер, нужны данные: {question[:160]}")
        await publish({"type": "office_chat", "from": agent_id, "role": role,
                       "text": f"@ресёрчер, нужны данные: {question[:160]}"})
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

    async def _handle_ask_colleague(args: dict) -> str:
        """Синхронная консультация: коллега нужной роли отвечает на вопрос ОДНИМ
        бесшумным LLM-вызовом (без инструментов → без рекурсии и циклов)."""
        col_role = (args.get("role") or "").strip()
        question = (args.get("question") or "").strip()
        if not col_role or not question:
            return "Укажи роль коллеги и конкретный вопрос."
        if col_role == role:
            return "Это твоя же роль — реши сам, без консультации."
        # Находим коллегу этой роли (или отвечаем «от лица роли», если он ещё не нанят)
        colleague = next((a for a in registry_module.all_agents() if a.role == col_role), None)
        col_id = colleague.agent_id if colleague else f"{col_role}_1"
        col_work = state.result_for(col_id) if colleague else ""
        from src.office import roles as roles_module
        col_base = roles_module.render(col_role)
        await publish({"type": "speech", "agent_id": agent_id,
                       "text": f"💬 спрашиваю {col_role}: {question[:60]}"})
        # вопрос коллеге виден в общем чате
        office_channel.post(agent_id, role, f"@{col_role}, {question[:200]}")
        await publish({"type": "office_chat", "from": agent_id, "role": role,
                       "text": f"@{col_role}, {question[:200]}"})
        sys = (col_base + prompt_builder.brief_block()
               + ("\n\n=== ТВОЯ ПОСЛЕДНЯЯ РАБОТА (опирайся на неё) ===\n" + col_work[:1500]
                  if col_work else "")
               + "\n\nКоллега по команде задаёт тебе вопрос. Ответь КОРОТКО, конкретно и по делу "
                 "(без воды), чтобы он сразу мог использовать ответ в работе.")
        try:
            answer = await llm.run_agent(
                system=sys, user=question,
                model=models_module.for_agent(col_id),
                max_tokens=600, use_search=False, agent_id=col_id,
            )
        except Exception as e:
            return f"Коллега {col_role} не смог ответить: {str(e)[:80]}. Реши сам."
        answer = (answer or "").strip() or "Коллега не дал содержательного ответа — реши сам."
        await publish({"type": "speech", "agent_id": col_id,
                       "text": f"💬 → {agent_id}: {answer[:80]}"})
        # ответ коллеги виден в общем чате
        office_channel.post(col_id, col_role, f"@{role}: {answer[:240]}")
        await publish({"type": "office_chat", "from": col_id, "role": col_role,
                       "text": f"@{role}: {answer[:240]}"})
        return f"Ответ {col_role}: {answer}"

    async def _handle_raise_event(args: dict) -> str:
        kind = (args.get("kind") or "signal").strip()
        summary = (args.get("summary") or "").strip()
        detail = (args.get("detail") or "").strip()
        if not summary:
            return "Опиши суть сигнала одной фразой."
        ev = events_module.raise_event(kind, summary, detail, from_role=role, from_agent=agent_id)
        if not ev:
            return "Событие не создано (пустая суть)."
        label = events_module.KINDS.get(ev["kind"], ev["kind"])
        await _publish_and_log({"type": "speech", "agent_id": agent_id,
                                "text": f"📨 Сигнал компании [{label}]: {summary[:70]}"})
        await publish({"type": "department_event", "agent_id": agent_id, "kind": ev["kind"],
                       "text": f"{label} от {role}: {summary[:120]}"})
        return ("Событие передано CEO — он интерпретирует его и при необходимости поручит "
                "нужному отделу. Продолжай свою задачу.")

    async def _handle_delegate_task(args: dict) -> str:
        from src.office import plan as plan_module
        from src.office import roles as roles_module
        col_role = (args.get("role") or "").strip()
        title = (args.get("title") or "").strip()
        if not col_role or not title:
            return "Укажи роль исполнителя и что нужно сделать."
        if col_role == role:
            return "Это твоя зона — сделай сам, не делегируй себе."
        if col_role not in roles_module.known_roles():
            valid = ", ".join(sorted(roles_module.known_roles()))
            return (f"Роли «{col_role}» не существует в офисе — задача НЕ поставлена. "
                    f"Реальные роли: {valid}.")
        t = plan_module.add_task(title, col_role, args.get("done_criterion", ""),
                                 requested_by=agent_id)
        await publish({"type": "speech", "agent_id": agent_id,
                       "text": f"📌 Поставил задачу {col_role}: {title[:50]}"})
        office_channel.post(agent_id, role, f"📌 @{col_role}, задача: {title[:160]}")
        await publish({"type": "office_chat", "from": agent_id, "role": role,
                       "text": f"📌 @{col_role}, задача: {title[:160]}"})
        return (f"Задача поставлена {col_role} (id={t['id']}) и добавлена на доску — "
                f"его лидер назначит исполнителя. Можешь продолжать своё.")

    async def _handle_send_message(args: dict) -> str:
        to_agent_id = (args.get("to_agent_id") or "").strip()
        message = args.get("message", "")
        if not registry_module.get(to_agent_id):
            real = ", ".join(a.agent_id for a in registry_module.all_agents()) or "пока никто не нанят"
            return f"Агента «{to_agent_id}» не существует — сообщение НЕ отправлено. Реальные коллеги: {real}."
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
        path = (args.get("path") or "").strip()
        content = args.get("content", "")
        # Самолечение: developer/designer/integrator иногда забывают префикс site/ у
        # веб-файла (видели в проде: 9 html-страниц подряд ушли в корень workspace
        # вместо site/) — тогда авто-публикация начинает читать/показывать клиенту
        # РАСХОДЯЩУЮСЯ копию, а правки в реальном site/ становятся невидимы. Нормализуем
        # путь ДО записи, а не патчим последствия на стороне чтения.
        if (role in ("developer", "designer", "integrator") and path
                and "/" not in path and path.lower().endswith((".html", ".css", ".js"))):
            path = f"site/{path}"
        res = workspace_module.write_file(path, content)
        await _publish_and_log({"type": "speech", "agent_id": agent_id, "text": f"📝 {res}"})
        if res.startswith("Файл сохранён:"):
            # Извлекаем реальный путь из ответа: «Файл сохранён: <path> (N символов).»
            actual_path = res.split(":", 1)[1].strip().split(" (")[0]
            await publish({"type": "file_written", "agent_id": agent_id, "path": actual_path,
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

    async def _handle_execute_code(args: dict) -> str:
        path = args.get("path", "")
        stdin = args.get("stdin", "")
        await _publish_and_log({"type": "speech", "agent_id": agent_id, "text": f"▶️ Запускаю {path}…"})
        res = workspace_module.execute_code(path, stdin)
        short = res[:200].replace("\n", " ")
        await _publish_and_log({"type": "speech", "agent_id": agent_id, "text": f"📤 {short}"})
        await publish({"type": "code_executed", "agent_id": agent_id, "path": path,
                       "text": f"▶️ {agent_id}: {path} → {short}"})
        return res

    async def _handle_delete_file(args: dict) -> str:
        path = args.get("path", "")
        res = workspace_module.delete_file(path)
        await _publish_and_log({"type": "speech", "agent_id": agent_id, "text": f"🗑 {res}"})
        return res

    async def _handle_configure_bot(args: dict) -> str:
        from src.office import bot_config
        patch = {}
        for k in ("services", "ask_fields", "greeting", "success_message"):
            if args.get(k) is not None:
                patch[k] = args[k]
        cfg = bot_config.update(patch)
        await _publish_and_log({"type": "speech", "agent_id": agent_id,
                                "text": f"⚙️ Настроил бота: услуги={cfg.get('services') or '—'}"})
        return (f"Конфиг бота обновлён. Услуги: {cfg.get('services') or 'нет (спросит имя+телефон)'}, "
                f"поля: {cfg.get('ask_fields')}. Теперь можно launch_bot.")

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

    async def _execute_integration(name: str, action_name: str, params: dict) -> str:
        """Ядро вызова интеграции — общее для use_integration и use_capability."""
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

        # Гейт автономии для ВНЕШНЕ-видимых действий: на уровнях ниже требуемого офис
        # не выполняет действие сам, а просит OK клиента. website публикует через свой
        # гейт (loop._publish_site_auto), поэтому его здесь не дублируем.
        if integ.name != "website":
            from src.office import autonomy
            act_type = autonomy._action_type_for(action_name)
            if autonomy.needs_approval(act_type):
                return (f"Действие «{integ.title}.{action_name}» затрагивает внешний мир, а уровень "
                        f"автономии «{autonomy.get_level()}» (только рекомендации) не позволяет офису "
                        f"делать это самостоятельно. НЕ повторяй вызов: сообщи клиенту через ask_user, "
                        f"что рекомендуешь сделать, и предложи повысить уровень автономии в «Компания», "
                        f"если он хочет, чтобы офис выполнял такое сам.")

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
            result = await action.handler(creds, params or {})
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

    async def _handle_use_integration(args: dict) -> str:
        return await _execute_integration(
            (args.get("name") or "").strip(),
            (args.get("action") or "").strip(),
            args.get("params") or {},
        )

    async def _handle_use_capability(args: dict) -> str:
        """Tool Router: потребность словами → подбор интеграции+действия → исполнение."""
        need = (args.get("need") or "").strip()
        params = args.get("params") or {}
        if not need:
            return "Опиши потребность словами (например «опубликовать лендинг»)."
        match = tool_router.best(need)
        if match:
            await _publish_and_log({"type": "speech", "agent_id": agent_id,
                                    "text": f"🧭 «{need[:50]}» → {match['title']}.{match['action']}"})
            return await _execute_integration(match["integration"], match["action"], params)
        # Неоднозначно или нет совпадений — показываем варианты, пусть агент выберет
        cands = tool_router.route(need, top=3)
        if not cands:
            avail = ", ".join(i.name for i in integrations_registry.all_integrations())
            return (f"Под потребность «{need}» не нашёл готового инструмента. "
                    f"Доступные интеграции: {avail}. Посмотри list_integrations.")
        lines = "\n".join(
            f"- {c['integration']}.{c['action']} ({c['title']}, {'✅' if c['connected'] else '⚪'})"
            for c in cands
        )
        return ("Уточни — под эту потребность подходят несколько инструментов. "
                f"Вызови use_integration с нужным:\n{lines}")

    async def _handle_use_skill(args: dict) -> str:
        """Skills: потребность словами → подбор скилла → его экспертный плейбук."""
        need = (args.get("need") or "").strip()
        if not need:
            return "Опиши потребность словами (например «3D-лендинг с анимациями»)."
        skill = skills_module.match(need, role)
        if skill:
            await _publish_and_log({"type": "speech", "agent_id": agent_id,
                                    "text": f"🧩 Беру скилл «{skill.title}»"})
            await publish({"type": "skill_used", "agent_id": agent_id,
                           "skill": skill.id, "text": f"🧩 Скилл «{skill.title}»"})
            if skill.handler:
                return await skill.handler({"need": need})
            return skill.playbook or f"Скилл «{skill.title}»: {skill.description}"
        cands = skills_module.suggestions(need, role, top=3)
        if not cands:
            avail = skills_module.catalog_for(role) or "пока нет подходящих"
            return (f"Под потребность «{need}» готового скилла нет — делай напрямую "
                    f"своими инструментами. Доступные скиллы: {avail}.")
        lines = "\n".join(f"- {s.title}: {s.description}" for s in cands)
        return f"Уточни — подходят несколько скиллов:\n{lines}"

    async def _handle_find_skills(args: dict) -> str:
        """Дискавери каталога скиллов (внутренний find-skills): вернуть СПИСОК
        подходящих способов, чтобы воркер/лидер выбрал и взял через use_skill."""
        query = (args.get("query") or "").strip()
        found = skills_module.search(query, role, top=6)
        if not found:
            return "В каталоге пока нет скиллов, доступных твоей роли — делай напрямую."
        lines = "\n".join(f"• {s.title} — {s.description}" for s in found)
        head = (f"Скиллы под «{query}»:" if query else "Доступные тебе скиллы:")
        return (f"{head}\n{lines}\n\nЧтобы взять нужный — вызови use_skill с "
                f"потребностью словами, получишь его экспертный плейбук.")

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

        # Роли, пишущие реальный код/HTML, генерируют большие файлы — им нужен
        # высокий лимит, иначе аргументы write_file обрезаются и файл выходит пустым.
        max_tok = 16000 if role in ("developer", "designer", "integrator") else 2000
        # Разработчику и дизайнеру нужно больше итераций: читать файлы + писать
        # несколько файлов (bot.py, config.py, requirements.txt и т.д.)
        # marketer/integrator тоже часто упираются в лимит: list_integrations + 2-3
        # read_file + web_search + 3 write_file (offer/site_content/bot_content) — это
        # уже 7-8 tool-calls, и модель не успевает написать итоговый текст (реальный
        # кейс: marketer сдавал out_len=0 на 8 итерациях, задача перезапускалась с нуля).
        max_iter = 15 if role in ("developer", "designer") else 10

        result = await llm.run_agent(
            system=system,
            user=task,
            model=model,
            max_tokens=max_tok,
            max_iterations=max_iter,
            max_searches=4,
            use_search=True,
            publish=_publish_and_log,
            agent_id=agent_id,
            extra_tools=[_REQUEST_RESEARCH_TOOL, _ASK_USER_TOOL, _ASK_COLLEAGUE_TOOL,
                         _RAISE_EVENT_TOOL, _DELEGATE_TASK_TOOL, _GET_CONNECTION_TOOL,
                         _READ_OFFICE_CHAT_TOOL,
                         _LIST_INTEGRATIONS_TOOL, _USE_CAPABILITY_TOOL, _USE_INTEGRATION_TOOL,
                         _USE_SKILL_TOOL, _FIND_SKILLS_TOOL,
                         _WRITE_FILE_TOOL, _READ_FILE_TOOL, _LIST_FILES_TOOL, _VERIFY_CODE_TOOL,
                         _EXECUTE_CODE_TOOL, _DELETE_FILE_TOOL, _CONFIGURE_BOT_TOOL],
            tool_handlers={
                "request_research": _handle_request_research,
                "ask_user": _handle_ask_user,
                "ask_colleague": _handle_ask_colleague,
                "raise_event": _handle_raise_event,
                "delegate_task": _handle_delegate_task,
                "read_office_chat": _handle_read_office_chat,
                "get_connection": _handle_get_connection,
                "list_integrations": _handle_list_integrations,
                "use_capability": _handle_use_capability,
                "use_skill": _handle_use_skill,
                "find_skills": _handle_find_skills,
                "use_integration": _handle_use_integration,
                "write_file": _handle_write_file,
                "read_file": _handle_read_file,
                "list_files": _handle_list_files,
                "verify_code": _handle_verify_code,
                "execute_code": _handle_execute_code,
                "delete_file": _handle_delete_file,
                "configure_bot": _handle_configure_bot,
            },
        )

        state.save_deliverable(agent_id, role, task, result)
        # Результат задачи НЕ дублируем в личный чат: артефакты лежат в файлах,
        # сводка — во вкладке «Итоги», ход работы — в журнале. Личный чат остаётся
        # местом для диалога и блокирующих вопросов агента, а не свалкой результатов.
        await publish({"type": "task_done", "agent_id": agent_id, "summary": result[:300]})
        return result

    return run
