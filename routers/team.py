"""
«Команда»: агенты, оргструктура, онбординг/бриф, история/логи/трейс/наблюдаемость, вехи, управление агентами. Перенесено из server.py (docs/technical-due-diligence-
2026-07-17.md §3.2.1, PR-5) механически — тот же код, то же поведение.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from fastapi.requests import Request
from fastapi.responses import StreamingResponse
from src.office import brief
from src.office import costs as costs_module
from src.office import demo
from src.office import initiatives as initiatives_module
from src.integrations import registry as integrations_registry
from src.office import memory
from routers.shared import DEMO_MODE
from src.office import milestones
from src.office import models as models_module
from src.office import loop as office_loop
from src.office import org
from src.office import progress
from src.office import registry
from src.saas import context as saas_context
from src.saas import db as saas_db
from src.saas import store as saas_store
from src.office import state
import time
from routers.shared import client_ip as _client_ip
from routers.shared import rate_limited as _rate_limited
from routers.shared import with_worker_id as _with_worker_id
from routers.shared import current_user

router = APIRouter()


@router.get("/api/workspace")
async def get_workspace(request: Request):
    """Данные текущего рабочего пространства (тенанта)."""
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "auth required"}, status_code=401)
    ws = saas_store.workspace_for_user(user["id"])
    if not ws:
        return JSONResponse({"error": "workspace not found"}, status_code=404)
    return {"id": ws["id"], "name": ws["name"], "plan": ws["plan"], "created_at": ws["created_at"]}

@router.post("/api/workspace/name")
async def rename_workspace(request: Request):
    """Переименовать рабочее пространство."""
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "auth required"}, status_code=401)
    data = await request.json()
    name = (data.get("name") or "").strip()
    if not name:
        return JSONResponse({"error": "name обязателен"}, status_code=400)
    from src.saas import db as saas_db
    saas_db.execute("UPDATE workspaces SET name=? WHERE owner_user_id=?", (name, user["id"]))
    ws = saas_store.workspace_for_user(user["id"])
    return {"ok": True, "workspace": {"id": ws["id"], "name": ws["name"], "plan": ws["plan"]}}

@router.get("/api/agents")
async def get_agents():
    return _with_worker_id([
        {
            "agent_id": a.agent_id,
            "role": a.role,
            "desk": a.desk,
            "status": a.status,
            "last_message": a.last_message,
            "task": a.task,
            "project_id": a.project_id,
        }
        for a in registry.all_agents()
    ])

@router.get("/api/brief/status")
async def brief_status():
    """Фронт проверяет: нужен ли онбординг, или офис уже работает."""
    return {"ready": brief.is_ready(), "demo": DEMO_MODE, "brief": brief.get()}

@router.post("/api/onboarding/scan")
async def onboarding_scan(request: Request):
    """Instant Learning: клиент даёт URL сайта → офис изучает его за секунды,
    БЕЗ единого вопроса и без LLM (company_scan.py). Вау-эффект первых секунд
    онбординга — «мы уже кое-что знаем о вас».

    Публичный эндпоинт (см. _PUBLIC_API) — доступен ДО регистрации/логина,
    иначе моат «AI уже понимает бизнес» не проявляется до формы. Именно
    поэтому здесь отдельный rate-limit по IP: без сессии/тенанта как ключа
    анонимный эндпоинт, делающий исходящий HTTP GET по любому URL, — готовый
    вектор для использования сервера как открытого прокси/сканера."""
    if _rate_limited("scan", _client_ip(request), 12):
        return JSONResponse({"error": "Слишком много запросов, попробуйте через минуту"}, status_code=429)
    data = await request.json()
    url = (data.get("url") or "").strip()
    if not url:
        return JSONResponse({"error": "пустой url"}, status_code=400)
    from src.office import company_scan
    result = await company_scan.scan(url)
    return result

@router.get("/api/onboarding/result")
async def get_onboarding_result():
    """Первое впечатление клиента (BOS §5) — аналитика + точки роста +
    инициативы, сгенерированные один раз сразу после стратегии (см.
    office/loop.py, office/onboarding_result.py). ready=False, пока BOOTSTRAP
    ещё не дошёл до этого шага — фронт показывает "офис изучает..."."""
    from src.office import onboarding_result as onboarding_result_module, initiatives as initiatives_module
    from src.agents import architect as architect_module
    d = onboarding_result_module.get()
    if not d:
        return {"ready": False, "analysis": [], "growth_points": [], "initiatives": [], "blocking": False}
    ini_ids = set(d.get("initiative_ids") or [])
    inis = [i for i in initiatives_module.pending() if i["id"] in ini_ids]
    confirmed = d.get("status") == "confirmed"
    # blocking=True — ТОЧНО то же условие, что держит office/loop.py перед
    # architect.run_async (портрет §23): не «есть неподтверждённый дашборд
    # вообще» (это правда для КАЖДОГО тенанта до первого клика, включая уже
    # прошедших BOOTSTRAP до появления этого гейта), а «офис РЕАЛЬНО стоит и
    # ждёт этого клика прямо сейчас». Одна точка правды, не дублирующая логика
    # на фронте — старые тенанты с уже спроектированным ТЗ сюда не попадают.
    blocking = onboarding_result_module.has_content(d) and not confirmed and not architect_module.load()
    return {"ready": True, "analysis": d.get("analysis", []),
            "growth_points": d.get("growth_points", []), "initiatives": inis,
            "confirmed": confirmed, "blocking": blocking}

@router.post("/api/onboarding/result/confirm")
async def confirm_onboarding_result(request: Request):
    """Владелец посмотрел первый дашборд (портрет §23) — разблокирует
    architect/milestones/plan в loop.py, которые до этого ждут этого вызова
    (см. onboarding_result.is_confirmed())."""
    from src.office import onboarding_result as onboarding_result_module
    data = await request.json()
    d = onboarding_result_module.confirm(note=(data.get("note") or ""))
    return {"ok": True, "confirmed": d.get("status") == "confirmed"}

@router.get("/api/onboarding/suggested-integrations")
async def get_suggested_integrations():
    """Интеграции, подобранные под текст брифа — момент пиковой мотивации
    сразу после результата онбординга (см. integrations/registry.suggested_for),
    не спрятаны в «Компания → Доступы»."""
    from src.integrations import registry as integrations_registry
    b = brief.get()
    text = " ".join(str(b.get(k, "")) for k in ("summary", "goal", "niche", "audience"))
    stage_key = (b.get("business_stage") or {}).get("key", "")
    return {"integrations": integrations_registry.suggested_for(text, business_stage=stage_key)}

@router.get("/api/history")
async def get_history():
    """Лента событий из прошлых запусков — фронт показывает её при загрузке."""
    return {"events": state.history(), "results": {
        a.agent_id: state.result_for(a.agent_id) for a in registry.all_agents()
    }}

@router.get("/api/logs")
async def get_logs():
    """Полный текстовый лог работы офиса — можно скачать и прислать на анализ."""
    from datetime import datetime
    import time as _time

    lines = []
    lines.append("=" * 60)
    lines.append("AI OFFICE — ЛОГ РАБОТЫ")
    lines.append(f"Сформирован: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
    lines.append("=" * 60)

    # Бриф
    b = brief.get()
    if b:
        lines.append("\n## БРИФ КЛИЕНТА")
        for k, v in b.items():
            lines.append(f"  {k}: {v}")

    # Модели
    lines.append("\n## МОДЕЛИ")
    lines.append(f"  по умолчанию: {models_module.get_default()}")
    for aid, m in models_module.assignments().items():
        lines.append(f"  {aid}: {m}")

    # Расход токенов и стоимость
    ct = costs_module.totals()
    lines.append("\n## РАСХОД (токены / стоимость)")
    lines.append(f"  Итого: ${ct['cost']:.4f} | токенов вход {ct['in_tokens']} / выход {ct['out_tokens']} | вызовов {ct['calls']}")
    for a in costs_module.by_agent():
        lines.append(f"  {a['agent_id']} ({a.get('model','')}): ${a['cost']:.4f} | "
                     f"вход {a['in_tokens']} / выход {a['out_tokens']} | вызовов {a['calls']}")

    # Команда — сгруппирована по проектам (реальный кейс: живой UI TeamView.tsx
    # группирует с 2026-07-06, этот текстовый экспорт — нет; клиент, скачавший
    # лог прогона с двумя параллельными проектами, видел плоский список без
    # деления и решил, что разделения по проектам не существует вовсе).
    from src.office import projects as projects_module
    lines.append("\n## КОМАНДА")
    proj_titles = {p["id"]: p["title"] for p in projects_module.all_projects()}
    by_project: dict[str, list] = {}
    for a in registry.all_agents():
        by_project.setdefault(a.project_id or "", []).append(a)
    # Штаб (без project_id) — первой секцией, дальше проекты в порядке появления.
    for pid in sorted(by_project.keys(), key=lambda p: (p != "", p)):
        label = "Штаб (без привязки к проекту)" if not pid else f"Проект «{proj_titles.get(pid, pid)}»"
        lines.append(f"  --- {label} ---")
        for a in by_project[pid]:
            lines.append(f"  [{a.status}] {a.agent_id} ({a.role}) — {a.task[:80]}")
            if a.last_message:
                lines.append(f"      последнее: {a.last_message[:120]}")

    # Этапы
    lines.append("\n## ЭТАПЫ ПУТИ")
    for s in milestones.all_stages():
        lines.append(f"  [{s['status']}] {s['title']} (id={s['id']}, записей: {len(s['items'])})")
        if s["summary"]:
            lines.append(f"      сводка: {s['summary'][:200]}")

    # Лента событий
    lines.append("\n## ЛЕНТА СОБЫТИЙ")
    for e in state.history():
        etype = e.get("type", "")
        who = e.get("agent_id", "")
        txt = e.get("text") or e.get("summary") or ""
        lines.append(f"  [{etype}] {who}: {txt[:200]}")

    # Детальный системный трейс — с временем, инструментами, длительностями, моделями,
    # токенами, публикациями, вердиктами критика. Это «всё, что произошло внутри».
    from src.office import trace as _trace
    trace_text = _trace.as_text(2000)
    if trace_text:
        lines.append("\n## ДЕТАЛЬНЫЙ ТРЕЙС (системный, с временными метками)")
        lines.append(trace_text)

    # Готовые результаты (полные)
    lines.append("\n## ГОТОВЫЕ РЕЗУЛЬТАТЫ (полный текст)")
    for d in state.deliverables():
        lines.append(f"\n  --- {d.get('role')} / {d.get('task','')[:60]} ({d.get('time','')}) ---")
        lines.append(d.get("content", ""))

    # Память (ответы пользователя)
    lines.append("\n## ПАМЯТЬ (ответы пользователя)")
    for m in memory.all_entries():
        lines.append(f"  В: {m.get('question','')}")
        lines.append(f"  О: {m.get('answer','')}")

    text = "\n".join(lines)
    fname = f"ai-office-log-{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    return StreamingResponse(
        iter([text]),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )

@router.get("/api/trace")
async def get_trace(limit: int = 400):
    """Детальный системный трейс (JSON): время, инструменты, длительности, публикации."""
    from src.office import trace as _trace
    return {"trace": _trace.tail(max(1, min(limit, 4000)))}

@router.get("/api/observability/timeline")
async def get_observability_timeline(limit: int = 400, since: float | None = None,
                                     until: float | None = None):
    """Единая временная шкала офиса: trace + промпты + решения + срезы мира,
    слитые по времени с перекрёстными ссылками (Phase 0.5)."""
    from src.office import observability
    return {"timeline": observability.timeline(since=since, until=until,
                                               limit=max(1, min(limit, 2000)))}

@router.get("/api/observability/decision/{decision_id}")
async def get_observability_decision(decision_id: str):
    """Полная цепочка одного решения: промпт → исполнение (trace) → world.diff
    до/после (Phase 0.5 DoD)."""
    from src.office import observability
    return observability.decision_chain(decision_id)

@router.get("/api/deliverables")
async def get_deliverables():
    """Готовые результаты работы агентов — пользователь может посмотреть и скопировать."""
    return {"deliverables": _with_worker_id(state.deliverables())}

@router.get("/api/progress")
async def get_progress():
    """Текущий этап развития офиса для индикатора прогресса (динамические этапы)."""
    return milestones.progress_payload()

@router.get("/api/milestones")
async def get_milestones():
    """Полный список этапов со сводками и записями проделанной работы."""
    return {"stages": milestones.all_stages()}

@router.get("/api/milestone/{stage_id}")
async def get_milestone(stage_id: str):
    """Детали одного этапа: сводка + что уже сделано."""
    m = milestones.get(stage_id)
    if m is None:
        return JSONResponse({"error": "этап не найден"}, status_code=404)
    return m

@router.get("/api/agent/{agent_id}")
async def get_agent_detail(agent_id: str):
    """Карточка агента: что делает сейчас и что уже сделал."""
    rec = registry.get(agent_id)
    if rec is None:
        return JSONResponse({"error": "агент не найден"}, status_code=404)
    return {
        "agent_id": rec.agent_id,
        "worker_id": rec.agent_id,  # BOS §12 п.4: agent_id deprecated-алиас
        "role": rec.role,
        "status": rec.status,
        "task": rec.task,
        "current": rec.last_message or rec.task,
        "done": _with_worker_id(state.deliverables_for(agent_id)),
        "activity": _with_worker_id(state.events_for(agent_id)),
        "model": models_module.for_agent(agent_id),
        "model_custom": agent_id in models_module.assignments(),
        "cost": costs_module.for_agent(agent_id),
    }

@router.get("/api/department-events")
async def get_department_events():
    """Доменные события офиса (Event Layer): сигналы отделов и их статус."""
    from src.office import events as events_module
    evs = events_module.recent(40)
    return {"events": evs, "pending": sum(1 for e in evs if not e.get("processed"))}

@router.post("/api/brief/reset")
async def brief_reset():
    """Полный сброс ТЕКУЩЕГО тенанта: новый клиент с чистого листа."""
    # СНАЧАЛА гасим живой офис-цикл: иначе его задача переживала wipe и продолжала
    # работать со старым состоянием в RAM — реанимировала план/стратегию и жгла токены.
    office_loop.forget_tenant(saas_context.get_tenant())
    models_module.reset()      # сбрасываем индивидуальные модели, глобальную оставляем
    saas_context.wipe()        # удаляет все файлы данных тенанта (бриф, состояние, код, стратегия, ТЗ…)
    return {"ok": True}

@router.get("/api/org-graph")
async def get_org_graph():
    """Узлы и рёбра для вкладки «Сценарии» (см. docs/scenario-graph-tab-spec.md)."""
    from src.office import org_graph
    return org_graph.build()

@router.post("/api/agent/{agent_id}/pause")
async def pause_agent(agent_id: str):
    """Ставит ОДНОГО сотрудника на паузу — в отличие от /api/office/pause,
    не трогает остальную компанию. Лидер отдела перестаёт предлагать ему задачи."""
    ok = registry.pause(agent_id)
    if not ok:
        return JSONResponse({"error": "агент не найден"}, status_code=404)
    return {"ok": True, "agent_id": agent_id, "paused": True}

@router.post("/api/agent/{agent_id}/resume")
async def resume_agent(agent_id: str):
    ok = registry.resume(agent_id)
    if not ok:
        return JSONResponse({"error": "агент не найден"}, status_code=404)
    office_loop.wake_tenant()
    return {"ok": True, "agent_id": agent_id, "paused": False}

@router.post("/api/agent/{agent_id}/model")
async def set_agent_model(agent_id: str, request: Request):
    """Назначить агенту индивидуальную модель (пустая — вернуть к общей)."""
    data = await request.json()
    model = (data.get("model") or "").strip()
    models_module.set_for_agent(agent_id, model)
    return {"ok": True, "agent_id": agent_id, "worker_id": agent_id,
            "model": models_module.for_agent(agent_id)}

@router.post("/api/role/{role}/model")
async def set_role_model(role: str, request: Request):
    """Назначить модель для роли (пустая — вернуть к глобальной). По умолчанию не задано."""
    data = await request.json()
    model = (data.get("model") or "").strip()
    models_module.set_for_role(role, model)
    return {"ok": True, "role": role, "model": models_module.for_role(role)}
