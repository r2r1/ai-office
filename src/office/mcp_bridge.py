"""
MCP-мост (Layer 2, платформенные провайдеры) — "Как это может работать у
тебя?": Model Context Protocol как ПРОТОКОЛЬНАЯ граница вместо Python-импорта.

Интеграции (integrations/*.py) — провайдер способности в ТОМ ЖЕ процессе.
MCP-сервер — провайдер в ОТДЕЛЬНОМ процессе за стандартным протоколом (stdio/
JSON-RPC): своё имя+схема+description на инструмент, свой список tools,
получаемый живым запросом (list_tools), а не зашитый в код агента статически.

Область этой фазы — ТОЛЬКО платформенные серверы (см. _PLATFORM_SERVERS ниже):
AI-Office сам публикует их всем тенантам, риск ограничен так же, как у
встроенных интеграций. Тенантские/устанавливаемые клиентом MCP-серверы —
исполнение ПРОИЗВОЛЬНОГО кода от имени тенанта и требуют SANDBOX_MODE=docker
(exec_sandbox.py) как обязательное условие, а не default — это следующая
фаза, здесь её нет.

Отключение сервера — деградация, не сбой: агент просто не получает эти
инструменты (as list_tools()==[] при ошибке), работа не падает.
"""

import sys
import time
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Платформенные MCP-серверы. roles: [] = доступен всем ролям. Формат конфига
# такой же плоский, как _CATALOG в capability.py/skills.py — новый сервер
# добавляется одной записью, без правок agent_factory.py.
_PLATFORM_SERVERS: dict[str, dict] = {
    "toy": {
        "command": sys.executable,
        "args": [str(Path(__file__).parent / "mcp_toy_server.py")],
        "roles": [],
    },
}

# Каталог инструментов запрашивается живым процессом на каждый его список —
# дорого делать на каждый tool-call агента. Кэш с TTL: сервер не переоткрывает
# процесс чаще раза в CACHE_TTL секунд, но и не залипает навсегда, если сервер
# обновит свои инструменты.
_CACHE_TTL = 300.0
_tools_cache: dict[str, tuple[float, list[dict]]] = {}


def enabled_servers(role: str = "") -> dict[str, dict]:
    """Платформенные серверы, доступные роли (пусто в roles = всем)."""
    return {k: v for k, v in _PLATFORM_SERVERS.items()
            if not v.get("roles") or role in v["roles"]}


def _params(conf: dict) -> StdioServerParameters:
    return StdioServerParameters(command=conf["command"], args=conf.get("args", []),
                                  env=conf.get("env"))


async def list_tools(server_id: str, use_cache: bool = True) -> list[dict]:
    """Каталог инструментов сервера: [{name, description, inputSchema}].
    Пустой список при недоступности сервера — не исключение (деградация)."""
    conf = _PLATFORM_SERVERS.get(server_id)
    if not conf:
        return []
    if use_cache:
        cached = _tools_cache.get(server_id)
        if cached and time.monotonic() - cached[0] < _CACHE_TTL:
            return cached[1]
    try:
        async with stdio_client(_params(conf)) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                tools = [
                    {"name": t.name, "description": t.description or "",
                     "inputSchema": t.inputSchema or {"type": "object", "properties": {}}}
                    for t in result.tools
                ]
        _tools_cache[server_id] = (time.monotonic(), tools)
        return tools
    except Exception:
        return []


async def call_tool(server_id: str, name: str, arguments: dict) -> str:
    """Вызывает инструмент на MCP-сервере, возвращает текст результата.
    Любая ошибка (сервер упал/недоступен/неизвестный инструмент) — короткое
    сообщение агенту, не исключение наружу (та же деградация, что у get_connection
    при отсутствующих кредах интеграции)."""
    conf = _PLATFORM_SERVERS.get(server_id)
    if not conf:
        return f"MCP-сервер «{server_id}» не настроен."
    try:
        async with stdio_client(_params(conf)) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments)
                parts = [getattr(block, "text", "") for block in (result.content or [])]
                parts = [p for p in parts if p]
                return "\n".join(parts) if parts else "(пустой ответ MCP-сервера)"
    except Exception as e:
        return f"Ошибка вызова MCP-инструмента «{server_id}.{name}»: {e}"


def _tool_name(server_id: str, name: str) -> str:
    """Namespace-префикс — та же схема, что у клиента этой сессии
    (mcp__<сервер>__<инструмент>): исключает коллизии имён между серверами."""
    return f"mcp__{server_id}__{name}"


def _make_handler(server_id: str, name: str):
    async def _handler(args: dict) -> str:
        return await call_tool(server_id, name, args)
    return _handler


async def build(role: str) -> tuple[list[dict], dict]:
    """Схемы (формат tool_schemas.py) + async-хендлеры всех платформенных MCP-
    инструментов, доступных роли. Один сервер недоступен — остальные не страдают
    (try/except на каждый, не общий)."""
    schemas: list[dict] = []
    handlers: dict[str, Any] = {}
    for server_id in enabled_servers(role):
        try:
            tools = await list_tools(server_id)
        except Exception:
            tools = []
        for t in tools:
            full_name = _tool_name(server_id, t["name"])
            schemas.append({
                "type": "function",
                "function": {
                    "name": full_name,
                    "description": f"[MCP:{server_id}] {t['description']}",
                    "parameters": t["inputSchema"],
                },
            })
            handlers[full_name] = _make_handler(server_id, t["name"])
    return schemas, handlers


def invalidate_cache(server_id: str = "") -> None:
    """Сброс кэша каталога — для тестов и на случай ручного обновления сервера."""
    if server_id:
        _tools_cache.pop(server_id, None)
    else:
        _tools_cache.clear()
