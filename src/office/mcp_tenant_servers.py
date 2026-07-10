"""
Тенантские MCP-серверы — клиент подключает СВОЙ MCP-сервер как «руки» своего
офиса (аналог skill_store.py: там клиент устанавливает СВОЙ текст-плейбук,
здесь — свой ИСПОЛНЯЕМЫЙ код). Это принципиально другой уровень риска, чем
skill_store (текст) или mcp_bridge._PLATFORM_SERVERS (код, но который пишет
и распространяет сама платформа): тенант указывает произвольную команду,
которая выполнится с сетевым/файловым доступом, если её не изолировать.

Инвариант — регистрация СРАЗУ отказывает, если песочница не готова
(SANDBOX_MODE=docker + реально доступный Docker), а не тихо принимает сервер
и деградирует при первом использовании. Тот же принцип, что exec_sandbox.
SandboxUnavailable: громкая ошибка в момент решения, не молчаливый провал
позже, когда владелец уже думает, что сервер работает.

Хранилище: data/tenants/<tid>/mcp_tenant_servers.json. env — учётные данные,
которые может потребовать сервер тенанта (например, токен его внутреннего
API) — шифруются at-rest тем же Fernet-ключом, что connections.py.
"""

import time
import uuid

from src.office import exec_sandbox
from src.saas import context as ctx
from src.saas import crypto

_FILE = "mcp_tenant_servers.json"


def _all() -> list[dict]:
    return ctx.read_json(_FILE, [])


def _save(items: list[dict]) -> None:
    ctx.write_json(_FILE, items)


def _require_sandbox_ready() -> None:
    """Тот же принцип, что exec_sandbox._require_docker_if_needed — только
    проверяется РАНЬШЕ, на регистрации сервера, а не на каждом его вызове."""
    if exec_sandbox.mode() != "docker":
        raise exec_sandbox.SandboxUnavailable(
            "Тенантские MCP-серверы требуют SANDBOX_MODE=docker (исполнение "
            "произвольного кода от имени тенанта без изоляции недопустимо). "
            "Сейчас песочница выключена — подключить сервер нельзя."
        )
    if not exec_sandbox.docker_available():
        raise exec_sandbox.SandboxUnavailable(
            "SANDBOX_MODE=docker, но Docker не отвечает — подключить тенантский "
            "MCP-сервер нельзя, пока песочница физически не готова."
        )


def add(label: str, command: str, args: list[str] | None = None,
        env: dict[str, str] | None = None, allow_network: bool = False) -> dict:
    """Регистрирует тенантский MCP-сервер. Бросает SandboxUnavailable, если
    песочница не готова — намеренно ДО сохранения, не после."""
    _require_sandbox_ready()
    items = _all()
    item = {
        "id": uuid.uuid4().hex[:8],
        "label": (label or "").strip()[:100] or command,
        "command": (command or "").strip(),
        "args": [str(a) for a in (args or [])],
        "env": {k: crypto.encrypt(v) for k, v in (env or {}).items()},
        "allow_network": bool(allow_network),
        "created_ts": time.time(),
    }
    items.append(item)
    _save(items)
    return _public(item)


def _public(item: dict) -> dict:
    """Для UI — без значений env (не масками, а вообще без них: тенант сам их
    вводил, показывать нечего смысла нет, только ключи)."""
    return {"id": item["id"], "label": item["label"], "command": item["command"],
            "args": item["args"], "env_keys": list(item.get("env", {}).keys()),
            "allow_network": item.get("allow_network", False),
            "created_ts": item.get("created_ts", 0)}


def list_all() -> list[dict]:
    return [_public(i) for i in _all()]


def get(server_id: str) -> dict | None:
    """С РАСШИФРОВАННЫМ env — только для внутреннего использования (mcp_bridge),
    не для API/UI."""
    for i in _all():
        if i["id"] == server_id:
            return {**i, "env": {k: crypto.decrypt(v) for k, v in i.get("env", {}).items()}}
    return None


def list_for_use() -> list[dict]:
    """Все тенантские серверы с расшифрованным env — для mcp_bridge.build()."""
    return [{**i, "env": {k: crypto.decrypt(v) for k, v in i.get("env", {}).items()}}
            for i in _all()]


def remove(server_id: str) -> bool:
    items = _all()
    new = [i for i in items if i["id"] != server_id]
    _save(new)
    return len(new) < len(items)


def reset() -> None:
    ctx.delete_file(_FILE)
