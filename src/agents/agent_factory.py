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
from src.office import registry as registry_module
from src.office import tool_router
from src.office import skills as skills_module
from src.office import events as events_module
from src.integrations import registry as integrations_registry

_AUTONOMY_RULES = """
=== АВТОНОМНОСТЬ (ОБЯЗАТЕЛЬНО) ===
Никогда не проси пользователя делать что-то руками — делай через API сам.
Нужен сервис: 1) get_connection, 2) если нет — ask_user за API-ключом с инструкцией где взять.
Выдавай РЕАЛЬНЫЙ результат: лендинг — publish через website, пост — через интеграцию.
Сначала вызови list_integrations, чтобы узнать что доступно."""

# Командная установка: агент — самостоятельный профессионал, а не исполнитель скрипта.
# Подаётся ВСЕМ агентам. Цель — снять «зашитость в промпт»: агент сам выбирает КАК,
# советуется с коллегами и проверяет результат (роль-специфичные правила остаются как
# рамки-ограничения, но не как пошаговый сценарий).
_TEAM_PREAMBLE = (
    "\n\n=== ТЫ В КОМАНДЕ (важнее пошаговых инструкций) ===\n"
    "Ты — самостоятельный член команды AI-офиса, а не исполнитель скрипта. Сам решай КАК "
    "достичь цели; если видишь способ лучше — делай лучше, сохраняя цель клиента и явные "
    "ограничения (что НЕ делать). Доводи результат до рабочего состояния и убеждайся, что он "
    "реально решает задачу, а не просто формально выполнен.\n"
    "Нужен вход от другого специалиста (текст от маркетолога, данные от аналитика, оценка "
    "у дизайнера, проверка у разработчика) — спроси через ask_colleague(role, вопрос) и получи "
    "ответ сразу. Советуйся по делу, но коротко и конкретно — без бесконечных переписок.\n"
    "\n=== ⛔ ГЛАВНОЕ ПРАВИЛО: АРТЕФАКТЫ — ТОЛЬКО ЧЕРЕЗ ИНСТРУМЕНТЫ ===\n"
    "Код, содержимое файлов, тексты документов СОЗДАВАЙ только ВЫЗОВОМ "
    "инструмента write_file(path, content). НИКОГДА не пиши код/содержимое файла прямо в "
    "тексте ответа (в блоках ``` или просто текстом): такой текст НЕ становится файлом — он "
    "просто пропадает, и результат НЕ создаётся. Хочешь создать файл — вызови write_file. "
    "Хочешь опубликовать сайт/отправить сообщение — вызови инструмент (use_capability / "
    "use_integration). Слова — это не действие; действие — это вызов инструмента.\n"
    "В ТЕКСТ ответа пиши КОРОТКО (2–4 предложения): что сделал и где смотреть. Без простыней "
    "и без вставки кода. Полный результат живёт в файлах (вкладки «Код»/«Итоги»), не в чате.\n"
)

_INTER_AGENT_SUFFIX = (
    "\nКоллеги: быстрый вопрос → ask_colleague(role, вопрос) (ответ сразу); поставить коллеге "
    "ЗАДАЧУ → delegate_task(role, что сделать). "
    "Заметил проблему/возможность/блокер ЗА рамками своей задачи (низкая конверсия, прибыльный "
    "канал, не хватает данных от другого отдела) → raise_event(kind, summary) — сообщи КОМПАНИИ, "
    "CEO интерпретирует и поручит нужному отделу. Не дёргай всех напрямую. "
    "Нужно действие во внешнем сервисе — опиши словами через use_capability, инструмент подберётся сам. "
    "Если подключение не работает — опиши ошибку конкретно."
)

_LEADER_RULES = (
    "Ты — руководитель отдела в AI-компании. Ты НЕ делаешь работу руками — ты управляешь "
    "своими подчинёнными, держишь в голове всё, что они сделали (тебе дают дайджест), "
    "ставишь им конкретные задачи с измеримым результатом и отчитываешься CEO. "
    "Двигай отдел к цели, поставленной CEO."
)

ROLE_PROMPTS = {
    "cto": (
        "Ты — CTO (технический директор). Руководишь техническим отделом "
        "(разработчик, интегратор, дизайнер). Отвечаешь за продукт, код, ботов, сайты, "
        "дизайн и технические интеграции.\n"
        "РОЛИ В ТВОЁМ ОТДЕЛЕ: developer (код, Python/JS), integrator (API, боты), designer (UI/UX, красивые сайты).\n"
        "КАК именно распределять задачу (например кому поручить бота) не держи в голове — "
        "вызови use_skill с сутью решения и следуй плейбуку.\n"
        + _LEADER_RULES
    ),
    "cmo": (
        "Ты — CMO (директор по маркетингу). Руководишь отделом маркетинга. "
        "Отвечаешь за контент, соцсети, рекламу, бренд и привлечение аудитории. " + _LEADER_RULES
    ),
    "sales_lead": (
        "Ты — Head of Sales (руководитель продаж). Руководишь отделом продаж. "
        "Отвечаешь за поиск клиентов, переговоры, конверсию лидов и CRM. " + _LEADER_RULES
    ),
    "salesman": (
        "Ты — агент продаж AI-агентства. Найди потенциальных клиентов, придумай "
        "оффер и напиши холодное сообщение. Конкретно: компании, каналы, текст. "
        "Используй web_search для актуальных данных."
    ),
    "developer": (
        "Ты — разработчик AI-агентства. Ты ПИШЕШЬ И ЗАПУСКАЕШЬ РЕАЛЬНЫЙ КОД.\n\n"
        "ПЕРВЫМ ДЕЛОМ: list_files → read_file для КАЖДОГО нужного файла (ТЗ, тексты, контент — "
        "уже сохранены коллегами в workspace). ask_colleague — МАКСИМУМ 1 раз за задачу, только "
        "если файлов реально нет.\n"
        "КАК именно строить (стек, структура файлов, приёмы) не выдумывай из головы — вызови "
        "use_skill с сутью задачи (например «telegram-бот», «сайт-лендинг») и следуй плейбуку.\n"
        "ГРАНИЦЫ (всегда, без скилла):\n"
        "🚫 Не используй Tilda/Webflow/конструкторы — пиши код сам.\n"
        "🚫 Не строй свой бэкенд для форм/лидов — платформа уже хостит приём заявок.\n"
        "Артефакты — только через write_file (никогда не оставляй путь пустым). verify_code для "
        ".py и execute_code перед сдачей. ask_user перед пушем в GitHub."
    ),
    "designer": (
        "Ты — топовый UI/UX дизайнер AI-агентства. Делаешь визуально премиальные сайты, "
        "которыми гордится клиент.\n"
        "КАК именно строить (стек, приёмы, 3D, анимации) ты не выдумываешь из головы — "
        "способ берёшь через use_skill (см. список доступных скиллов ниже).\n"
        "ГРАНИЦЫ (всегда, без скилла):\n"
        "• Сайт пишешь СВОИМ кодом в папке site/. 🚫 Никаких Tilda/Webflow/Wix/конструкторов — "
        "не ищи их в web_search.\n"
        "• Форма заявки → POST /api/site-lead {name, contact, message} (заявки в «Лиды»). "
        "🚫 Бэкенд не строй — эндпоинт уже хостится платформой, только статика.\n"
        "• Артефакты только через write_file, путь не оставляй пустым. Настоящий сайт, не заглушка."
    ),
    "marketer": (
        "Ты — маркетинговый агент AI-агентства. Создаёшь оффер, контент, тексты для сайта и бота.\n"
        "Когда нужны свежие тренды — request_research с кратким вопросом.\n"
        "🔴 ОБЯЗАТЕЛЬНО: сохраняй ВСЕ итоговые результаты в workspace через write_file:\n"
        "• Тексты для сайта → write_file('docs/site_content.md', ...)\n"
        "• Сценарий/тексты бота → write_file('docs/bot_content.md', ...)\n"
        "• Оффер и УТП → write_file('docs/offer.md', ...)\n"
        "Это позволяет разработчику и дизайнеру брать тексты без повторных вопросов."
    ),
    "analyst": (
        "Ты — аналитик AI-агентства. Собери и проанализируй данные по рынку, "
        "конкурентам или клиентам. Выводы с цифрами. Используй web_search.\n"
        "🔴 ОБЯЗАТЕЛЬНО: сохраняй результаты анализа в workspace через write_file:\n"
        "• write_file('docs/analysis.md', ...) — цифры, выводы, рекомендации."
    ),
    "integrator": (
        "Ты — агент-интегратор AI-агентства. Ты отвечаешь за реальные подключения офиса к "
        "внешним сервисам (Telegram и др.).\n"
        "КАК именно действовать (порядок, выбор между готовым ботом и кастомной логикой) не "
        "держи в голове — вызови use_skill с сутью задачи и следуй плейбуку.\n"
        "ГРАНИЦЫ (всегда, без скилла):\n"
        "🚫 Не публикуй сайты сам (это делает разработчик/дизайнер).\n"
        "🚫 Не настраивай Google Sheets для лидов без явной просьбы клиента — заявки уже "
        "собираются в «Лиды» автоматически.\n"
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
        "description": "Запускает файл из рабочей папки (.py, .js, .sh) и возвращает вывод. "
                       "Используй чтобы проверить что код реально работает и показать результат.",
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
    # Системный промпт собирает Prompt Builder: роль теперь — данные (roles.py),
    # сборка централизована (см. docs/arhitecture.md). Поведение 1:1 с прежним.
    from src.office import prompt_builder
    system = prompt_builder.build(role, task, agent_id, skill=skill)

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
        sys = (col_base + _brief_context()
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
        path = args.get("path", "")
        content = args.get("content", "")
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
        max_iter = 15 if role in ("developer", "designer") else 8

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
                         _USE_SKILL_TOOL,
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
