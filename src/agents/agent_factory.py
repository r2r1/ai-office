"""
Фабрика агентов — создаёт нового агента по роли и задаче.
Работает через единое ядро llm.py.

Любой агент может запросить ресёрчера через инструмент request_research.
"""

from typing import Callable, Awaitable

from src.core import llm
from src.agents import tool_schemas as _ts
from src.agents import file_tool_handlers
from src.agents import comms_tool_handlers
from src.agents import integration_tool_handlers
from src.agents import portfolio_tool_handlers
from src.office import mcp_bridge
from src.office import models as models_module
from src.office import office_channel
from src.office import self_awareness
from src.office import state
from src.office import workspace as workspace_module

# Иерархия доступа (BOS §6.2): кто видит портфель целиком — единый источник
# правды в org.is_portfolio_role (используется и здесь для гейта инструментов,
# и в prompt_builder для портфельного слота промпта).

# Тексты ролей и командные политики переехали в файлы (Prompt Builder — единая
# сборка): роли — src/office/builtin_roles/<role>.md (читает roles.py), политики
# (автономность, «артефакты только через инструменты», межагентность, правила
# лидера) — src/office/policies/*.md (читает prompt_builder.policy). Инструменты
# агента вынесены в отдельные модули (этот файл был 901-строчным god-модулем,
# docs/audit-dd-2026-07-06.md §1/§19 п.6):
#   tool_schemas.py             — JSON-схемы 19 инструментов (чистые данные)
#   file_tool_handlers.py       — write_file/read_file/list_files/verify_code/
#                                  execute_code/delete_file/configure_bot
#   comms_tool_handlers.py      — request_research/ask_user/ask_colleague/
#                                  raise_event/delegate_task/read_office_chat/
#                                  get_connection (+ try_extract_connection)
#   integration_tool_handlers.py — list_integrations/use_integration/
#                                  use_capability/use_skill/find_skills
# Каждый проход декомпозиции делался ПОСЛЕ того, как tests/test_agent_tool_
# handlers.py фиксировал текущее поведение — иначе рефакторинг замыканий над
# agent_id/role/publish рисковал тихо сломать wiring без единого сигнала.

# Backward-compat: старые тесты/код могли ссылаться на приватное имя здесь.
_try_extract_connection = comms_tool_handlers.try_extract_connection


def create(role: str, task: str, agent_id: str, publish: Callable[[dict], Awaitable[None]],
           skill: str = "", model: str = "", title: str = ""):
    """Возвращает async-функцию, запускающую агента. `model` — решение Execution
    Policy для конкретной задачи (пусто → обычный путь models.for_agent).
    `title` — короткая подпись задачи для карточки в «Артефактах»/«Готовых
    результатах»; `task` часто приходит УЖЕ дополненным контекстом (бриф/ТЗ/
    память — task_with_context), и если не передать короткий title отдельно,
    в save_deliverable уходит эта громадная строка целиком (реальный баг:
    вкладки «Артефакты» и «Готовые результаты» рендерили простыню на
    полэкрана вместо короткой подписи)."""
    # Системный промпт собирает Prompt Builder (роли/политики — .md-файлы,
    # сборка централизована, см. docs/bos-architecture.md §7). Полный промпт
    # логируется в prompts.jsonl тенанта — отладка мышления зрячая.
    from src.office import prompt_builder
    system = prompt_builder.build(role, task, agent_id, skill=skill)
    prompt_builder.log_prompt(agent_id, role, system, task)

    async def _publish_and_log(event: dict) -> None:
        """Обёртка над publish: speech-события агентов дублируются в общий канал."""
        await publish(event)
        if event.get("type") == "speech" and event.get("agent_id") == agent_id:
            office_channel.post(agent_id, role, event.get("text", ""))

    async def run() -> str:
        run_model = model or models_module.for_agent(agent_id)
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

        # execute_code исполняет процесс без изоляции от ФС хоста (security-долг,
        # docs/audit-dd-2026-07.md §17) — выключен оператором по умолчанию. Инструмент
        # прячем из каталога ЦЕЛИКОМ (не только блокируем вызов): модель не тратит
        # токены/итерации на действие, которое ей всё равно откажут (workspace.
        # execute_code вернул бы _DISABLED_MSG, но лучше вообще не предлагать выбор).
        _file_handlers = file_tool_handlers.build(agent_id, role, publish, _publish_and_log)
        _code_exec_tools = [_ts.EXECUTE_CODE_TOOL] if workspace_module.code_execution_allowed() else []
        if not workspace_module.code_execution_allowed():
            _file_handlers.pop("execute_code", None)

        _comms_handlers = comms_tool_handlers.build(agent_id, role, publish, _publish_and_log)
        _integration_handlers = integration_tool_handlers.build(agent_id, role, publish, _publish_and_log)

        def _touch_liveness() -> None:
            # Каждый ответ API/инструмента = «агент жив»: продлеваем watchdog, чтобы
            # длинная ЗАКОННАЯ работа (десяток правок сайта) не считалась зависанием
            # и не порождала второго исполнителя при живом первом.
            try:
                from src.office import execution
                execution.touch(agent_id)
            except Exception:
                pass

        # Лидеры отделов (и CEO) спрашивают клиента НАПРЯМУЮ (ask_user) — они и
        # есть решающий узел иерархии. Рядовые сотрудники и штабные роли
        # (researcher/strategist/architect/hr) эскалируют вопрос СВОЕМУ
        # руководителю (ask_leader) — тот либо отвечает сам, либо передаёт
        # дальше (см. comms_tool_handlers._handle_ask_leader). Не даём одному
        # агенту оба инструмента — иначе модель иногда просто выбирает более
        # короткий путь (ask_user) в обход иерархии.
        from src.office import org as org_module
        _ask_tool = _ts.ASK_USER_TOOL if role in org_module.LEAD_ROLES or role == "orchestrator" else _ts.ASK_LEADER_TOOL

        _extra_tools = [_ts.REQUEST_RESEARCH_TOOL, _ask_tool, _ts.ASK_COLLEAGUE_TOOL,
                        _ts.RAISE_EVENT_TOOL, _ts.DELEGATE_TASK_TOOL, _ts.CREATE_RECURRING_PROCESS_TOOL,
                        _ts.GET_CONNECTION_TOOL,
                        _ts.READ_OFFICE_CHAT_TOOL,
                        _ts.LIST_INTEGRATIONS_TOOL, _ts.USE_CAPABILITY_TOOL, _ts.USE_INTEGRATION_TOOL,
                        _ts.USE_SKILL_TOOL, _ts.FIND_SKILLS_TOOL, _ts.RECORD_METRIC_TOOL,
                        _ts.DISCOVER_RESOURCE_TOOL, _ts.REGISTER_EXTERNAL_API_TOOL,
                        _ts.WRITE_FILE_TOOL, _ts.READ_FILE_TOOL, _ts.LIST_FILES_TOOL, _ts.VERIFY_CODE_TOOL,
                        *_code_exec_tools, _ts.DELETE_FILE_TOOL, _ts.CONFIGURE_BOT_TOOL]
        # Иерархия доступа (BOS §6.2): кросс-проектное чтение портфеля — лидерам
        # отделов, CEO и надпроектным сервисным ролям. Воркер заперт в своём проекте.
        _portfolio_enabled = org_module.is_portfolio_role(role)
        _portfolio_tools = ([_ts.LIST_PROJECTS_TOOL, _ts.LIST_PROJECT_FILES_TOOL, _ts.READ_PROJECT_FILE_TOOL]
                            if _portfolio_enabled else [])
        _portfolio_handlers = (portfolio_tool_handlers.build(agent_id, role, publish, _publish_and_log)
                               if _portfolio_enabled else {})

        # Platform Self-Knowledge (BOS §6.1), узкая версия: агент видит СВОЮ роль/
        # скилл/список СВОИХ инструментов, а не исходный код платформы — доступно
        # всем ролям, риска нет (это отражение собственной конфигурации, не чужого кода).
        _tool_names = [t["function"]["name"] for t in _extra_tools] + \
            [t["function"]["name"] for t in _portfolio_tools] + ["describe_self"]

        async def _handle_describe_self(args: dict) -> str:
            return self_awareness.describe(role, _tool_names, skill=skill)

        # MCP-мост (Layer 2, платформенные серверы) — те же слоты extra_tools/
        # tool_handlers, что и у остальных источников инструментов, только схема
        # приходит живым list_tools() вместо статичного tool_schemas.py. Сервер
        # недоступен/не настроен → build() отдаёт пустые списки, агент просто не
        # видит эти инструменты (деградация, не сбой создания агента).
        _mcp_schemas, _mcp_handlers = await mcp_bridge.build(role)

        result = await llm.run_agent(
            system=system,
            user=task,
            model=run_model,
            max_tokens=max_tok,
            max_iterations=max_iter,
            max_searches=4,
            use_search=True,
            publish=_publish_and_log,
            agent_id=agent_id,
            on_activity=_touch_liveness,
            extra_tools=[*_extra_tools, *_portfolio_tools, _ts.DESCRIBE_SELF_TOOL, *_mcp_schemas],
            tool_handlers={
                **_comms_handlers,
                **_integration_handlers,
                **_file_handlers,
                **_portfolio_handlers,
                **_mcp_handlers,
                "describe_self": _handle_describe_self,
            },
        )

        state.save_deliverable(agent_id, role, title or task, result)
        # Результат задачи НЕ дублируем в личный чат: артефакты лежат в файлах,
        # сводка — во вкладке «Итоги», ход работы — в журнале. Личный чат остаётся
        # местом для диалога и блокирующих вопросов агента, а не свалкой результатов.
        await publish({"type": "task_done", "agent_id": agent_id, "summary": result[:300]})
        return result

    return run
