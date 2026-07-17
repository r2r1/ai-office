"""
Админ-API — операционный обзор по ВСЕМ тенантам разом (баланс, ошибки, пауза,
прокси), намеренно ОТДЕЛЬНЫЙ от обычной пользовательской авторизации (saas/auth.py,
сессии/GitHub OAuth): это инструмент оператора платформы, не клиента. Защищён
общим bearer-токеном ADMIN_API_KEY (.env) — если он не задан, все эндпоинты
отвечают 503, чтобы админка не оказалась случайно открыта без ключа.

Фронтенд — намеренно ОТДЕЛЬНЫЙ статический файл (admin_panel/index.html), а не
часть webapp/: разворачивается на изолированном сервере/URL, не зависит от
пользовательского SPA и его деплоя.

Внутри операций, затрагивающих конкретный тенант (пауза/прокси), явно
переключаем ContextVar (saas/context.py) на его id — по тому же паттерну, что
office/llm_settings.py:provision_tenant_key и office/loop.py используют для
обращения к данным тенанта вне его собственного HTTP-запроса.
"""

import os

from fastapi import APIRouter, Header, HTTPException

from src.office import control as control_module
from src.office import costs as costs_module
from src.office import llm_settings
from src.office import trace as trace_module
from src.saas import context as saas_context
from src.saas import store as saas_store

router = APIRouter()

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "").strip()


def _require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    if not ADMIN_API_KEY:
        raise HTTPException(503, "ADMIN_API_KEY не задан в .env — админка отключена")
    if not x_admin_key or x_admin_key != ADMIN_API_KEY:
        raise HTTPException(401, "неверный или отсутствующий X-Admin-Key")


def _with_tenant(tid: str):
    """Контекст-менеджер: временно переключает ContextVar тенанта, чтобы
    вызвать per-tenant модуль (control.py/llm_settings.py/costs.py/trace.py)
    вне его собственного HTTP-запроса, и вернуть ContextVar как было."""
    class _Ctx:
        def __enter__(self):
            self.prev = saas_context.get_tenant()
            saas_context.set_tenant(tid)
            return self

        def __exit__(self, *exc):
            saas_context.set_tenant(self.prev)

    return _Ctx()


@router.get("/admin/api/tenants")
async def list_tenants(x_admin_key: str | None = Header(default=None)) -> dict:
    _require_admin(x_admin_key)
    out = []
    for ws in saas_store.all_workspaces():
        tid = ws["id"]
        with _with_tenant(tid):
            status = control_module.status()
            totals = costs_module.totals()
            proxy = llm_settings.proxy_url()
            has_own_key = llm_settings.has_own_key()
        out.append({
            "id": tid,
            "name": ws.get("name"),
            "created_at": ws.get("created_at"),
            "paused": status["paused"],
            "pause_reason": status["reason"],
            "cost_total": round(totals["cost"], 4),
            "calls_total": totals["calls"],
            "has_proxy": bool(proxy),
            "has_own_llm_key": has_own_key,
        })
    return {"tenants": out}


@router.post("/admin/api/tenant/{tid}/pause")
async def pause_tenant(tid: str, reason: str = "", x_admin_key: str | None = Header(default=None)) -> dict:
    _require_admin(x_admin_key)
    with _with_tenant(tid):
        control_module.pause(reason or "остановлено администратором")
        return control_module.status()


@router.post("/admin/api/tenant/{tid}/resume")
async def resume_tenant(tid: str, x_admin_key: str | None = Header(default=None)) -> dict:
    _require_admin(x_admin_key)
    with _with_tenant(tid):
        control_module.resume()
        return control_module.status()


@router.get("/admin/api/tenant/{tid}/costs")
async def tenant_costs(tid: str, x_admin_key: str | None = Header(default=None)) -> dict:
    _require_admin(x_admin_key)
    with _with_tenant(tid):
        return costs_module.payload()


@router.get("/admin/api/tenant/{tid}/errors")
async def tenant_errors(tid: str, n: int = 200, x_admin_key: str | None = Header(default=None)) -> dict:
    """Последние записи трейса с признаком ошибки — трейс уже пишет ВСЕ события
    тенанта (office/trace.py), здесь просто фильтруем и не заводим отдельный
    журнал ошибок с нуля."""
    _require_admin(x_admin_key)
    with _with_tenant(tid):
        entries = trace_module.tail(n)
    errors = [e for e in entries if "error" in str(e.get("kind", "")).lower() or e.get("error")]
    return {"errors": errors[-100:]}


@router.get("/admin/api/tenant/{tid}/proxy")
async def get_tenant_proxy(tid: str, x_admin_key: str | None = Header(default=None)) -> dict:
    _require_admin(x_admin_key)
    with _with_tenant(tid):
        return {"proxy_url": llm_settings.proxy_url()}


@router.post("/admin/api/tenant/{tid}/proxy")
async def set_tenant_proxy(tid: str, proxy_url: str = "", x_admin_key: str | None = Header(default=None)) -> dict:
    _require_admin(x_admin_key)
    with _with_tenant(tid):
        llm_settings.set_proxy(proxy_url)
        return {"proxy_url": llm_settings.proxy_url()}


@router.delete("/admin/api/tenant/{tid}")
async def delete_tenant(tid: str, x_admin_key: str | None = Header(default=None)) -> dict:
    """Необратимо: удаляет тенанта целиком (пользователей, все данные на диске —
    saas_store.delete_workspace). Оператор явно указывает tid, а не полагается
    на ContextVar текущей сессии — это действие НАД чужим тенантом, не своим."""
    _require_admin(x_admin_key)
    ok = saas_store.delete_workspace(tid)
    if not ok:
        raise HTTPException(404, "тенант не найден")
    return {"ok": True, "deleted": tid}


@router.post("/admin/api/proxy/broadcast")
async def broadcast_proxy(proxy_url: str = "", x_admin_key: str | None = Header(default=None)) -> dict:
    """Ставит ОДИН прокси всем тенантам разом — быстрый путь, когда прокси
    общий (не per-tenant), но выставлять его нужно каждому тенанту отдельно
    (per-tenant override главнее общего LLM_PROXY_URL, core/llm.py:_resolve_proxy)."""
    _require_admin(x_admin_key)
    updated = []
    for ws in saas_store.all_workspaces():
        tid = ws["id"]
        with _with_tenant(tid):
            llm_settings.set_proxy(proxy_url)
        updated.append(tid)
    return {"updated": updated, "proxy_url": proxy_url}
