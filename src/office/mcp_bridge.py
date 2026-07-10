"""
MCP-мост (Layer 2) — "Как это может работать у тебя?": Model Context Protocol
как ПРОТОКОЛЬНАЯ граница вместо Python-импорта.

Интеграции (integrations/*.py) — провайдер способности в ТОМ ЖЕ процессе.
MCP-сервер — провайдер в ОТДЕЛЬНОМ процессе за стандартным протоколом (stdio/
JSON-RPC): своё имя+схема+description на инструмент, свой список tools,
получаемый живым запросом (list_tools), а не зашитый в код агента статически.

Два источника серверов, РАЗНЫЙ уровень доверия:

  _PLATFORM_SERVERS — платформенные, AI-Office сам публикует их всем тенантам
  (риск ограничен так же, как у встроенных интеграций) — запускаются НАПРЯМУЮ.

  mcp_tenant_servers.py — тенантские: клиент подключает СВОЙ MCP-сервер, это
  исполнение ПРОИЗВОЛЬНОГО кода от его имени. Запускаются ТОЛЬКО через Docker
  (_docker_wrap) — обёртка теми же флагами изоляции, что exec_sandbox._run_docker
  (read-only ФС, cap-drop, лимиты ресурсов), НЕТ volume-mount workspace тенанта
  (эксфильтрировать нечего — сервер физически не видит файлы других тенантов
  или самой платформы). Сеть — НЕ выключена по умолчанию, в отличие от
  execute_code: разница модели угроз в том, что execute_code реально читает/
  пишет workspace (сеть = канал эксфильтрации ЭТИХ файлов), а тенантский MCP-
  сервер файлов не видит вообще — сеть ему часто НУЖНА по делу (обратиться к
  собственному API клиента), поэтому tenant явно включает allow_network при
  регистрации, а не получает её тайком. mcp_tenant_servers.add() отказывает
  СРАЗУ, если Docker не готов (см. её докстринг) — mcp_bridge здесь только
  повторно проверяет на использовании (sandbox мог отключиться после регистрации).

Отключение сервера (платформенного или тенантского) — деградация, не сбой:
агент просто не получает эти инструменты (list_tools()==[] при ошибке),
работа не падает.
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


def _docker_wrap(conf: dict) -> dict:
    """Оборачивает тенантский server-конфиг {command, args, env, allow_network}
    в `docker run` — те же флаги изоляции, что exec_sandbox._run_docker (read-
    only ФС, cap-drop, no-new-privileges, лимиты CPU/памяти/pids), но БЕЗ
    volume-mount (тенантскому MCP-серверу не нужен доступ к workspace — он
    провайдер способности, не исполнитель файлов задачи) и с СЕТЬЮ по
    умолчанию НЕ выключенной жёстко — controlled через allow_network (см.
    докстринг модуля: другая модель угроз, чем execute_code). env передаётся
    внутрь контейнера через `-e KEY=VALUE`, не через env самого `docker`-процесса
    (StdioServerParameters.env адресован процессу, который она запускает —
    здесь это `docker`, а секреты нужны ВНУТРИ контейнера)."""
    from src.office import exec_sandbox as sbx

    docker_args = [
        "run", "--rm", "-i",
        "--read-only",
        "--tmpfs", "/tmp:rw,size=64m,noexec",
        f"--memory={sbx._MEMORY_LIMIT}",
        f"--cpus={sbx._CPU_LIMIT}",
        f"--pids-limit={sbx._PIDS_LIMIT}",
        "--security-opt=no-new-privileges",
        "--cap-drop=ALL",
    ]
    if not conf.get("allow_network"):
        docker_args += ["--network", "none"]
    # ⚠️ -e KEY=VALUE попадает в argv контейнера — виден через `docker inspect`/
    # `ps` на хосте тому, у кого есть доступ к хосту (тот же класс ограничения,
    # что у большинства docker-обвязок без --env-file). Известный компромисс
    # этой фазы, не решённая проблема — секрет тенанта живёт максимум на время
    # жизни короткого контейнера, не постоянно в файле на диске.
    for k, v in (conf.get("env") or {}).items():
        docker_args += ["-e", f"{k}={v}"]
    docker_args.append(sbx.IMAGE_NAME)
    docker_args.append(conf["command"])
    docker_args += list(conf.get("args") or [])
    return {"command": "docker", "args": docker_args, "env": None}


_TENANT_PREFIX = "tenant_"


def _tenant_sandbox_ready() -> bool:
    from src.office import exec_sandbox as sbx
    return sbx.mode() == "docker" and sbx.docker_available()


def _tenant_server_ids() -> list[str]:
    """id тенантских серверов ТЕКУЩЕГО тенанта (ctx.tenant_id — ContextVar,
    правильно изолирован между параллельными задачами разных тенантов), с
    префиксом, чтобы не столкнуться с id платформенных. Пусто, если песочница
    не готова — деградация на использовании, не только на регистрации (sandbox
    мог быть выключен ПОСЛЕ того, как сервер зарегистрировали)."""
    if not _tenant_sandbox_ready():
        return []
    from src.office import mcp_tenant_servers
    return [f"{_TENANT_PREFIX}{s['id']}" for s in mcp_tenant_servers.list_all()]


def _resolve_conf(server_id: str) -> dict | None:
    """Платформенный конфиг — как есть; тенантский — читается свежо (env
    расшифровывается тут же) и оборачивается в docker. Не кэшируется как
    конфиг (кэшируется только СПИСОК инструментов, см. _tools_cache) — иначе
    расшифрованные креды тенанта осели бы в процесс-глобальной структуре
    дольше, чем нужно."""
    conf = _PLATFORM_SERVERS.get(server_id)
    if conf:
        return conf
    if server_id.startswith(_TENANT_PREFIX) and _tenant_sandbox_ready():
        from src.office import mcp_tenant_servers
        raw_id = server_id[len(_TENANT_PREFIX):]
        srv = mcp_tenant_servers.get(raw_id)
        if srv:
            return _docker_wrap(srv)
    return None


async def list_tools(server_id: str, use_cache: bool = True) -> list[dict]:
    """Каталог инструментов сервера: [{name, description, inputSchema}].
    Пустой список при недоступности сервера — не исключение (деградация)."""
    conf = _resolve_conf(server_id)
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
    conf = _resolve_conf(server_id)
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
    """Схемы (формат tool_schemas.py) + async-хендлеры всех MCP-инструментов
    (платформенных + тенантских, если песочница готова), доступных роли. Один
    сервер недоступен — остальные не страдают (try/except на каждый, не общий).
    Тенантские серверы не фильтруются по роли (пока нет UI-поля под это) —
    видны всем ролям тенанта, как get_connection/use_capability."""
    schemas: list[dict] = []
    handlers: dict[str, Any] = {}
    for server_id in [*enabled_servers(role), *_tenant_server_ids()]:
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
