"""
«Результаты»: лиды, сайты, реестр результатов, персонализация вкладок (ui-prefs). Перенесено из server.py (docs/technical-due-diligence-
2026-07-17.md §3.2.1, PR-5) механически — тот же код, то же поведение.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from fastapi.requests import Request
from src.office import domains as domains_module
from src.integrations import registry as integrations_registry
from src.office import leads as leads_module
from src.office import results as results_module
from src.saas import context as saas_context
from src.office import sites as sites_module
from src.office import ui_prefs as ui_prefs_module

router = APIRouter()


@router.post("/api/leads/{lead_id}/followup")
async def send_lead_followup(lead_id: str, request: Request):
    """Отправить follow-up лиду напрямую в Telegram-ЛС (личный аккаунт) и записать
    в историю лида. Body: {text}. Target берётся из contact лида — если это не
    @username/телефон, интеграция сама вернёт понятную причину отказа."""
    data = await request.json()
    text = (data.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "text обязателен"}, status_code=400)
    lead = leads_module.get(lead_id)
    if not lead:
        return JSONResponse({"error": "лид не найден"}, status_code=404)
    integ = integrations_registry.get("telegram_personal")
    if not integrations_registry.is_connected(integ):
        return JSONResponse({"error": "нет активной сессии личного Telegram — подключите в «Доступы»"},
                            status_code=400)
    creds = integrations_registry.credentials_for(integ)
    result = await integ.actions["send_dm"].handler(creds, {"target": lead["contact"], "text": text})
    sent = "отправлено" in result.lower()
    leads_module.add_note(lead_id, f"Telegram: {text[:80]}" if sent else f"⚠ Не отправлено: {result[:150]}",
                          by="owner")
    return {"ok": sent, "result": result}

@router.get("/api/sites")
async def get_sites():
    """Список опубликованных лендингов (с числом заявок)."""
    tid = saas_context.get_tenant()
    domains_by_slug: dict[str, list[str]] = {}
    for d in domains_module.for_tenant(tid):
        domains_by_slug.setdefault(d["slug"], []).append(d["domain"])
    out = []
    for s in sites_module.all_sites():
        out.append({**s, "leads": len(leads_module.for_site(s["slug"])),
                    "url": f"/site/{tid}/{s['slug']}",
                    "domains": domains_by_slug.get(s["slug"], [])})
    return {"sites": out}

@router.post("/api/sites/{slug}/domain")
async def add_site_domain(slug: str, request: Request):
    """Привязать кастомный домен к опубликованному сайту (docs/product-capability-gaps.md
    п.5). Клиент сам направляет DNS домена (A/CNAME) на платформу — это вне нашего
    контроля; здесь только серверное сопоставление Host → тенант/сайт."""
    tid = saas_context.get_tenant()
    if sites_module.get(slug) is None:
        return JSONResponse({"error": "сайт с таким адресом не найден"}, status_code=404)
    body = await request.json()
    domain = (body.get("domain") or "").strip()
    result = domains_module.register(domain, tid, slug)
    if "error" in result:
        return JSONResponse(result, status_code=400)
    return {"domain": result, "instructions": (
        f"Направьте DNS домена {result['domain']} на этот сервер (A-запись на IP сервера "
        f"или CNAME, в зависимости от вашего DNS-провайдера) — платформа не регистрирует "
        f"домены и не управляет DNS сама.")}

@router.delete("/api/sites/{slug}/domain/{domain}")
async def remove_site_domain(slug: str, domain: str):
    tid = saas_context.get_tenant()
    ok = domains_module.unregister(domain, tid)
    return {"ok": ok}

@router.get("/api/leads")
async def get_leads():
    """Все собранные лиды (мини-CRM: статус + история)."""
    return {"leads": leads_module.all_leads(), "statuses": leads_module.STATUSES,
            "labels": leads_module.STATUS_LABELS}

@router.post("/api/leads/{lead_id}/status")
async def set_lead_status(lead_id: str, request: Request):
    """Сменить статус лида (мини-CRM). Body: {status, note?}.
    ⚠️ Путь ОБЯЗАН быть /api/leads/... (множественное число), не /api/lead/... —
    последний уже занят публичным приёмом заявок POST /api/lead/{tenant}/{slug}
    (без авторизации, для форм лендингов). Оба двухсегментные, FastAPI матчит по
    порядку регистрации — /api/lead/{lead_id}/status ловился ТЕМ роутом (tenant=
    lead_id, slug="status") и не долистывал до этого хендлера (нашли по 404 в реальном тесте)."""
    data = await request.json()
    status = (data.get("status") or "").strip()
    note = data.get("note") or ""
    lead = leads_module.set_status(lead_id, status, note)
    if not lead:
        return JSONResponse({"error": "лид не найден или статус некорректен"}, status_code=404)
    return {"ok": True, "lead": lead}

@router.post("/api/leads/{lead_id}/note")
async def add_lead_note(lead_id: str, request: Request):
    """Добавить заметку к лиду. Body: {text}."""
    data = await request.json()
    text = (data.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "text обязателен"}, status_code=400)
    lead = leads_module.add_note(lead_id, text, by="owner")
    if not lead:
        return JSONResponse({"error": "лид не найден"}, status_code=404)
    return {"ok": True, "lead": lead}

@router.get("/api/results")
async def get_results():
    """Реестр типов результата работы команды (лиды/сайты и в будущем другие) —
    метаданные вкладок «Результаты» (id/label/count), см. results.py."""
    return results_module.snapshot()

@router.get("/api/ui-prefs/{section}")
async def get_ui_prefs(section: str):
    """Персональные предпочтения владельца по видимости/порядку под-вкладок раздела."""
    return ui_prefs_module.get_section(section)

@router.post("/api/ui-prefs/{section}")
async def set_ui_prefs(section: str, request: Request):
    """Body: {order?: string[], hidden?: string[]}."""
    data = await request.json()
    return ui_prefs_module.set_section(section, data.get("order"), data.get("hidden"))
