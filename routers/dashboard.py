"""
«Обзор»: сводки офиса (дайджест, понимание бизнеса, инфраструктура, здоровье, возможности), мир (World Model), метрики, бизнес-дашборд, расход. Перенесено из server.py (docs/technical-due-diligence-
2026-07-17.md §3.2.1, PR-5) механически — тот же код, то же поведение.
"""

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi.requests import Request
from src.office import bus
from src.office import costs as costs_module
from src.office import health as health_module
from src.office import initiatives as initiatives_module
from src.agents import orchestrator
from routers.shared import with_worker_id as _with_worker_id

router = APIRouter()


@router.get("/api/digest")
async def get_digest():
    """Morning Digest — что офис сделал с последнего визита. Обновляет метку визита."""
    from src.office import digest as digest_module
    return digest_module.get_and_mark_seen()

@router.get("/api/digest/last")
async def get_digest_last():
    """Повторно открыть ПОСЛЕДНИЙ уже показанный дайджест (round2 audit, U3) —
    в отличие от /api/digest, НЕ продвигает last_seen и ничего не потребляет."""
    from src.office import digest as digest_module
    return digest_module.peek_last()

@router.get("/api/understanding")
async def get_understanding():
    """Индикатор «Понимание компании»: score 0–100, что есть и чего не хватает."""
    from src.office import understanding as understanding_module
    return understanding_module.payload()

@router.get("/api/digital-infrastructure")
async def get_digital_infrastructure():
    """Уровень 2 Instant Learning: единый список источников данных о компании —
    подключённые интеграции платформы + сигналы, увиденные на сайте клиента
    (CRM/аналитика/соцсети), к которым платформа пока не подключена напрямую."""
    from src.office import digital_infrastructure
    return digital_infrastructure.payload()

@router.get("/api/costs")
async def get_costs():
    """Расход токенов и стоимость по агентам и суммарно (ROI-панель)."""
    payload = costs_module.payload()
    return {**payload, "agents": _with_worker_id(payload.get("agents", []))}

@router.get("/api/apinet/balance")
async def apinet_balance():
    """Реальный баланс/расход аккаунта apinet (точные цифры из их API).
    Работает только если заданы APINET_ACCESS_TOKEN/USER_ID."""
    from src.saas import apinet
    if not apinet.is_configured():
        return {"configured": False}
    return {"configured": True, **apinet.balance()}

@router.get("/api/office/status")
async def office_status():
    """Статус офис-цикла (работает / на паузе)."""
    from src.office import control as control_module
    return control_module.status()

@router.post("/api/office/pause")
async def office_pause():
    """Поставить офис на паузу (агенты доделают текущие задачи, новые не начнут)."""
    from src.office import control as control_module, bus as bus_module
    control_module.pause("Пауза по запросу пользователя")
    await bus_module.publish({"type": "system", "text": "⏸ Офис поставлен на паузу пользователем"})
    return {"ok": True}

@router.post("/api/office/resume")
async def office_resume():
    """Возобновить работу офиса."""
    from src.office import control as control_module, bus as bus_module
    control_module.resume()
    await bus_module.publish({"type": "system", "text": "▶ Офис возобновил работу"})
    return {"ok": True}

@router.get("/api/world")
async def get_world():
    """World Model: единый срез мира компании (Business State + Objectives + DNA)."""
    from src.office import world as world_module
    return world_module.snapshot()

@router.get("/api/metrics")
async def get_metrics():
    """Measurement (Phase 3): текущие показания метрик (факт|оценка) + история."""
    from src.office import metrics as metrics_module
    cur = metrics_module.current()
    return {"current": cur,
            "series": {r["metric_id"]: metrics_module.series(r["metric_id"]) for r in cur}}

@router.get("/api/gap")
async def get_gap():
    """Gap Analysis (Phase 4): разрывы между желаемым (Objective) и метрикой."""
    from src.office import gap as gap_module
    return {"gaps": gap_module.compute()}

@router.get("/api/dashboard")
async def get_dashboard():
    """Бизнес-дашборд (вкладка "Бизнес"): системные карточки (пересчитываются
    каждый раз из живых источников) + кастомные графики, добавленные по запросу
    клиента, в сохранённом порядке (перестановка — POST /api/dashboard/reorder)."""
    from src.office import dashboard as dashboard_module
    widgets = dashboard_module.all_widgets()
    for w in widgets:
        if w.get("kind") == "chart":
            w["series"] = dashboard_module.resolve_series(w)
    return {"widgets": widgets}

@router.post("/api/dashboard/request")
async def post_dashboard_request(request: Request):
    """Ручная кастомизация дашборда словами ("построй график выручки по месяцам
    за 12 месяцев"). CEO выбирает метрику из реально измеримых или честно
    отказывает — отказ с suggest_integration заводит инициативу (та же логика,
    что "не выдумываем KPI без данных", см. dashboard.py)."""
    from src.agents import orchestrator
    from src.office import initiatives as initiatives_module, dashboard as dashboard_module
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Опиши, что добавить на дашборд")
    # Тот же класс бага, что закрыт в routers/comms.py: пауза (control.py) блокирует
    # только автономный цикл (loop.py), а не прямые LLM-вызовы из HTTP-роутов.
    from src.office import control as control_module
    if control_module.is_paused():
        raise HTTPException(status_code=409, detail="Офис на паузе — возобновите работу, чтобы изменить дашборд")
    result = await orchestrator.interpret_dashboard_request(text)
    if not result.get("ok"):
        iid = ""
        if result.get("suggest_integration"):
            # tasks (BOS §4 гибкость сервиса): не просто текст-заглушка, а
            # готовый план — скрипт + повторяющийся процесс + запись метрики
            # (см. dashboard_widget.md) — принятие инициативы сразу заводит
            # проект с этими задачами (существующий accept_initiative).
            iid = initiatives_module.add(
                result["suggest_integration"], result.get("reason", ""),
                "На дашборде появится реальная метрика вместо отказа",
                tasks=result.get("tasks") or [], source="user", needs_research=False)
        return {"ok": False, "reason": result.get("reason", ""), "initiative_id": iid}
    widget = dashboard_module.add_custom({
        "metric_id": result["metric_id"], "chart_type": result["chart_type"],
        "group_by": result["group_by"], "range_days": result["range_days"],
        "title": result["title"],
    })
    widget["series"] = dashboard_module.resolve_series(widget)
    return {"ok": True, "widget": widget}

@router.post("/api/dashboard/layout")
async def post_dashboard_layout(request: Request):
    """Свободное перетаскивание/ресайз виджета "как иконки на рабочем столе" —
    позиция и размер, любые оба (не только вертикальный порядок списком)."""
    from src.office import dashboard as dashboard_module
    body = await request.json()
    wid = (body.get("id") or "").strip()
    if not wid:
        raise HTTPException(status_code=400, detail="Нужен id виджета")
    dashboard_module.set_layout(wid, body.get("x", 0), body.get("y", 0),
                                body.get("w", 240), body.get("h", 140))
    return {"ok": True}

@router.post("/api/dashboard/remove")
async def post_dashboard_remove(request: Request):
    from src.office import dashboard as dashboard_module
    body = await request.json()
    return {"ok": dashboard_module.remove_custom(body.get("id", ""))}

@router.get("/api/health")
async def get_health(request: Request):

    return health_module.payload()

@router.get("/api/capabilities")
async def get_capabilities(request: Request):
    """Реестр способностей компании (BOS §5): что умеем / чего не хватает под план /
    что можно подключить. НЕ режимы качества моделей — те на /api/quality-modes."""
    from src.office import capability
    return capability.registry()
