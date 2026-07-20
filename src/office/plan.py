"""
План-граф задач — машинночитаемый список задач компании (per-tenant).

В отличие от текстовой стратегии/ТЗ (по которым агенты «додумывают»), это структура:
задача = {id, title, role, department, deps, status, done_criterion}. Лидер берёт из
графа СЛЕДУЮЩУЮ готовую к работе задачу своего отдела (зависимости выполнены) — это
убирает дубли, делает прогресс измеримым, а «готово» проверяемым.

Хранилище: data/tenants/<tid>/plan.json — {tasks: [...], generated: bool}.
"""

import time

from src.saas import context as ctx
from src.office import org, needs

_FILE = "plan.json"


def _data() -> dict:
    return ctx.read_json(_FILE, {"tasks": [], "generated": False})


# Роли, у которых есть отдел-исполнитель. Задача с ролью вне этого набора не
# маршрутизируется (department=='' → её никто не берёт), и офис тихо стопорился.
_ROLE_REMAP = {
    "researcher": "analyst", "architect": "developer", "strategist": "marketer",
    "hr": "developer", "cto": "developer", "cmo": "marketer", "sales_lead": "salesman",
    "seo": "marketer", "qa": "developer", "copywriter": "marketer", "ux": "developer",
    # designer слит в developer (один владелец артефакта site/, см. roles.py) —
    # редирект нужен для старых тенантов/промптов, которые ещё помнят роль "designer".
    "designer": "developer",
}


def _valid_role(role: str) -> str:
    """Приводит роль задачи к исполнимой (с реальным отделом). Неизвестную → developer."""
    role = (role or "").strip()
    if org.department_of_role(role):
        return role
    return _ROLE_REMAP.get(role, "developer")


# ── Детерминированная маршрутизация бота записи ──────────────────────────────
# Бизнес-правило «бот записи клиентов / сбора лидов → ТОЛЬКО integrator, НИКОГДА
# developer» раньше жило исключительно в подсказке LLM-пути лидеров
# (leaders._DEPT_HINTS), который работает только до генерации плана — то есть
# почти никогда. Живая детерминированная маршрутизация правило не знала: план мог
# назначить booking-бота developer, и никто не поправлял (скрытый прод-баг).
# Платформа имеет готовый движок записи (bot_engine) — его настраивает и запускает
# integrator (launch_bot), кастомный код developer тут не нужен. Бот с НЕСТАНДАРТНОЙ
# логикой (постинг в группу, парсинг, рассылка) — исключение, остаётся у developer.
# Детектор «бот» — needs.is_bot_reference (единая точка; НЕ голая подстрока «бот»,
# см. предупреждение в needs.py про «работать/доработать»).
_BOOKING_WORDS = ("запис", "бронир", "лид", "заяв", "букинг", "booking")
_CUSTOM_BOT_WORDS = ("постинг", "парс", "групп", "кастом", "рассылк", "нестандарт")


def _route_role(role: str, title: str) -> str:
    """Детерминированно корректирует роль задачи по заголовку. Задача про бота
    записи/сбора лидов принудительно уходит integrator (кроме кастомной логики)."""
    role = _valid_role(role)
    if role not in ("developer", "designer", "integrator"):
        return role
    t = (title or "").lower()
    is_bot = needs.is_bot_reference(t)
    if is_bot and any(w in t for w in _BOOKING_WORDS) \
            and not any(w in t for w in _CUSTOM_BOT_WORDS):
        return "integrator"
    return role


# ── Artifacts-декларации (BOS §12) ───────────────────────────────────────────
# Задача ОБЪЯВЛЯЕТ, какой артефакт производит/трогает — это ЕДИНСТВЕННЫЙ источник
# для мьютекса (plan.touches_site), выбора уровней приёмки (acceptance) и capability-
# гейта. Раньше «трогает ли задача сайт» определялось по словам в ЗАГОЛОВКЕ в момент
# ПОТРЕБЛЕНИЯ (plan._NON_SITE_WORDS, acceptance._SITE_WORDS) — и дважды ловило один
# прод-баг (QA-задача «Собрать сценарий проверки» без site-слов реально писала в
# site/). Теперь тип артефакта выводится ОДИН раз при генерации плана и хранится в
# задаче; потребители читают декларацию, а не парсят заголовок заново.
#
# Словарь артефактов: "site" (папка site/), "bot" (Telegram-бот), "integration"
# (внешний сервис), "doc" (тексты/аналитика в docs/).
def _derive_artifacts(role: str, title: str) -> list[str]:
    """Тип артефакта задачи по роли+заголовку (единая точка вывода). LLM-план может
    задать `artifacts` явно — тогда вывод не нужен (см. set_tasks)."""
    t = (title or "").lower()
    if needs.is_bot_reference(t):
        return ["bot"]
    if role == "developer":
        # developer по умолчанию пишет в site/ (тот же инвертированный
        # безопасный принцип, что был в touches_site) — кроме бот-задач (выше)
        # и фоновых скриптов/процессов (реальный найденный баг: см. docstring
        # needs.is_process_reference — иначе такая задача ложно считалась
        # «тоже про сайт» и accept_initiative молча сливал её в чужой проект).
        if needs.is_process_reference(t):
            return ["doc"]
        return ["site"]
    if role == "designer":
        # designer вернулась (2026-07-14) как отдельная роль, но артефакт — НЕ
        # site/: она производит docs/brand_book.md ДО того, как developer начнёт
        # писать код (см. roles.py.ROLE_META["designer"], builtin_skills/brand_book.md).
        # Тот же "doc", что у marketer/analyst — не участвует в site-мьютексе.
        return ["doc"]
    if role == "integrator":
        return ["integration"]
    return ["doc"]


def artifacts_of(task: dict) -> list[str]:
    """Артефакты задачи: явная декларация или вывод (совместимость со старыми
    задачами без поля artifacts)."""
    arts = task.get("artifacts")
    if arts:
        return list(arts)
    return _derive_artifacts(task.get("role", ""), task.get("title", ""))


def _required_caps(t: dict) -> list[str]:
    """Требуемые способности задачи: явные из LLM-плана → декларация составного
    глагола (workflows.py, Layer 4) → выведенные по словам заголовка
    (capability.derive_required). Составной глагол ("проанализировать Битрикс")
    не выводится из одного слова — у него есть точная декларация, ей отдаём
    приоритет перед угадыванием. Lazy-импорт: оба модуля читают plan."""
    explicit = [c for c in (t.get("required_capabilities") or []) if c]
    if explicit:
        return explicit
    from src.office import workflows
    wf_caps = workflows.required_capabilities_of(t.get("title") or "")
    if wf_caps is not None:
        return wf_caps
    from src.office import capability
    return capability.derive_required(t)


def _workflow_id(title: str) -> str:
    from src.office import workflows
    wf = workflows.match(title or "")
    return wf.id if wf else ""


def _save(d: dict) -> None:
    ctx.write_json(_FILE, d)


def is_generated() -> bool:
    return bool(_data().get("generated"))


def resync_pending_milestone(project_id: str, stage_id: str) -> int:
    """Переподписывает ЕЩЁ НЕ ВЗЯТЫЕ в работу задачи проекта на актуальный
    активный этап — см. milestones.mark_active().

    Реальный найденный баг (живой аудит 2026-07-20): set_tasks() подписывает
    milestone_id ОДИН РАЗ, в момент генерации, по "предполагаемому следующему"
    этапу (milestones.active_stage_id — текущий индекс сразу после последнего
    "done"). Если офис ПОСЛЕ этого реально переключает фокус на другой этап
    (decision_engine/planning_engine зовут mark_active другого stage_id,
    минуя "предполагаемый" — например прыгает сразу к "Сборка бота", пропуская
    "Контент"), уже сгенерированные задачи навсегда остаются подписаны старым,
    пропущенным этапом. UI показывал их "без этапа" (тот этап, на который они
    были подписаны, никогда не становится активным), хотя реальная работа шла
    под другим, новым — разрыв между "Прогресс" (который знает про смену
    фокуса) и "Этапы и задачи" (который смотрит только на milestone_id).

    Трогает только status=="pending" — уже взятые/готовые задачи сохраняют
    исторически точную метку того этапа, где реально были начаты/сделаны."""
    d = _data()
    n = 0
    for t in d.get("tasks", []):
        if (t.get("project") == project_id and t.get("status") == "pending"
                and t.get("milestone_id") != stage_id):
            t["milestone_id"] = stage_id
            n += 1
    if n:
        _save(d)
    return n


def set_tasks(tasks: list[dict]) -> None:
    """Сохраняет сгенерированный граф задач (нормализует поля). Задачи принадлежат
    активному ПРОЕКТУ (BOS: Project — единица работы крупнее задачи)."""
    from src.office import projects, milestones
    project_id = projects.ensure_active()["id"]
    # Этап, актуальный для проекта ПРЯМО СЕЙЧАС — единственная точка простановки
    # milestone_id (см. milestones.active_stage_id): задача и её этап связаны
    # ЧЕСТНО (в момент создания), а не подгоняются задним числом. Старые задачи
    # без milestone_id (созданные до этой связи) UI показывает отдельной веткой.
    milestone_id = milestones.active_stage_id(project_id)
    norm = []
    for i, t in enumerate(tasks):
        # роль без отдела → исполнимая (A1); бот записи → integrator (детерминированно)
        role = _route_role(t.get("role") or "", t.get("title") or "")
        tid = (t.get("id") or f"t{i+1}").strip()
        norm.append({
            "id": tid,
            "title": (t.get("title") or "").strip()[:200],
            "role": role,
            "department": org.department_of_role(role),
            "deps": [d for d in (t.get("deps") or []) if d],
            "done_criterion": (t.get("done_criterion") or "").strip()[:200],
            "status": "pending",
            "assignee": "",        # agent_id исполнителя (когда взята в работу)
            "requested_by": "",    # кто поставил (CEO/план или коллега-агент)
            "project": project_id,
            "milestone_id": milestone_id,
            # Подсказка Execution Policy: routine → дешёвая модель (опционально)
            "tier": (t.get("tier") or "").strip().lower(),
            # Декларация артефактов (BOS §12): явная из LLM-плана или выведенная
            "artifacts": [a for a in (t.get("artifacts") or []) if a] or _derive_artifacts(role, t.get("title") or ""),
            # Декларация требуемых способностей (BOS §5): внешние доступы под задачу
            "required_capabilities": _required_caps(t),
            # Составной глагол (Layer 4), если заголовок его матчит — "" для обычных задач
            "workflow_id": _workflow_id(t.get("title") or ""),
        })
    # Чистим deps от ссылок на НЕсуществующие id: LLM иногда генерит зависимость на
    # опечатанный/выдуманный id, и такая задача (и всё, что от неё зависит) НИКОГДА не
    # становится готовой — офис тихо застревал без единой ошибки в логе. Неизвестные deps
    # просто отбрасываем (лучше выполнить раньше, чем не выполнить вообще).
    valid_ids = {t["id"] for t in norm}
    for t in norm:
        cleaned = [d for d in t["deps"] if d in valid_ids and d != t["id"]]
        t["deps"] = cleaned
    _save({"tasks": norm, "generated": True})


def add_task(title: str, role: str, done_criterion: str = "",
             requested_by: str = "", deps: list[str] | None = None, parent: str = "",
             project_id: str = "", artifacts: list[str] | None = None) -> dict:
    """
    Добавляет задачу в доску (например, поставленную КОЛЛЕГОЙ-агентом другому отделу/роли).
    Возвращает созданную задачу. Видна в to-do списке исполнителя и у его лидера.

    `parent` — id другой задачи (BOS §5/§1: вложенность произвольной глубины через
    parent_id вместо отдельной сущности Subtask). Пусто — задача верхнего уровня.

    `project_id` — явная принадлежность проекту (см. параллельные Work,
    projects.active_list()). Пусто — прежнее поведение: задача уходит в
    ensure_active() (единственный/первый активный проект). Явно указывать
    нужно там, где задача рождается ДЛЯ конкретного нового Work (например,
    принятая инициатива), а не для того, что уже само собой активно.

    `artifacts` — явная декларация артефакта (см. _derive_artifacts). Пусто —
    выводится по роли+заголовку, как раньше. Явно указывать нужно там, где
    вызывающий код уже ТОЧНО знает тип артефакта лучше, чем эвристика по
    словам заголовка (например, шаблон задач dashboard_widget.md — см. ниже).
    """
    d = _data()
    tasks = d.get("tasks", [])
    role = _route_role(role, title)  # роль без отдела → исполнимая; бот записи → integrator
    # Дедуп: если такая же незакрытая задача той же роли в ТОМ ЖЕ проекте уже
    # есть — не плодим дубль (циклы делегирования иначе ставили один и тот же
    # таск несколько раз). Раньше матч не проверял project_id вовсе — задача
    # с совпавшим заголовком в СОВСЕМ ДРУГОМ (возможно старом/чужом) проекте
    # тихо "поглощала" новую: принятая инициатива не создавала ничего своего,
    # просто возвращала чужую задачу — выглядело как "инициатива исчезла"
    # (реальный баг: "Автообновление курса USD/RUB"). Инвариант проекта —
    # дедупликация СКОУПЛЕНА проектом, а не глобальная.
    norm_title = " ".join((title or "").lower().split())
    norm_role = (role or "").strip()
    dedup_pid = project_id or None
    for t in tasks:
        if dedup_pid is not None and t.get("project") != dedup_pid:
            continue
        if (t.get("status") in ("pending", "in_progress")
                and t.get("role") == norm_role
                and " ".join((t.get("title", "")).lower().split()) == norm_title):
            return t  # уже стоит в очереди/в работе — возвращаем существующую
    from src.office import projects, milestones
    tid = f"t{len(tasks) + 1}_{int(time.time()) % 10000}"
    pid = project_id or projects.ensure_active()["id"]
    task = {
        "id": tid, "title": (title or "").strip()[:200], "role": (role or "").strip(),
        "department": org.department_of_role((role or "").strip()),
        "deps": [x for x in (deps or []) if x],
        "done_criterion": (done_criterion or "").strip()[:200],
        "status": "pending", "assignee": "", "requested_by": requested_by,
        "project": pid,
        "milestone_id": milestones.active_stage_id(pid),
        "parent": (parent or "").strip(),
        "artifacts": [a for a in (artifacts or []) if a] or _derive_artifacts(role, title),
        "required_capabilities": _required_caps({"title": title}),
        "workflow_id": _workflow_id(title),
    }
    tasks.append(task)
    d["tasks"] = tasks
    d["generated"] = True  # доска становится активной даже если граф не строился
    _save(d)
    return task


def all_tasks() -> list[dict]:
    return list(_data().get("tasks", []))


def for_project(project_id: str) -> list[dict]:
    """Задачи, принадлежащие конкретному проекту (для карточки проекта в UI)."""
    return [t for t in all_tasks() if t.get("project") == project_id]


def children_of(task_id: str) -> list[dict]:
    """Прямые подзадачи (parent_id == task_id) — BOS §5: вложенность вместо Subtask."""
    return [t for t in all_tasks() if t.get("parent") == task_id]


def set_deps(task_id: str, deps: list[str]) -> None:
    """Патчит зависимости уже созданной задачи — нужно для двухпроходного
    построения графа: LLM отдаёт зависимости через свои временные id (t1, t2),
    реальные id задача получает только при add_task(), поэтому граф
    достраивается вторым проходом после того, как все задачи уже созданы."""
    d = _data()
    for t in d.get("tasks", []):
        if t["id"] == task_id:
            t["deps"] = [x for x in deps if x and x != task_id]
            _save(d)
            return


def adopt_orphan_tasks(project_id: str) -> int:
    """Миграция: приписывает задачи БЕЗ проекта (созданные до появления сущности
    Project) к указанному проекту. Возвращает число усыновлённых задач."""
    d = _data()
    n = 0
    for t in d.get("tasks", []):
        if not t.get("project"):
            t["project"] = project_id
            n += 1
    if n:
        _save(d)
    return n


# Статусы, закрывающие задачу. skipped — задача снята осознанно (роль без
# отдела-исполнителя), НЕ выполнена: зависимости она удовлетворяет (иначе всё,
# что от неё зависит, зависло бы навсегда), но в done-прогрессе не врёт.
_CLOSED = ("done", "skipped")


def _done_ids() -> set:
    return {t["id"] for t in all_tasks() if t.get("status") in _CLOSED}


def departments_needed() -> list[str]:
    """Какие отделы нужны для невыполненных задач (для CEO — открыть параллельно)."""
    deps = set()
    for t in all_tasks():
        if t.get("status") not in _CLOSED and t.get("department"):
            deps.add(t["department"])
    return sorted(deps)


def ready_for_department(dept_id: str) -> list[dict]:
    """Все готовые к работе задачи отдела (зависимости выполнены, ещё не сделаны).

    Задачи проекта НЕ на паузе/в очереди (см. projects.pause) — иначе пауза
    проекта ничего не значила бы: план всё равно продолжал бы раздавать его
    задачи воркерам, как будто проект активен."""
    from src.office import projects as projects_module
    active_project_ids = {p["id"] for p in projects_module.active_list()}
    done = _done_ids()
    roles = set(org.member_roles(dept_id))
    out = []
    for t in all_tasks():
        if t.get("status") != "pending":
            continue
        if t.get("department") != dept_id and t.get("role") not in roles:
            continue
        proj = t.get("project", "")
        if proj and proj not in active_project_ids:
            continue
        if all(dep in done for dep in t.get("deps", [])):
            out.append(dict(t))
    return out


def next_for_department(dept_id: str) -> dict | None:
    """Первая готовая к работе задача отдела (или None)."""
    ready = ready_for_department(dept_id)
    return ready[0] if ready else None


# ── Мьютекс артефакта «сайт» ─────────────────────────────────────────────────
# Две задачи, пишущие в site/, НЕЛЬЗЯ выполнять параллельно: агенты переписывают
# index.html целиком и затирают работу друг друга (реальный кейс: designer затёр
# 3D-версию developer через 9 секунд — «последний победил»).
#
# Мьютекс читает ДЕКЛАРАЦИЮ артефактов задачи (artifacts_of), а не парсит заголовок
# в момент проверки. Раньше «трогает сайт» считалось по словам в ЗАГОЛОВКЕ — и
# дважды ловило баг: QA-задача developer «Собрать сценарий проверки…» без site-слов
# по факту писала в site/, мьютекс её не видел, и два агента 4 минуты параллельно
# переписывали один site/index.html (ai-office-log-20260702_134612). Теперь тип
# артефакта объявлен при генерации задачи (см. _derive_artifacts) и хранится в ней.
def touches_site(task: dict) -> bool:
    """Задача пишет в site/ — по объявленному артефакту «site» (BOS §12)."""
    return "site" in artifacts_of(task)


def site_task_in_progress() -> str:
    """id сайт-задачи, которая сейчас в работе (или ''). Для мьютекса артефакта."""
    for t in all_tasks():
        if t.get("status") == "in_progress" and touches_site(t):
            return t["id"]
    return ""


def mark(task_id: str, status: str) -> None:
    d = _data()
    for t in d.get("tasks", []):
        if t["id"] == task_id:
            t["status"] = status
            t["updated_ts"] = time.time()
            break
    _save(d)


def assign(task_id: str, agent_id: str) -> None:
    """Взять задачу в работу: статус in_progress + закрепить исполнителя."""
    d = _data()
    for t in d.get("tasks", []):
        if t["id"] == task_id:
            t["status"] = "in_progress"
            t["assignee"] = agent_id
            t["updated_ts"] = time.time()
            break
    _save(d)


def complete(task_id: str, acceptance: dict | None = None) -> None:
    """Закрыть задачу. `acceptance` — вердикт приёмки (уровни/проблемы), пишется
    в задачу для UI и History (BOS §8: done только через приёмку)."""
    d = _data()
    for t in d.get("tasks", []):
        if t["id"] == task_id:
            t["status"] = "done"
            if acceptance is not None:
                t["acceptance"] = acceptance
            t["progress_note"] = ""  # задача закрыта — прогресс внутри неё больше не нужен
            t["updated_ts"] = time.time()
            break
    _save(d)


def revert(task_id: str) -> int:
    """Вернуть зависшую/упавшую/не прошедшую приёмку задачу в очередь
    (in_progress → pending). Каждый возврат увеличивает счётчик попыток —
    по нему loop эскалирует вместо вечного цикла fail→revert→fail (BOS §8).
    Возвращает новое число попыток (0, если задача не была in_progress)."""
    d = _data()
    for t in d.get("tasks", []):
        if t["id"] == task_id and t.get("status") == "in_progress":
            t["status"] = "pending"
            t["assignee"] = ""
            t["attempts"] = int(t.get("attempts", 0)) + 1
            t["updated_ts"] = time.time()
            _save(d)
            return t["attempts"]
    return 0


def block(task_id: str, reason: str) -> None:
    """Заблокировать задачу после исчерпания попыток: она уходит с доски исполнителей
    (ready_for_department берёт только pending) и ждёт вмешательства владельца/CEO."""
    d = _data()
    for t in d.get("tasks", []):
        if t["id"] == task_id:
            t["status"] = "blocked"
            t["assignee"] = ""
            t["blocked_reason"] = (reason or "")[:300]
            t["updated_ts"] = time.time()
            break
    _save(d)


def blocked_tasks() -> list[dict]:
    """Заблокированные задачи (ждут решения владельца/CEO) — читается heartbeat'ом
    цикла (loop.py) и personal-чатом CEO (интент-контекст), чтобы «жду разблокировки»
    не было молчаливым и вопрос владельца можно было связать с конкретным блокером."""
    return [t for t in all_tasks() if t.get("status") == "blocked"]


_MAX_PRIOR_BLOCKERS = 3


def unblock(task_id: str) -> bool:
    """Вернуть заблокированную задачу в очередь со сброшенными попытками
    (владелец/CEO вмешался — исполнитель получает чистый счётчик попыток).

    Причину блокировки НЕ стираем бесследно — переносим в prior_blockers
    (round2 audit, N2): раньше unblock() полностью обнулял last_feedback И
    blocked_reason, и переисполнитель начинал СОВСЕМ ВСЛЕПУЮ, без единого
    намёка на то, почему задача уже 3 раза провалилась. Если корень проблемы
    не устранился вмешательством владельца (он просто нажал «разблокировать»,
    не факт что причина уже устранена), задача с высокой вероятностью
    повторяет тот же провал по кругу, никогда не узнавая, что уже пробовала."""
    d = _data()
    for t in d.get("tasks", []):
        if t["id"] == task_id and t.get("status") == "blocked":
            prior = list(t.get("prior_blockers") or [])
            note = (t.get("blocked_reason") or t.get("last_feedback") or "").strip()
            if note:
                prior.append(note)
            t["prior_blockers"] = prior[-_MAX_PRIOR_BLOCKERS:]
            t["status"] = "pending"
            t["attempts"] = 0
            t["blocked_reason"] = ""
            t["last_feedback"] = ""
            t["progress_note"] = ""  # владелец вмешался — исполнитель начинает чисто
            t["updated_ts"] = time.time()
            _save(d)
            return True
    return False


def set_feedback(task_id: str, feedback: str) -> None:
    """Сохранить фидбек приёмки в задаче — попадёт исполнителю при переназначении."""
    d = _data()
    for t in d.get("tasks", []):
        if t["id"] == task_id:
            t["last_feedback"] = (feedback or "")[:500]
            break
    _save(d)


def set_progress_note(task_id: str, note: str) -> bool:
    """Сохранить короткую заметку «что уже сделано / чего жду» — переживает
    переназначение задачи (см. revert(), где НЕ чистится) тому же или другому
    агенту. Реальный найденный баг (форензик-аудит прогона 2026-07-18): скилл
    «Бренд-бук» (внутренний цикл спроси CTO → спроси маркетолога → запиши
    файл) перезапускался с нуля 5 раз подряд, потому что каждое повторное
    взятие той же задачи не знало, на каком шаге агент уже был — контекст
    собирался заново из брифа/памяти/уроков, ни один из которых не хранит
    прогресс ВНУТРИ конкретной задачи. Возвращает False, если задача не
    найдена (вызывающий инструмент должен явно сказать агенту об этом, не
    молчать)."""
    d = _data()
    for t in d.get("tasks", []):
        if t["id"] == task_id:
            t["progress_note"] = (note or "").strip()[:300]
            _save(d)
            return True
    return False


def get_task(task_id: str) -> dict | None:
    for t in all_tasks():
        if t["id"] == task_id:
            return t
    return None


def reassign(task_id: str, agent_id: str) -> bool:
    """Ручное переназначение задачи другому исполнителю (вкладка «Сценарии»).
    Задача возвращается в pending под новым исполнителем — следующий цикл
    планировщика подхватит её как обычную готовую к работе задачу той же роли,
    без специального пути в exec-логике."""
    d = _data()
    for t in d.get("tasks", []):
        if t["id"] == task_id:
            if t.get("status") not in ("pending", "in_progress", "blocked"):
                return False
            t["assignee"] = agent_id
            t["status"] = "pending"
            t["updated_ts"] = time.time()
            _save(d)
            return True
    return False


def for_agent(agent_id: str) -> list[dict]:
    """To-do список конкретного агента: его задачи + поставленные ему коллегами."""
    return [t for t in all_tasks()
            if t.get("assignee") == agent_id and t.get("status") not in _CLOSED]


def board(dept_id: str | None = None) -> dict:
    """Доска задач (todo/doing/done) — целиком или по отделу. Для отслеживания лидером/UI."""
    tasks = all_tasks()
    if dept_id:
        roles = set(org.member_roles(dept_id))
        tasks = [t for t in tasks if t.get("department") == dept_id or t.get("role") in roles]
    return {
        "todo": [t for t in tasks if t.get("status") == "pending"],
        "doing": [t for t in tasks if t.get("status") == "in_progress"],
        "done": [t for t in tasks if t.get("status") == "done"],
        "blocked": [t for t in tasks if t.get("status") == "blocked"],
        "skipped": [t for t in tasks if t.get("status") == "skipped"],
    }


def board_summary(dept_id: str | None = None) -> str:
    """Короткая сводка доски для лидера: «✓3 ⟳1 ☐2» + что в работе."""
    b = board(dept_id)
    doing = "; ".join(f"{t['id']}:{t['title'][:30]}" for t in b["doing"]) or "—"
    blocked = f" ⛔{len(b['blocked'])}" if b.get("blocked") else ""
    skipped = f" ⏭{len(b['skipped'])}" if b.get("skipped") else ""
    return f"✓{len(b['done'])} ⟳{len(b['doing'])} ☐{len(b['todo'])}{blocked}{skipped} | в работе: {doing}"


def progress(project_id: str = "") -> dict:
    """done — реально выполненные; skipped — снятые (роль без отдела). Процент и
    «всё закрыто» считаются по done+skipped, но done НЕ завышается пропущенными.
    project_id задан — считает только по задачам этого проекта (карточка проекта)."""
    tasks = for_project(project_id) if project_id else all_tasks()
    total = len(tasks)
    done = sum(1 for t in tasks if t.get("status") == "done")
    skipped = sum(1 for t in tasks if t.get("status") == "skipped")
    return {"total": total, "done": done, "skipped": skipped,
            "percent": round((done + skipped) / total * 100) if total else 0}


def reset() -> None:
    ctx.delete_file(_FILE)
