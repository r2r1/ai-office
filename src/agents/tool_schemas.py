"""
JSON-схемы инструментов агента (OpenAI tool-calling формат) — вынесены из
agent_factory.py (был 901-строчный god-модуль, смешивавший декларации
инструментов, диспетчеризацию и ~19 обработчиков в одном файле, docs/
audit-dd-2026-07-06.md §1/§19 п.6). Здесь — только СТАТИЧЕСКИЕ данные (что
агент видит в описании инструмента), без единой строчки логики: безопасно
читать/менять отдельно от обработчиков (agent_factory.py), которые остаются
там же (нужны замыкания над agent_id/role/publish конкретного вызова
create() — их развязка отдельная, более рискованная задача).
"""

# Инструмент: задать вопрос пользователю
ASK_USER_TOOL = {
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
ASK_COLLEAGUE_TOOL = {
    "type": "function",
    "function": {
        "name": "ask_colleague",
        "description": "Задать КОНКРЕТНЫЙ вопрос коллеге нужной роли и СРАЗУ получить ответ "
                       "(он отвечает на основе своей работы и контекста). Используй, когда тебе "
                       "нужен вход другого специалиста: текст/оффер у marketer, данные у analyst, "
                       "дизайн и тех-проверка сайта у developer, проектное решение у architect. "
                       "Это не передача задачи — это короткая консультация по делу.",
        "parameters": {
            "type": "object",
            "properties": {
                "role": {"type": "string", "description": "Роль коллеги: marketer, developer, "
                         "analyst, architect, integrator, salesman, researcher"},
                "question": {"type": "string", "description": "Конкретный вопрос (одно-два предложения)"},
            },
            "required": ["role", "question"],
        },
    },
}

# Инструмент: поднять СОБЫТИЕ в компанию (Event Layer) — не конкретному коллеге, а CEO
RAISE_EVENT_TOOL = {
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
DELEGATE_TASK_TOOL = {
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
                "role": {"type": "string", "description": "Роль исполнителя (developer, "
                         "marketer, analyst, integrator, salesman)"},
                "title": {"type": "string", "description": "Что нужно сделать (конкретно)"},
                "done_criterion": {"type": "string", "description": "Когда задача считается выполненной"},
            },
            "required": ["role", "title"],
        },
    },
}

# Прямые send_message/read_messages у воркеров убраны: межагентка идёт через
# ask_colleague (синхронная консультация) и delegate_task (задача на доску) —
# см. tool_handlers в agent_factory.py. Свои копии этих инструментов остались
# только в chat.py (диалог пользователя с агентом), там они живые.

# Инструмент: получить доступ/учётные данные к внешней платформе
GET_CONNECTION_TOOL = {
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
READ_OFFICE_CHAT_TOOL = {
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
LIST_INTEGRATIONS_TOOL = {
    "type": "function",
    "function": {
        "name": "list_integrations",
        "description": "Список интеграций с внешними сервисами: доступные действия и статус подключения. Вызови перед use_integration.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

# Инструмент: Tool Router — опиши потребность словами, инструмент подберётся сам
USE_CAPABILITY_TOOL = {
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
USE_SKILL_TOOL = {
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
FIND_SKILLS_TOOL = {
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
USE_INTEGRATION_TOOL = {
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
WRITE_FILE_TOOL = {
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

READ_FILE_TOOL = {
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

LIST_FILES_TOOL = {
    "type": "function",
    "function": {
        "name": "list_files",
        "description": "Показывает все файлы проекта в рабочей папке (что уже написано).",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

VERIFY_CODE_TOOL = {
    "type": "function",
    "function": {
        "name": "verify_code",
        "description": "Проверяет компиляцию .py файлов. Вызывай после write_file и до предложения пушить в GitHub.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

EXECUTE_CODE_TOOL = {
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

DELETE_FILE_TOOL = {
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
CONFIGURE_BOT_TOOL = {
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
REQUEST_RESEARCH_TOOL = {
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
