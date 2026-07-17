"""
«Работа»: файлы/хранилище/терминал, план задач, проекты, процессы, спецификация, инициативы, решения. Перенесено из server.py (docs/technical-due-diligence-
2026-07-17.md §3.2.1, PR-5) механически — тот же код, то же поведение.
"""

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from fastapi.requests import Request
from fastapi.responses import Response
import asyncio
from src.office import bus
from src.office import decisions as decisions_module
from src.office import initiatives as initiatives_module
from src.office import milestones
from src.office import loop as office_loop
from src.office import plan as plan_module
from src.office import progress
from src.office import registry
from src.office import roles as roles_module
from src.saas import context as saas_context
from src.office import sites as sites_module
from src.office import state
from src.office import workspace as workspace_module
from routers.shared import rate_limited as _rate_limited

router = APIRouter()


@router.get("/api/files")
async def get_files():
    """Список файлов кода, написанных агентами в рабочей папке проекта."""
    return {"files": workspace_module.list_files()}

@router.get("/api/storage/usage")
async def get_storage_usage():
    """Разбивка использования диска тенантом (вкладка «Хранилище») — сколько
    занимают файлы проектов (по папке), системные данные и Docker-ресурсы
    (постоянные приложения/MCP-серверы), не только сырой список файлов."""
    from src.office import storage_usage
    return storage_usage.summary()

@router.get("/api/plan")
async def get_plan():
    """Доска задач офиса: todo/doing/done + прогресс. Для вкладки «Задачи»."""
    tasks = plan_module.all_tasks()
    # имя исполнителя через роль (developer_1 → Разработчик) делаем на фронте
    return {
        "generated": plan_module.is_generated(),
        "tasks": tasks,
        "progress": plan_module.progress(),
    }

@router.get("/api/file")
async def get_file(path: str):
    """Содержимое одного файла из рабочей папки (для вкладки «Папки»)."""
    from fastapi.responses import PlainTextResponse
    content = workspace_module.read_file(path)
    return PlainTextResponse(content)

@router.get("/api/raw/{path:path}")
async def get_raw_file(path: str):
    """
    Сырой файл рабочей папки с корректным content-type и по path-адресу
    (а не query). Нужно для превью многофайлового сайта во вкладке «Папки»:
    при загрузке index.html через src относительные css/js/картинки резолвятся
    от /api/raw/<dir>/ и подтягиваются автоматически.
    """
    import mimetypes
    from fastapi.responses import Response
    data = workspace_module.read_bytes(path)
    if data is None:
        return Response(content=b"not found", status_code=404)
    ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
    return Response(content=data, media_type=ctype)

@router.post("/api/run")
async def run_file(request: Request):
    """Запустить файл из рабочей папки (.py / .js / .sh) и вернуть вывод.

    ⚠️ Исполнение процесса не изолировано от файловой системы хоста
    (docs/audit-dd-2026-07.md §17) — выключено по умолчанию оператором.
    """
    if not workspace_module.code_execution_allowed():
        return JSONResponse(
            {"ok": False, "error": "code_execution_disabled",
             "output": workspace_module._DISABLED_MSG}, status_code=403)
    if _rate_limited("run", saas_context.get_tenant(), 15):
        return JSONResponse({"ok": False, "output": "Слишком много запусков подряд — подождите минуту."},
                            status_code=429)
    data = await request.json()
    path = (data.get("path") or "").strip()
    stdin = data.get("stdin") or ""
    if not path:
        return JSONResponse({"ok": False, "output": "Нужен path файла."})
    output = workspace_module.execute_code(path, stdin)
    ok = not output.startswith("❌")
    return JSONResponse({"ok": ok, "output": output})

@router.post("/api/terminal")
async def terminal(request: Request):
    """Терминал рабочей папки: выполняет команду в workspace тенанта (cwd — подпапка).

    ⚠️ shell=True не ограничивает саму команду (path traversal через `cat ../../
    <tenant>/...`, чтение .env и т.п.) — docs/audit-dd-2026-07.md §17. Выключено
    по умолчанию оператором до появления реальной песочницы исполнения.
    """
    if not workspace_module.code_execution_allowed():
        return JSONResponse(
            {"ok": False, "error": "code_execution_disabled",
             "output": workspace_module._DISABLED_MSG}, status_code=403)
    if _rate_limited("terminal", saas_context.get_tenant(), 15):
        return JSONResponse({"ok": False, "output": "Слишком много команд подряд — подождите минуту."},
                            status_code=429)
    data = await request.json()
    cmd = (data.get("cmd") or "").strip()
    cwd = (data.get("cwd") or "").strip()
    if not cmd:
        return JSONResponse({"ok": False, "output": "Введите команду."})
    output = workspace_module.run_command(cmd, cwd)
    ok = not output.startswith("❌")
    return JSONResponse({"ok": ok, "output": output})

@router.post("/api/task/{task_id}/reassign")
async def reassign_task(task_id: str, request: Request):
    """Переназначить задачу другому исполнителю (вкладка «Сценарии»). Body: {agent_id}."""
    from src.office import plan as plan_mod
    data = await request.json()
    agent_id = (data.get("agent_id") or "").strip()
    if not agent_id:
        return JSONResponse({"error": "agent_id обязателен"}, status_code=400)
    target = registry.get(agent_id)
    if not target:
        return JSONResponse({"error": "агент не найден"}, status_code=404)
    task = plan_mod.get_task(task_id)
    if not task:
        return JSONResponse({"error": "задача не найдена"}, status_code=404)
    if task.get("role") != target.role:
        return JSONResponse(
            {"error": f"агент {agent_id} — роль {target.role}, задаче нужна роль {task.get('role')}"},
            status_code=409)
    if not plan_mod.reassign(task_id, agent_id):
        return JSONResponse({"error": "задачу нельзя переназначить в её текущем статусе"}, status_code=409)
    office_loop.wake_tenant()
    return {"ok": True, "task_id": task_id, "agent_id": agent_id}

@router.get("/api/objectives")
async def get_objectives():
    """Objectives — измеримые цели компании (desired state)."""
    from src.office import objectives as objectives_module
    return {"objectives": objectives_module.all_objectives()}

@router.post("/api/objectives")
async def post_objective(request: Request):
    """Создать/обновить Objective. Body: {title, desired?, measured_by?, priority?}
    или {id, ...patch} для обновления."""
    from src.office import objectives as objectives_module
    data = await request.json()
    if data.get("id"):
        obj = objectives_module.update(data["id"], **data)
        return {"ok": bool(obj), "objective": obj}
    if not (data.get("title") or "").strip():
        return {"ok": False, "message": "Нужен title"}
    obj = objectives_module.add(
        data["title"], desired=data.get("desired", ""),
        measured_by=data.get("measured_by", ""),
        priority=int(data.get("priority", 50)), source="owner",
        project_id=data.get("project_id", ""))
    return {"ok": True, "objective": obj}

@router.get("/api/intents")
async def get_intents():
    """Журнал намерений владельца и их интерпретаций (Intent Layer)."""
    from src.office import intent as intent_module
    return {"intents": intent_module.recent(50)}

@router.get("/api/projects")
async def get_projects():
    """Проекты компании: активные (может быть несколько параллельно, см.
    project_limits) + очередь + история с «что оставил после себя»."""
    from src.office import projects as projects_module
    return {"projects": projects_module.all_projects(),
            "active": projects_module.active(),
            "active_count": projects_module.active_project_count(),
            "max_active": projects_module.get_limit()}

@router.post("/api/projects/limit")
async def set_project_limit(request: Request):
    """Сколько проектов офис ведёт ОДНОВРЕМЕННО — владелец настраивает сам
    (по умолчанию 3, см. projects.DEFAULT_MAX_ACTIVE)."""
    from src.office import projects as projects_module
    body = await request.json()
    n = int(body.get("max_active", projects_module.DEFAULT_MAX_ACTIVE))
    projects_module.set_limit(n)
    return {"ok": True, "max_active": projects_module.get_limit()}

@router.post("/api/project/{project_id}/pause")
async def post_project_pause(project_id: str):
    """Ставит проект на паузу — освобождает слот параллельности для очереди,
    не закрывая Work (см. src/office/projects.py:pause)."""
    from src.office import projects as projects_module
    proj = projects_module.pause(project_id)
    if not proj:
        raise HTTPException(status_code=400, detail="Проект не найден или не активен")
    return {"ok": True, "project": proj}

@router.post("/api/project/{project_id}/resume")
async def post_project_resume(project_id: str):
    from src.office import projects as projects_module
    proj = projects_module.resume(project_id)
    if not proj:
        raise HTTPException(status_code=400, detail="Проект не найден или не на паузе")
    return {"ok": True, "project": proj}

@router.post("/api/projects/reorder")
async def post_projects_reorder(request: Request):
    """Приоритет очереди проектов — владелец решает, кто из ожидающих
    активируется раньше при освобождении слота (см. projects.reorder_queue)."""
    from src.office import projects as projects_module
    body = await request.json()
    projects_module.reorder_queue(body.get("order") or [])
    return {"ok": True}

@router.get("/api/processes")
async def get_processes():
    """Повторяющиеся процессы (BOS §5: Process — recurring action, не только
    поток Instance вроде продаж) — «контент-завод», «ежедневная аналитика»."""
    from src.office import processes as processes_module
    return {"processes": processes_module.all_processes()}

@router.post("/api/processes")
async def create_process(request: Request):
    from src.office import processes as processes_module
    body = await request.json()
    title = (body.get("title") or "").strip()
    role = (body.get("role") or "").strip()
    instruction = (body.get("instruction") or "").strip()
    if not title or not role or not instruction:
        raise HTTPException(status_code=400, detail="Нужны title, role и instruction")
    proc = processes_module.create(title, role, instruction, body.get("cadence", "every_cycle"))
    office_loop.wake_tenant()
    return {"ok": True, "process": proc}

@router.post("/api/process/{process_id}/pause")
async def pause_process(process_id: str):
    from src.office import processes as processes_module
    proc = processes_module.set_status(process_id, "paused")
    if not proc:
        raise HTTPException(status_code=404, detail="Процесс не найден")
    return {"ok": True, "process": proc}

@router.post("/api/process/{process_id}/resume")
async def resume_process(process_id: str):
    from src.office import processes as processes_module
    proc = processes_module.set_status(process_id, "active")
    if not proc:
        raise HTTPException(status_code=404, detail="Процесс не найден")
    return {"ok": True, "process": proc}

@router.post("/api/process/{process_id}/delete")
async def delete_process(process_id: str):
    from src.office import processes as processes_module
    ok = processes_module.delete(process_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Процесс не найден")
    return {"ok": True}

@router.get("/api/project/{project_id}")
async def get_project_detail(project_id: str):
    """Карточка одного проекта: сам проект + его задачи, прогресс, СВОИ этапы
    (Stage теперь привязаны к Work — BOS §5/§14 п.6) и СВОИ артефакты (сайты +
    готовые материалы) — «Итоги» были общим котлом на всю компанию, теперь это
    выдача конкретного Work (карта сайта, рефакторинг сессии 2026-07-05)."""
    from src.office import projects as projects_module
    proj = projects_module.get(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Проект не найден")
    tasks = plan_module.for_project(project_id)
    tid = saas_context.get_tenant()
    proj_sites = [{**s, "url": f"/site/{tid}/{s['slug']}"} for s in sites_module.for_project(project_id)]
    return {
        "project": proj,
        "tasks": tasks,
        "progress": plan_module.progress(project_id),
        "milestones": milestones.progress_payload(project_id),
        "sites": proj_sites,
        "deliverables": state.deliverables_for_project(project_id),
    }

@router.get("/api/specification")
async def get_specification(project_id: str = ""):
    """Спецификация работы — контракт приёмки (Acceptance L1). per-project
    (см. specification.py): без project_id — контракт активного проекта по
    умолчанию, как раньше; с project_id — контракт конкретного параллельного Work."""
    from src.office import specification as spec_module
    return spec_module.get(project_id) or {"status": "none"}

@router.get("/api/specifications")
async def get_all_specifications():
    """Контракты приёмки ВСЕХ проектов тенанта разом — вкладка «Проект» может
    показать спецификацию каждого параллельного Work, не только активного."""
    from src.office import specification as spec_module
    return {"items": spec_module.all_specs()}

@router.post("/api/specification/confirm")
async def confirm_specification(request: Request):
    """Владелец подтверждает спецификацию. Body: {note?, project_id?}."""
    from src.office import specification as spec_module
    data = await request.json() if (await request.body()) else {}
    spec = spec_module.confirm(data.get("note", ""), data.get("project_id", ""))
    return {"ok": True, "specification": spec}

@router.post("/api/task/{task_id}/unblock")
async def unblock_task(task_id: str):
    """Вернуть заблокированную задачу в очередь (решение владельца/CEO)."""
    from src.office import plan as plan_mod
    from src.office import events as events_module
    if not plan_mod.unblock(task_id):
        return {"ok": False, "message": "Задача не найдена или не заблокирована"}
    # kind-контракт BOS §10: разблокировка задачи закрывает её blocker-событие,
    # иначе оно вечно висело в pending и в World Model.
    events_module.resolve_for_task(task_id)
    office_loop.wake_tenant()
    return {"ok": True}

@router.get("/api/decisions")
async def get_decisions(request: Request):

    return decisions_module.payload()

@router.get("/api/initiatives")
async def get_initiatives(request: Request):

    return initiatives_module.payload()

@router.post("/api/initiatives")
async def propose_initiative(request: Request):
    """Предприниматель сам предлагает инициативу (BOS §5: Intent не обязан идти
    только от AI-наблюдения) — минимальный ввод, глубокий анализ офис делает
    сам в фоне (не блокируем HTTP-ответ длинным LLM-вызовом с поиском)."""
    import asyncio
    from src.office import initiative_research
    from src.saas import context as ctx
    body = await request.json()
    title = (body.get("title") or "").strip()
    idea = (body.get("idea") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Нужно название инициативы")
    iid = initiatives_module.propose(title, idea)

    tid = ctx.get_tenant()

    async def _bg():
        ctx.set_tenant(tid)
        await initiative_research.run(iid, title, idea, bus.publish)

    asyncio.create_task(_bg())
    return {"ok": True, "id": iid}

@router.post("/api/initiative/{iid}/accept")
async def accept_initiative(iid: str, request: Request):
    """Принятая инициатива — BOS §5: decision spawn_project. Каждая принятая
    инициатива — СВОЙ Work, а не дозапись в первый попавшийся активный проект
    (раньше вторая инициатива молча растворялась в задачах первой, если та
    была активна и непуста). Если слоты параллельных проектов заняты
    (projects.get_limit(), по умолчанию 3) — новый Work встаёт в очередь
    (status="queued") и активируется сам, когда что-то закроется.

    Идемпотентность (docs/technical-due-diligence-2026-07-17.md §5.6): двойной
    клик или ретрай сети на этой кнопке раньше мог создать проект и задачи
    ДВАЖДЫ. Если фронт прислал заголовок Idempotency-Key — второй запрос с
    тем же ключом вернёт ПРЕЖНИЙ результат, не тронув план повторно."""
    from routers.shared import idempotent
    idem_key = (request.headers.get("idempotency-key") or "").strip()
    tid = saas_context.get_tenant()
    return await idempotent(f"accept_initiative:{tid}", f"{iid}:{idem_key}", 300,
                             lambda: _do_accept_initiative(iid, request))


async def _do_accept_initiative(iid: str, request: Request) -> dict:
    from src.office import projects as projects_module
    initiative = next((i for i in initiatives_module.pending() if i["id"] == iid), None)

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    override = bool(body.get("override"))

    # Явный гейт вердикта (docs/product-capability-gaps.md п.6): если анализ
    # сказал "не стоит", принять инициативу всё ещё можно (последнее слово у
    # владельца, BOS §2), но НЕ тихо мимо рекомендации — фронт должен явно
    # переспросить и прислать override=true вторым запросом.
    try:
        tasks = initiatives_module.accept(iid, override=override)
    except initiatives_module.InitiativeBlocked as e:
        return JSONResponse({
            "error": "initiative_blocked",
            "recommendation": e.recommendation,
            "research": e.research,
            "message": "Исследование рекомендует НЕ делать эту инициативу. "
                       "Чтобы принять вопреки рекомендации, повторите запрос с override=true.",
        }, status_code=409)

    # Аудит (docs/pre-release-audit-2026-07-15.md, находка Medium #8): реальный
    # прогон показал, что цель брифа («сайт для лидов») и принятая инициатива
    # («пересборка лендинга под заявки») — оба про сайт одного и того же бизнеса —
    # заводили КАЖДЫЙ свой отдельный проект, и оба независимо опубликовали СВОЙ
    # сайт. Для владельца это выглядит как два разных URL с двумя версиями одной
    # компании без единого объяснения зачем. Правило: если новая инициатива сама
    # трогает site/ (developer/designer-задачи), а среди уже активных проектов
    # есть такой, что УЖЕ опубликовал сайт — не открываем второй параллельный
    # сайт-проект молча, а дозаписываем задачи инициативы в СУЩЕСТВУЮЩИЙ, с явным
    # объяснением в ленте. Другие типы инициатив (бот, CRM, контент-план и т.п.)
    # это правило не затрагивает — параллельные Work по разным артефактам
    # остаются штатной моделью (BOS §1, §4).
    initiative_touches_site = any(plan_module.touches_site(t) for t in tasks)
    reused_site_project = None
    if initiative_touches_site:
        for p in projects_module.active_list():
            if p.get("type") != "project":
                continue
            # Аудит логов 2026-07-17: гейт на sites_module.for_project() (сайт
            # УЖЕ опубликован) не срабатывает, если вторая site-инициатива
            # принимается в первые секунды офис-цикла — до того, как ПЕРВЫЙ
            # (из брифа/BOOTSTRAP) проект успел опубликовать. Оба тогда строят
            # site/ ПАРАЛЛЕЛЬНО — а site/ на диске один на тенанта (см.
            # critic.site_dir()), т.е. это не просто путаница в UI, а гонка,
            # затирающая работу друг друга. Критерий переиспользования — не
            # «уже опубликован», а «уже есть активный проект, чьи задачи
            # трогают site/», публикация тут ни при чём.
            if sites_module.for_project(p["id"]) or any(
                    plan_module.touches_site(t) for t in plan_module.for_project(p["id"])):
                reused_site_project = p
                break

    if reused_site_project:
        proj = reused_site_project
        await bus.publish({"type": "system",
                           "text": f"🔗 Инициатива «{(initiative or {}).get('title', '')}» тоже "
                                   f"про сайт — задачи добавлены в уже идущий проект «{proj['title']}» "
                                   f"(уже опубликовал сайт), а не в отдельный: одному бизнесу — один сайт."})
    else:
        proj = projects_module.create((initiative or {}).get("title", ""),
                                       (initiative or {}).get("rationale", ""))
    added = 0
    skipped_roles: list[str] = []
    # Двухпроходное построение графа: LLM отдаёт зависимости через СВОИ
    # временные id (t1, t2, ...) — реальные id задача получает только внутри
    # add_task(). Первый проход создаёт задачи и запоминает temp→real;
    # второй патчит deps через plan.set_deps (BOS §5: сценарий составлен ДО
    # начала работы, а не придумывается на ходу).
    temp_to_real: dict[str, str] = {}
    created: list[tuple[str, list[str]]] = []
    for t in tasks:
        role = (t.get("role") or "").strip()
        title = (t.get("title") or "").strip()
        # Реальный кейс (лог прогона 2026-07-09): CEO придумал роли "copywriter"/
        # "product analyst" для задач инициативы — такой роли в офисе нет, задача
        # молча осиротела бы (planning_engine.has_orphan_tasks её просто скипнет
        # позже), а отдел вместо неё изобрёл СОВСЕМ ДРУГОЙ план с нуля: клиент
        # принял одну инициативу, а по факту получил другую. Отсекаем на входе,
        # а не даём тихо разъехаться утверждённому плану и реально исполненному.
        if role and role not in roles_module.known_roles():
            skipped_roles.append(f"{title} (роль «{role}» не существует)")
            continue
        if role and title:
            real = plan_module.add_task(title, role, t.get("done_criterion", ""),
                                        requested_by="user", project_id=proj["id"])
            added += 1
            temp_id = (t.get("id") or "").strip()
            if temp_id:
                temp_to_real[temp_id] = real["id"]
            deps = [d for d in (t.get("deps") or []) if isinstance(d, str)]
            if deps:
                created.append((real["id"], deps))
    for real_id, temp_deps in created:
        resolved = [temp_to_real[d] for d in temp_deps if d in temp_to_real]
        if resolved:
            plan_module.set_deps(real_id, resolved)

    proj_after = projects_module.get(proj["id"]) if added else proj

    # Своя спецификация для ЭТОГО проекта сразу, не когда-нибудь позже в цикле
    # BOOTSTRAP (тот вызов покрывает только проект, созданный из брифа при
    # старте офиса) — без этого 100% задач второго параллельного Work сверялись
    # бы с чужим контрактом (реальный кейс, см. specification.py докстринг).
    from src.office import specification as spec_module
    spec_module.ensure(proj["id"])

    # Раньше принятие инициативы не оставляло НИ ОДНОГО следа в ленте событий —
    # новый проект с командой и бюджетом появлялся молча, владелец узнавал о нём
    # только случайно наткнувшись на вкладку «Проект». Теперь видно явно, что
    # именно произошло и почему тратится бюджет. Если проект переиспользован
    # (см. reused_site_project выше) — объяснение уже отправлено там, второе
    # сообщение только дублировало бы его другими словами.
    if not reused_site_project:
        await bus.publish({"type": "system",
                           "text": f"💡 Инициатива «{(initiative or {}).get('title', '')}» принята — "
                                   f"открыт проект «{proj_after['title'] if proj_after else proj['title']}» "
                                   f"({added} задач(и))"})
    if skipped_roles:
        await bus.publish({"type": "system",
                           "text": f"⚠️ {len(skipped_roles)} задач(и) инициативы пропущено "
                                   f"(несуществующая роль): {'; '.join(skipped_roles[:3])}"})

    office_loop.wake_tenant()
    return {
        "ok": True, "tasks_added": added, "tasks_skipped": len(skipped_roles),
        "project_id": proj_after["id"] if proj_after else "",
        "project_title": proj_after["title"] if proj_after else "",
    }

@router.post("/api/initiative/{iid}/reject")
async def reject_initiative(iid: str, request: Request):

    initiatives_module.reject(iid)
    return {"ok": True}
