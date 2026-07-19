"""
«Настройки»: модели/LLM-ключи, философия, конституция, автономность, доверие, режимы качества, скиллы, роли, лимиты. Перенесено из server.py (docs/technical-due-diligence-
2026-07-17.md §3.2.1, PR-5) механически — тот же код, то же поведение.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from fastapi.requests import Request
from src.office import autonomy as autonomy_module
from src.office import constitution as constitution_module
from src.office import costs as costs_module
from src.office import llm_settings as llm_settings_module
from src.office import models as models_module
from src.office import philosophy as philosophy_module
from src.office import quality_modes as quality_modes_module
from src.office import roles as roles_module
from src.office import skills as skills_module
from src.office import trust as trust_module
from src.saas import context as saas_context
from src.saas import members as members_module
from src.saas import store as saas_store
from routers.shared import current_user

router = APIRouter()


@router.get("/api/models")
async def get_models():
    """Текущая глобальная модель, индивидуальные назначения и подсказки."""
    return {
        "default": models_module.get_default(),
        "per_agent": models_module.assignments(),
        "per_role": models_module.role_assignments(),
        "roles": models_module.role_catalog(),
        "presets": models_module.PRESETS,
    }

@router.get("/api/llm-settings")
async def get_llm_settings():
    """Персональные настройки доступа к LLM (свой ключ клиента)."""
    return llm_settings_module.public()

@router.post("/api/llm-settings")
async def set_llm_settings(request: Request):
    """Сохранить свой API-ключ и base_url. Ключ шифруется на диске."""
    data = await request.json()
    llm_settings_module.set_settings(
        base_url=(data.get("base_url") or "").strip(),
        api_key=(data.get("api_key") or "").strip(),
    )
    return {"ok": True, **llm_settings_module.public()}

@router.post("/api/llm-settings/clear")
async def clear_llm_key():
    """Удалить свой ключ — вернуться на общий ключ оператора."""
    llm_settings_module.clear_key()
    return {"ok": True, **llm_settings_module.public()}

@router.get("/api/model")
async def get_model():
    return {"model": models_module.get_default()}

@router.post("/api/model")
async def set_model(request: Request):
    """Сменить глобальную модель офиса."""
    data = await request.json()
    model = (data.get("model") or "").strip()
    if not model:
        return JSONResponse({"error": "model обязателен"}, status_code=400)
    models_module.set_default(model)
    return {"ok": True, "model": model}

@router.get("/api/philosophy")
async def get_philosophy(request: Request):

    return philosophy_module.load()

@router.post("/api/philosophy")
async def post_philosophy(request: Request):

    data = await request.json()
    philosophy_module.save(data)
    return {"ok": True}

@router.get("/api/constitution")
async def get_constitution(request: Request):

    return constitution_module.payload()

@router.post("/api/constitution")
async def post_constitution(request: Request):

    data = await request.json()
    constitution_module.save(data)
    return {"ok": True}

@router.get("/api/autonomy")
async def get_autonomy(request: Request):

    return autonomy_module.payload()

@router.post("/api/autonomy")
async def post_autonomy(request: Request):

    data = await request.json()
    level = data.get("level", "")
    if level not in autonomy_module.LEVELS:
        return JSONResponse({"error": f"Уровень должен быть одним из: {autonomy_module.LEVELS}"}, status_code=400)
    autonomy_module.set_level(level)
    return {"ok": True, "level": level}

@router.post("/api/autonomy/upgrade")
async def post_autonomy_upgrade(request: Request):
    """Повысить автономию на один уровень — приём предложения офиса одним нажатием (B3)."""
    new_level = autonomy_module.upgrade()
    return {"ok": True, "level": new_level}

@router.get("/api/trust")
async def get_trust(request: Request):

    return trust_module.payload()

@router.get("/api/quality-modes")
async def get_quality_modes(request: Request):
    """Режимы качества выбора модели (🟣 Экономия → ⚫ Эксперт)."""
    return quality_modes_module.payload()

@router.post("/api/quality-modes")
async def post_quality_modes(request: Request):
    data = await request.json()
    mode = data.get("mode")
    if mode:
        if mode not in quality_modes_module.QUALITY_MODES:
            return JSONResponse({"error": "Неизвестный режим"}, status_code=400)
        quality_modes_module.set_mode(mode)
    # Эксперт-режим: точечные оверрайды по типу задачи (capability-типу модели).
    for cap, model in (data.get("expert") or {}).items():
        quality_modes_module.set_expert(cap, model)
    return {"ok": True, **quality_modes_module.payload()}

@router.get("/api/skills")
async def get_skills(request: Request):

    return {"skills": skills_module.catalog_payload()}

@router.post("/api/skills/install")
async def install_skill(request: Request):
    """Установка скилла-файла (аналог npx skills add) — ЯВНОЕ действие пользователя.
    source: markdown | url | github. Скилл = инструкция агентам; ставь из доверенных источников."""
    data = await request.json()
    src = (data.get("source") or "markdown").strip()
    res = skills_module.install(
        src,
        content=data.get("content", ""),
        url=data.get("url", ""),
        ref=data.get("ref", ""),
    )
    if not res.get("ok"):
        return JSONResponse(res, status_code=400)
    return res

@router.delete("/api/skills/{skill_id}")
async def delete_skill(skill_id: str, request: Request):

    res = skills_module.remove(skill_id)
    if not res.get("ok"):
        return JSONResponse(res, status_code=400)
    return res

@router.get("/api/roles")
async def get_roles(request: Request):

    return roles_module.payload()

@router.get("/api/limits")
async def get_limits(request: Request):

    return costs_module.limit_payload()

@router.post("/api/limits")
async def post_limits(request: Request):

    data = await request.json()
    costs_module.set_limits(
        total_usd=data.get("total_usd", 0),
        daily_usd=data.get("daily_usd", 0),
    )
    return {"ok": True, **costs_module.limit_payload()}


# ---- Multi-user доступ (портрет §12) — выдаёт/отзывает ТОЛЬКО основатель ----

@router.get("/api/members")
async def get_members(request: Request):
    """Список людей с доступом к тенанту + сам основатель первым. Видно
    любому авторизованному в тенанте (не только основателю) — прозрачность
    состава команды не секрет, только ПРАВА менять её — секрет основателя."""
    tid = saas_context.get_tenant()
    # По id ТЕКУЩЕГО тенанта, не по пользователю — участник может владеть
    # СВОИМ отдельным воркспейсом где-то ещё; нам нужен основатель именно
    # ТЕКУЩЕГО tid, не «какой-то воркспейс, к которому причастен этот человек».
    ws = saas_store.db.query_one("SELECT * FROM workspaces WHERE id = ?", (tid,))
    owner_id = ws["owner_user_id"] if ws else None
    owner = saas_store.public_user(saas_store.get_user(owner_id)) if owner_id else None
    members = []
    for r in members_module.members_of(tid):
        u = saas_store.get_user(r["user_id"])
        if u:
            members.append({**r, "user": saas_store.public_user(u)})
    return {"founder": owner, "members": members}


@router.post("/api/members/grant")
async def post_members_grant(request: Request):
    """Выдать/обновить права участнику. 403, если вызывающий не основатель —
    enforced и здесь (403 для API-ответа), и внутри members.grant (NotFounder,
    defense in depth — см. докстринг saas/members.py)."""
    me = current_user(request)
    if not me:
        return JSONResponse({"error": "Требуется авторизация"}, status_code=401)
    tid = saas_context.get_tenant()
    data = await request.json()
    target_email = (data.get("email") or "").strip().lower()
    if not target_email:
        return JSONResponse({"error": "Укажите email участника"}, status_code=400)
    target = saas_store.db.query_one("SELECT * FROM users WHERE email = ?", (target_email,))
    if not target:
        return JSONResponse({"error": "Пользователь с таким email ещё не входил в сервис"},
                            status_code=404)
    try:
        rights = members_module.grant(
            tid, target["id"], me["id"],
            visibility_domains=data.get("visibility_domains") or [],
            decide_domains=data.get("decide_domains") or [],
            can_direct_agents=bool(data.get("can_direct_agents")),
        )
    except members_module.NotFounder:
        return JSONResponse({"error": "Права выдаёт только основатель"}, status_code=403)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"ok": True, "rights": rights}


@router.post("/api/members/revoke")
async def post_members_revoke(request: Request):
    me = current_user(request)
    if not me:
        return JSONResponse({"error": "Требуется авторизация"}, status_code=401)
    tid = saas_context.get_tenant()
    data = await request.json()
    target_user_id = (data.get("user_id") or "").strip()
    try:
        ok = members_module.revoke(tid, target_user_id, me["id"])
    except members_module.NotFounder:
        return JSONResponse({"error": "Права отзывает только основатель"}, status_code=403)
    return {"ok": ok}
