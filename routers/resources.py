"""
«Ресурсы»: доступы (connections), постоянные приложения (tenant_apps), MCP-серверы
тенанта, каталог интеграций + вход в личный Telegram. Перенесено из server.py
(docs/technical-due-diligence-2026-07-17.md §3.2.1, PR-5) механически — тот же
код, то же поведение.
"""

from fastapi import APIRouter
from fastapi.requests import Request
from fastapi.responses import JSONResponse

from src.office import bus, connections
from src.integrations import registry as integrations_registry
from src.saas import context as saas_context

router = APIRouter()


@router.get("/api/connections")
async def get_connections():
    return {"connections": connections.list_all()}


@router.post("/api/connections")
async def save_connection(request: Request):
    data = await request.json()
    if not (data.get("name") or "").strip():
        return JSONResponse({"error": "название обязательно"}, status_code=400)
    item = connections.save(data)
    return {"ok": True, "connection": item}


@router.delete("/api/connections/{cid}")
async def delete_connection(cid: str):
    ok = connections.delete(cid)
    return {"ok": ok}


@router.get("/api/apps")
async def get_hosted_apps():
    """Постоянные приложения тенанта (office/tenant_apps.py) — вкладка «Приложения»."""
    from src.office import tenant_apps
    return {"apps": tenant_apps.list_all()}


@router.get("/api/apps/{app_id}")
async def get_hosted_app_detail(app_id: str):
    """Детали приложения — включая РАСШИФРОВАННЫЕ env (владелец их сам и вводил,
    показать ему обратно — не утечка, тот же принцип, что connections.py) и
    docker-compose.yml для просмотра, что реально поднято."""
    from src.office import tenant_apps
    item = tenant_apps.get(app_id)
    if item is None:
        return JSONResponse({"error": "не найдено"}, status_code=404)
    return {**item, "env_values": tenant_apps.env_values(app_id), "compose_yaml": tenant_apps.compose_yaml(app_id)}


@router.get("/api/apps/{app_id}/logs")
async def get_hosted_app_logs(app_id: str, tail: int = 100):
    from src.office import tenant_apps
    if tenant_apps.get(app_id) is None:
        return JSONResponse({"error": "не найдено"}, status_code=404)
    return {"logs": tenant_apps.logs(app_id, tail=tail)}


@router.post("/api/apps/{app_id}/pause")
async def pause_hosted_app(app_id: str):
    from src.office import tenant_apps
    ok = tenant_apps.stop(app_id)
    return {"ok": ok, "app": tenant_apps.get(app_id)}


@router.post("/api/apps/{app_id}/resume")
async def resume_hosted_app(app_id: str):
    from src.office import tenant_apps
    ok = tenant_apps.start(app_id)
    return {"ok": ok, "app": tenant_apps.get(app_id)}


@router.delete("/api/apps/{app_id}")
async def delete_hosted_app(app_id: str):
    from src.office import tenant_apps
    ok = tenant_apps.remove(app_id)
    return {"ok": ok}


@router.get("/api/mcp-servers")
async def get_mcp_servers():
    """Тенантские MCP-серверы (office/mcp_tenant_servers.py) — подключает их
    агент (register_external_api/discover_resource), владелец здесь только
    просматривает и может отключить, симметрично /api/apps."""
    from src.office import mcp_tenant_servers
    return {"servers": mcp_tenant_servers.list_all()}


@router.get("/api/mcp-servers/{server_id}")
async def get_mcp_server_detail(server_id: str):
    from src.office import mcp_tenant_servers
    servers = mcp_tenant_servers.list_all()
    item = next((s for s in servers if s["id"] == server_id), None)
    if item is None:
        return JSONResponse({"error": "не найдено"}, status_code=404)
    return {**item, "env_values": mcp_tenant_servers.env_values(server_id)}


@router.delete("/api/mcp-servers/{server_id}")
async def delete_mcp_server(server_id: str):
    from src.office import mcp_tenant_servers
    ok = mcp_tenant_servers.remove(server_id)
    return {"ok": ok}


@router.get("/api/integrations")
async def get_integrations():
    """Каталог поддерживаемых интеграций со статусом подключения."""
    return {"integrations": integrations_registry.catalog_payload()}


@router.post("/api/integrations/{name}/test")
async def test_integration(name: str):
    """Проверяет подключение: запускает безопасное действие без обязательных параметров."""
    integ = integrations_registry.get(name)
    if integ is None:
        return JSONResponse({"error": "интеграция не найдена"}, status_code=404)
    if not integrations_registry.is_connected(integ):
        return JSONResponse({"error": "нет учётных данных — добавьте подключение"}, status_code=400)
    # Берём действие-пинг: первое без обязательных параметров
    ping = next((a for a in integ.actions.values() if not a.required), None)
    if ping is None:
        return JSONResponse({"error": "у интеграции нет проверочного действия"}, status_code=400)
    creds = integrations_registry.credentials_for(integ)
    try:
        result = await ping.handler(creds, {})
        await bus.publish({"type": "integration_used", "agent_id": "user",
                           "integration": integ.name, "action": ping.name,
                           "text": f"⚙️ Проверка {integ.title}: {result[:120]}"})
        return {"ok": True, "result": result}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:200]}, status_code=200)


@router.get("/api/integrations/telegram_personal/config")
async def telegram_personal_config():
    """Заданы ли ключи ПРИЛОЖЕНИЯ оператором (.env) — если да, форма входа не
    просит пользователя искать api_id/api_hash на my.telegram.org самому."""
    from src.office import telegram_login
    return {"has_default_creds": telegram_login.has_default_creds()}


@router.post("/api/integrations/telegram_personal/login/start")
async def telegram_personal_login_start(request: Request):
    """Шаг 1 входа в личный Telegram: запросить код на телефон. Body: {phone,
    api_id?, api_hash?} — последние два нужны, только если оператор не задал
    TELEGRAM_API_ID/TELEGRAM_API_HASH в .env (см. office/telegram_login.py)."""
    from src.office import telegram_login
    data = await request.json()
    phone = (data.get("phone") or "").strip()
    if not phone:
        return JSONResponse({"error": "нужен phone"}, status_code=400)
    api_id = 0
    if data.get("api_id"):
        try:
            api_id = int(data["api_id"])
        except (TypeError, ValueError):
            return JSONResponse({"error": "api_id должен быть числом"}, status_code=400)
    api_hash = (data.get("api_hash") or "").strip()
    if not telegram_login.has_default_creds() and (not api_id or not api_hash):
        return JSONResponse({"error": "нужны api_id и api_hash (оператор не задал их в .env)"},
                            status_code=400)
    tid = saas_context.get_tenant()
    result = await telegram_login.start(tid, phone, api_id, api_hash)
    return result


@router.post("/api/integrations/telegram_personal/login/confirm")
async def telegram_personal_login_confirm(request: Request):
    """Шаг 2: подтвердить код (+ 2FA-пароль при need_password). Body: {code, password?}."""
    from src.office import telegram_login
    data = await request.json()
    tid = saas_context.get_tenant()
    result = await telegram_login.confirm(tid, data.get("code", ""), data.get("password", ""))
    return result


@router.post("/api/integrations/telegram_personal/login/cancel")
async def telegram_personal_login_cancel():
    from src.office import telegram_login
    telegram_login.cancel(saas_context.get_tenant())
    return {"ok": True}
