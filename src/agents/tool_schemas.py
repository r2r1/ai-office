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

# Инструмент: эскалация вопроса СВОЕМУ руководителю (не пользователю напрямую).
# Рядовые сотрудники не беспокоят клиента лично — если ответа нет в файлах
# проекта, вопрос уходит руководителю (лидеру отдела, а штабным ролям — CEO),
# и уже он решает: ответить самому или передать клиенту (см. comms_tool_handlers).
ASK_LEADER_TOOL = {
    "type": "function",
    "function": {
        "name": "ask_leader",
        "description": "Задать вопрос СВОЕМУ руководителю, когда ответа нет в файлах и контексте "
                       "этого проекта (например, нужны данные/решение за пределами твоей рабочей "
                       "области). НЕ для вопросов пользователю напрямую — руководитель либо ответит "
                       "сам, либо (если нужен именно клиент) передаст вопрос дальше сам.",
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "Конкретный вопрос (одно-два предложения)"},
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

# Инструмент: записать числовую метрику бизнеса (появится на бизнес-дашборде)
RECORD_METRIC_TOOL = {
    "type": "function",
    "function": {
        "name": "record_metric",
        "description": "Записывает числовое значение метрики бизнеса — единственный способ добавить "
                       "НОВУЮ метрику на бизнес-дашборд (например курс валюты, остатки склада — что "
                       "угодно, для чего ты написал скрипт/процесс сбора данных). Вызывай каждый раз, "
                       "когда получил свежее значение (например из периодического процесса). "
                       "⚠️ Если скрипт вернул ошибку (сеть недоступна, источник не ответил и т.п.) — "
                       "НЕ ВЫЗЫВАЙ record_metric с придуманным правдоподобным числом. Значение "
                       "source='оценка' — это для честно посчитанной оценки (например по формуле), "
                       "а не для угаданного числа взамен реальных данных. Если реальных данных нет — "
                       "просто не вызывай инструмент в этом цикле и опиши ошибку в тексте задачи "
                       "(напиши разработчику: сети у скрипта в песочнице нет вовсе — см. builtin_roles/developer.md).",
        "parameters": {
            "type": "object",
            "properties": {
                "metric_id": {"type": "string", "description": "Короткий id латиницей, snake_case (например usd_rub_rate)"},
                "value": {"type": "number", "description": "Числовое значение"},
                "label": {"type": "string", "description": "Человекочитаемое название (например 'Курс USD/RUB')"},
                "unit": {"type": "string", "description": "Единица (например 'руб', '$', 'шт')"},
                "source": {"type": "string", "enum": ["факт", "оценка"], "description": "факт — измерено напрямую; оценка — вычислено/приблизительно"},
            },
            "required": ["metric_id", "value"],
        },
    },
}

# Инструмент: discovery по URL — «дай системе ссылку, пусть сама поймёт, что это»
DISCOVER_RESOURCE_TOOL = {
    "type": "function",
    "function": {
        "name": "discover_resource",
        "description": "По ГОЛОЙ ссылке (без заранее написанной интеграции под неё) определяет, что "
                       "это за ресурс — GitHub-репозиторий, OData-сервис (1С и т.п.), REST API со "
                       "спецификацией OpenAPI, обычный сайт, или недоступен — и подсказывает, каким "
                       "путём с ним работать (существующая интеграция / нужны креды / register_external_api). "
                       "Вызывай ПЕРВЫМ, когда клиент даёт ссылку на внешнюю систему и просишь понять, что там.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Ссылка на внешний ресурс (http/https)"},
            },
            "required": ["url"],
        },
    },
}

# Инструмент: подключить обобщённый REST API через MCP (для kind=rest_api_openapi
# из discover_resource) — требует готовую Docker-песочницу (SANDBOX_MODE=docker),
# иначе отказывает с понятным сообщением, не тихо деградирует.
REGISTER_EXTERNAL_API_TOOL = {
    "type": "function",
    "function": {
        "name": "register_external_api",
        "description": "Подключает произвольный REST API со спецификацией OpenAPI/Swagger как набор "
                       "инструментов — используй ПОСЛЕ discover_resource, когда kind=\"rest_api_openapi\". "
                       "Поднимает обобщённый MCP-мост в изолированном Docker-контейнере (не пишет новый "
                       "код), который сам прочитает спецификацию сервиса. Требует включённой Docker-"
                       "песочницы на платформе — если её нет, вернёт понятную ошибку, не сделает вид, "
                       "что подключил.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Базовый URL API (тот же, что был в discover_resource)"},
                "label": {"type": "string", "description": "Короткое человекочитаемое имя сервиса"},
                "auth_header": {"type": "string", "description": "Имя заголовка авторизации, если нужен (напр. Authorization)"},
                "auth_value": {"type": "string", "description": "Значение заголовка авторизации (получи у пользователя через ask_user, не выдумывай)"},
            },
            "required": ["url", "label"],
        },
    },
}

# Инструмент: подключить ГОТОВЫЙ MCP-сервер стороннего сервиса (npx-пакет и т.п.)
# как есть — в отличие от register_external_api (который всегда поднимает НАШ
# обобщённый REST-мост поверх голого API), здесь запускается РОДНОЙ MCP-сервер
# сервиса со своими типизированными инструментами. Тот же тенантский реестр и
# то же требование Docker-песочницы (mcp_tenant_servers.add), просто без
# хардкода command на mcp_generic_rest_server.py.
REGISTER_MCP_SERVER_TOOL = {
    "type": "function",
    "function": {
        "name": "register_mcp_server",
        "description": "Подключает ГОТОВЫЙ MCP-сервер стороннего сервиса (например, у сервиса есть "
                       "свой npx-пакет с MCP-сервером — Postiz, Figma и т.п.) — в отличие от "
                       "register_external_api, здесь запускается РОДНОЙ сервер сервиса как есть, "
                       "со своими инструментами, а не наш обобщённый REST-мост поверх голого API. "
                       "Используй, когда клиент/задача называют конкретный сервис с ГОТОВЫМ MCP-сервером "
                       "(не когда есть только голый REST API без MCP — тогда discover_resource + "
                       "register_external_api). Требует включённой Docker-песочницы на платформе — если "
                       "её нет, вернёт понятную ошибку, не сделает вид, что подключил. Команда выполняется "
                       "ИЗОЛИРОВАННО в контейнере — доверяй её только известным пакетам сервиса, не "
                       "выдуманным именам.",
        "parameters": {
            "type": "object",
            "properties": {
                "label": {"type": "string", "description": "Короткое человекочитаемое имя сервиса (напр. «Postiz»)"},
                "command": {"type": "string", "description": "Исполняемая команда (напр. npx, node, python3) — "
                                   "берётся из официальной документации MCP-сервера сервиса, не выдумывается"},
                "args": {"type": "array", "items": {"type": "string"},
                         "description": "Аргументы команды (напр. [\"-y\", \"@gitroom/postiz-mcp\"])"},
                "env": {"type": "object", "additionalProperties": {"type": "string"},
                        "description": "Переменные окружения для сервера (API-ключи и т.п.) — значения "
                                       "получи у пользователя через ask_user, не выдумывай"},
                "allow_network": {"type": "boolean", "description": "Разрешить сетевой доступ контейнеру "
                                   "(нужен почти всегда — сервер стучится к API сервиса). По умолчанию false "
                                   "(контейнер без сети) — включай явно, когда сервису реально нужна сеть."},
            },
            "required": ["label", "command"],
        },
    },
}

# Инструмент: найти готовый рецепт подключения известного open-source MCP-сервиса
# (office/mcp_connectors.py, каталог office/builtin_mcp_connectors/*.md) — ДО того,
# как звать register_mcp_server вручную. Решает конкретный найденный кейс: модель
# без каталога сама придумывала неверный npm-пакет для Postiz вместо реального
# stdio↔SSE моста mcp-remote. Каталог — по файлу на сервис, растёт без правки кода.
FIND_MCP_CONNECTORS_TOOL = {
    "type": "function",
    "function": {
        "name": "find_mcp_connectors",
        "description": "Ищет по каталогу ГОТОВЫХ рецептов подключения известных open-source MCP-"
                       "сервисов (Postiz и т.п. — растёт со временем). Возвращает список кандидатов "
                       "с id и тем, какие значения (needs) нужно собрать у пользователя. Вызывай "
                       "ПЕРЕД register_mcp_server, когда сервис по описанию похож на что-то известное "
                       "(кроспостинг, дизайн-инструмент и т.п.) — если каталог знает точный рецепт, не "
                       "изобретай command/args сам, возьми через connect_mcp_connector.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Что ищешь, своими словами (можно пусто — покажет весь каталог)"},
            },
            "required": [],
        },
    },
}

# Инструмент: подключить сервис из каталога по готовому рецепту (id) + собранным
# значениям needs — резолвит command/args сам, агенту не нужно ничего собирать руками.
CONNECT_MCP_CONNECTOR_TOOL = {
    "type": "function",
    "function": {
        "name": "connect_mcp_connector",
        "description": "Подключает известный сервис из каталога (см. find_mcp_connectors) по его id — "
                       "command/args уже прописаны в рецепте, нужно только передать values со значениями "
                       "needs (URL/ключи), которые ты получил у пользователя через ask_user. Не выдумывай "
                       "значения needs сам. Требует готовую Docker-песочницу на платформе, как и "
                       "register_mcp_server/register_external_api.",
        "parameters": {
            "type": "object",
            "properties": {
                "connector_id": {"type": "string", "description": "id рецепта из find_mcp_connectors (напр. «postiz»)"},
                "values": {"type": "object", "additionalProperties": {"type": "string"},
                           "description": "Значения needs рецепта, ключ→значение (напр. {\"POSTIZ_URL\": \"http://host:4007\", \"POSTIZ_API_KEY\": \"...\"})"},
            },
            "required": ["connector_id", "values"],
        },
    },
}

# Инструмент: поднять ПОСТОЯННЫЙ сервис тенанта (self-hosted Postiz и т.п.) —
# office/tenant_apps.py. Другая модель угроз, чем register_mcp_server (там
# короткоживущий MCP-сервер на время задачи, здесь — стек 24/7 с реальным
# расходом CPU/RAM хоста и публично проксируемым HTTP). ⚠️ ВСЕГДА только
# после явного "да" пользователя через ask_user — та же дисциплина, что у
# git push (agent_factory.py): реальная инфраструктура, не просто токены LLM.
HOST_APP_TOOL = {
    "type": "function",
    "function": {
        "name": "host_app",
        "description": "Поднимает ПОСТОЯННЫЙ (24/7) docker-compose стек стороннего open-source "
                       "сервиса на платформе (например self-hosted Postiz) — в отличие от "
                       "register_mcp_server/register_external_api (короткоживущий MCP-сервер на "
                       "время задачи), это реальная инфраструктура: расход CPU/RAM хоста непрерывно, "
                       "публично доступный адрес /apps/{tenant}/{app_id}/. ⚠️ ВЫЗЫВАЙ ТОЛЬКО ПОСЛЕ "
                       "ЯВНОГО «да» ПОЛЬЗОВАТЕЛЯ через ask_user — никогда не поднимай инфраструктуру "
                       "по своей инициативе, даже если задача явно про это просит. Лимит — несколько "
                       "приложений на тенанта; требует включённой Docker-песочницы на платформе.",
        "parameters": {
            "type": "object",
            "properties": {
                "label": {"type": "string", "description": "Короткое человекочитаемое имя (напр. «Postiz»)"},
                "compose_yaml": {"type": "string", "description": "Полное содержимое docker-compose.yml сервиса "
                                   "(из официального репозитория сервиса, не выдумывай) — ОБЯЗАН объявлять маппинг "
                                   "портов host_port:container_port у главного сервиса"},
                "host_port": {"type": "integer", "description": "Порт хоста, на который compose пробрасывает "
                                   "главный сервис (тот же, что в маппинге ports compose_yaml)"},
                "container_port": {"type": "integer", "description": "Внутренний порт контейнера, на котором слушает сервис"},
                "env": {"type": "object", "additionalProperties": {"type": "string"},
                        "description": "Переменные окружения стека (секреты и т.п.) — значения получи через ask_user"},
            },
            "required": ["label", "compose_yaml", "host_port", "container_port"],
        },
    },
}

# Инструмент: список постоянных приложений тенанта.
LIST_HOSTED_APPS_TOOL = {
    "type": "function",
    "function": {
        "name": "list_hosted_apps",
        "description": "Показывает постоянные приложения тенанта, поднятые через host_app — id, "
                       "статус, порт. Проверь ПЕРЕД host_app, не поднято ли уже похожее (не дублируй).",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

# Инструмент: остановить/удалить постоянное приложение тенанта.
STOP_HOSTED_APP_TOOL = {
    "type": "function",
    "function": {
        "name": "stop_hosted_app",
        "description": "Останавливает постоянное приложение тенанта (host_app). remove=true — полностью "
                       "удаляет стек и данные (docker compose down -v), не просто ставит на паузу.",
        "parameters": {
            "type": "object",
            "properties": {
                "app_id": {"type": "string", "description": "id приложения (см. list_hosted_apps)"},
                "remove": {"type": "boolean", "description": "true — удалить стек и данные насовсем, false (по умолчанию) — только остановить"},
            },
            "required": ["app_id"],
        },
    },
}

# Инструмент: завести повторяющийся процесс (BOS §5 — Process, не Task с концом)
CREATE_RECURRING_PROCESS_TOOL = {
    "type": "function",
    "function": {
        "name": "create_recurring_process",
        "description": "Заводит ПОВТОРЯЮЩИЙСЯ процесс — задача будет ставиться заново каждый цикл "
                       "офиса, как только предыдущая закрыта (например периодический сбор внешних "
                       "данных и запись через record_metric). Используй, когда клиент/задача просит "
                       "что-то ОБНОВЛЯТЬ регулярно, а не сделать один раз.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Короткое название процесса"},
                "role": {"type": "string", "description": "Роль исполнителя (developer, integrator, marketer, analyst, ...)"},
                "instruction": {"type": "string", "description": "Что делать КАЖДЫЙ раз (конкретно, включая какой metric_id записывать через record_metric, если применимо)"},
            },
            "required": ["title", "role", "instruction"],
        },
    },
}

# Инструмент: записать ДОЛГОВРЕМЕННОЕ знание о бизнесе клиента (Company World Model).
# До его появления knowledge.remember() был мёртвым путём записи: слой знаний
# существовал, но ни один агент физически не мог его пополнить — «офис постоянно
# узнаёт компанию» не работало в самом основании (спека §17.6).
REMEMBER_FACT_TOOL = {
    "type": "function",
    "function": {
        "name": "remember_fact",
        "description": "Записывает ФАКТ О БИЗНЕСЕ КЛИЕНТА в долговременную память офиса — "
                       "коллеги увидят его в контексте будущих задач. Записывай то, что "
                       "узнал и что пригодится другим: особенности рынка, конкурентов, "
                       "предпочтения аудитории, ограничения ниши. НЕ записывай: что ты "
                       "сделал (это журнал результатов, он ведётся сам), содержимое файлов, "
                       "пересказ задачи. Одно утверждение — один вызов. Честно указывай "
                       "source: откуда знание — от этого зависит, насколько офис будет "
                       "ему доверять; выдуманный source='measured' у гипотезы испортит "
                       "решения всей компании.",
        "parameters": {
            "type": "object",
            "properties": {
                "fact": {"type": "string", "description": "Одно короткое утверждение о бизнесе (до 280 символов)"},
                "source": {"type": "string",
                           "enum": ["measured", "outcome", "scanned", "researched", "owner_said", "inferred"],
                           "description": "Происхождение: measured — измерил сам (скрипт/данные); "
                                          "outcome — подтверждено исходом сделанной работы; scanned — из "
                                          "реальных данных интеграции/скана; researched — из веб-ресёрча; "
                                          "owner_said — клиент сказал (не проверено); inferred — твой вывод/гипотеза"},
            },
            "required": ["fact", "source"],
        },
    },
}

# Инструмент: заметка прогресса ВНУТРИ текущей задачи (переживает переназначение)
NOTE_PROGRESS_TOOL = {
    "type": "function",
    "function": {
        "name": "note_progress",
        "description": "Записывает короткую заметку «что уже сделано / чего жду» по ТЕКУЩЕЙ задаче — "
                       "она сохранится, даже если задачу заберёт другой агент или ту же задачу дадут "
                       "тебе заново после паузы. Используй для МНОГОШАГОВЫХ задач (например скилл с "
                       "циклом «спроси коллегу → жди ответа → запиши файл») — иначе повторное взятие "
                       "той же задачи начнёт этот внутренний цикл с нуля, как будто прогресса не было.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Одно предложение: что уже сделано и чего именно ждёшь"},
            },
            "required": ["text"],
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

# Platform Self-Knowledge (BOS §6.1) — узкая версия: агент видит СВОЮ роль,
# скилл и список СВОИХ инструментов (см. office/self_awareness.py), а не
# исходный код платформы (auth.py, crypto.py и т.д. не раскрываются).
DESCRIBE_SELF_TOOL = {
    "type": "function",
    "function": {
        "name": "describe_self",
        "description": ("Показывает твою собственную конфигурацию: роль, активный скилл, "
                         "список доступных тебе инструментов. НЕ показывает код платформы — "
                         "только твою текущую настройку."),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

# Иерархия доступа (BOS §6.1): лидеры/CEO видят бизнес НАСКВОЗЬ — читают файлы
# любого проекта тенанта, не только своего. Read-only; выдаются только лидерским/
# сервисным ролям (см. agent_factory). Рядовой воркер этих инструментов не видит.
LIST_PROJECTS_TOOL = {
    "type": "function",
    "function": {
        "name": "list_projects",
        "description": ("Показывает ВСЕ проекты компании (id, заголовок, статус, папка) — "
                         "обзор портфеля для решений уровня бизнеса, а не одного проекта."),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

LIST_PROJECT_FILES_TOOL = {
    "type": "function",
    "function": {
        "name": "list_project_files",
        "description": "Показывает дерево файлов конкретного проекта компании (не только твоего текущего).",
        "parameters": {
            "type": "object",
            "properties": {"project_dir": {"type": "string", "description": "Папка проекта из list_projects (поле workspace_dir)"}},
            "required": ["project_dir"],
        },
    },
}

READ_PROJECT_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "read_project_file",
        "description": "Читает файл конкретного проекта компании (read-only, для обзора чужой работы).",
        "parameters": {
            "type": "object",
            "properties": {
                "project_dir": {"type": "string", "description": "Папка проекта из list_projects (поле workspace_dir)"},
                "path": {"type": "string", "description": "Путь файла внутри этого проекта"},
            },
            "required": ["project_dir", "path"],
        },
    },
}

ANALYZE_IMAGE_TOOL = {
    "type": "function",
    "function": {
        "name": "analyze_image",
        "description": "Смотрит на изображение по URL и описывает его словами (vision-модель) — например, "
                       "экспортированный figma.export_images макет: палитра, композиция, стиль, элементы. "
                       "Не для site/* скриншотов твоей же работы — только для внешних референсов/макетов.",
        "parameters": {
            "type": "object",
            "properties": {
                "image_url": {"type": "string", "description": "Прямая ссылка на изображение (например, из figma.export_images)"},
                "question": {"type": "string", "description": "Что именно нужно узнать (например «опиши палитру и стиль»)"},
            },
            "required": ["image_url"],
        },
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
