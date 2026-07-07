"""
Prompt Builder — компилятор мышления компании (см. docs/bos-architecture.md §7).

ЕДИНАЯ точка сборки всего, что видит воркер: и системного промпта (build), и
контекста задачи (task_context). Чистая функция над состоянием мира: Builder не
знает ничего, чего нет в World Model (бриф, память, знания, план, роли, скиллы).
Понадобилось что-то ещё — это дырка в модели мира, а не повод дописать шаблон.

Слоты (порядок фиксирован спецификацией):
  system:  Identity (роль + специализация) → Policies (team/autonomy/inter_agent)
           → Brief → Memory (указания клиента) → Tools (каталог скиллов роли)
  task:    Business (niche/audience) → Goal → Stage → Department → Task
           → Knowledge (retrieval) → Lessons → Output Format

Роли — файлы `builtin_roles/*.md` (roles.py), политики — файлы `policies/*.md`
(загружаются здесь). Каждая сущность мира сериализуется в промпт ровно одним
сериализатором — например подпись «цель прогона ≠ то, что продаёт бизнес» живёт
только здесь, и класс багов goal/niche не может размазаться по коду.

Философия и Конституция доходят до агента через слой знаний (knowledge GLOBAL →
task_context), поэтому здесь не дублируются — иначе платим за токены дважды.

Каждый собранный промпт ЦЕЛИКОМ логируется в prompts.jsonl тенанта (+ короткая
запись в trace) — отладка «почему агент сделал глупость» стала зрячей.
"""

import json
import time
import uuid
from datetime import datetime
from pathlib import Path

from src.office import roles
from src.office import skills as skills_module
from src.office import memory as memory_module
from src.office import brief as brief_module

_POLICY_DIR = Path(__file__).parent / "policies"
_policy_cache: dict[str, str] = {}


def policy(name: str) -> str:
    """Текст политики из policies/<name>.md (кешируется на процесс)."""
    if name not in _policy_cache:
        f = _POLICY_DIR / f"{name}.md"
        try:
            _policy_cache[name] = f.read_text(encoding="utf-8").strip()
        except OSError:
            _policy_cache[name] = ""
    return _policy_cache[name]


def brief_block() -> str:
    """Блок брифа клиента — ЕДИНСТВЕННЫЙ сериализатор брифа в промпт.
    «goal» — ответ клиента на «какой результат вы хотите ОТ ОФИСА» (onboarding.py),
    НЕ то, что продаёт бизнес; подпись обязательна (реальный баг: сайт продавал
    «упаковку бизнеса» вместо натяжных потолков)."""
    b = brief_module.get()
    if not b:
        return ""
    parts = []
    if b.get("niche"):
        parts.append(f"Ниша — что бизнес продаёт: {b['niche']}")
    if b.get("goal"):
        parts.append(f"Цель ЭТОГО прогона офиса (не то, что продаёт компания): {b['goal']}")
    if b.get("audience"):
        parts.append(f"Аудитория — кому продаёт: {b['audience']}")
    if b.get("assets"):
        parts.append(f"Что есть: {b['assets']}")
    if b.get("constraints"):
        # Раньше тонуло внутри summary (одной строкой среди прочего) — архитектор/
        # воркеры не видели явно, что клиент уже пользуется (CRM/таблицы/рассылки/
        # аналитика) или прямо запретил. Отдельная строка — не пропустишь.
        parts.append(f"Ограничения и уже используемые инструменты клиента: {b['constraints']}")
    if b.get("summary"):
        parts.append(f"Резюме: {b['summary']}")
    if not parts:
        return ""
    return "\n\n=== БРИФ КЛИЕНТА (всегда держи в контексте) ===\n" + "\n".join(parts)


def company_system(policy_name: str, agent_id: str, role: str, task: str,
                   with_brief: bool = True, fmt: dict | None = None,
                   extra: str = "") -> tuple[str, str]:
    """Системный промпт для «штабных» ролей (CEO/лидеры/сервисные) из ЕДИНОГО места:
    текст-политика (policies/<policy_name>.md) + тот же слот Brief, что у воркеров
    (единственный сериализатор goal≠niche — brief_block). Промпт логируется целиком
    в prompts.jsonl (раньше решения CEO/лидеров отлаживались вслепую). Возвращает
    (system, prompt_id) — prompt_id идёт в Decision для сшивки Observability.

    fmt   — подстановки в текст политики через str.format (для параметризованных
            промптов вроде лидерского {title}/{roles_desc}; JSON-скобки в .md должны
            быть удвоены {{ }}).
    extra — доп. блок, дописываемый после Brief (напр. dept-хинты маршрутизации).

    Тексты промптов больше НЕ живут литералами в src/agents — только .md-политики
    (engineering-principles §1 «бизнес-логика не в промптах-литералах», BOS §7)."""
    system = policy(policy_name)
    if fmt:
        system = system.format(**fmt)
    if with_brief:
        system += brief_block()
    if extra:
        system += extra
    pid = log_prompt(agent_id, role, system, task)
    return system, pid


def build(role: str, task: str, agent_id: str, skill: str = "") -> str:
    """Системный промпт воркера: Identity → Policies → Brief → Memory → Tools."""
    identity = roles.render(role)
    if skill:
        identity += f"\n\nТвоя специализация в этом проекте: {skill}"
    policies = "\n\n" + policy("team") + "\n\n" + policy("autonomy") + "\n\n" + policy("inter_agent")
    # Каталог скиллов подмешивается ДИНАМИЧЕСКИ из реестра под роль: добавили скилл
    # с roles=[...] — он сам появился в промпте только у релевантных ролей.
    tools = skills_module.prompt_block(role)
    return identity + policies + brief_block() + memory_module.context_block() + tools


def portfolio_block(role: str) -> str:
    """Обзор всех проектов компании для ролей, видящих бизнес насквозь (BOS §6.2).
    Пусто для рядового воркера и когда проектов ещё нет. Сериализатор Project в
    промпт — ровно один (projects.portfolio), новой сущности мира не вводит.
    Публичная функция (не приватный хелпер task_context): нужна ТАКЖЕ
    orchestrator.decide_company/leaders.decide — их промпт строится отдельно
    (company_system), не через task_context, и раньше портфель CEO/лидерам,
    принимающим РЕАЛЬНЫЕ решения об отделах, вообще не долетал."""
    from src.office import org, projects
    if not org.is_portfolio_role(role):
        return ""
    items = projects.portfolio()
    if not items:
        return ""
    lines = "\n".join(
        f"  • {p['title'] or '(без названия)'} — {p['status']}, папка: {p['workspace_dir'] or '(корень)'}"
        for p in items
    )
    return ("\n=== ПОРТФЕЛЬ ПРОЕКТОВ КОМПАНИИ (ты видишь бизнес целиком) ===\n"
            f"{lines}\n"
            "Файлы любого проекта можешь посмотреть через list_project_files/"
            "read_project_file (только чтение) — решай на срезе всего бизнеса, "
            "а не одного проекта.\n")


def task_context(role: str, task: str, skill: str = "",
                 department: str = "", objective: str = "") -> str:
    """Контекст задачи (user-сообщение воркера): бизнес → цель → этап → отдел →
    задача → знания → уроки → формат результата. Перенесено из loop._task_with_context —
    теперь итоговый промпт собирается в одном модуле и виден целиком."""
    from src.office import org, milestones, knowledge, lessons
    from src.agents import architect

    b = brief_module.get()
    niche = (b.get("niche") or "").strip()
    audience = (b.get("audience") or "").strip()
    biz_line = ""
    if niche:
        biz_line += f"Бизнес клиента — ЧТО он продаёт конечным покупателям: {niche}\n"
    if audience:
        biz_line += f"Аудитория бизнеса — КОМУ он продаёт: {audience}\n"
    goal = brief_module.effective_goal()
    # Активный этап читаем из хранилища вех (SSOT), а не из памяти процесса.
    cur = next((s for s in milestones.all_stages() if s.get("status") == "active"), None)
    stage = f"Текущий этап: {cur['title']}\n" if cur else ""
    skill_line = f"Твоя специализация: {skill}\n" if skill else ""
    dept_line = ""
    if department and department in org.catalog():
        title = org.lead_title(department)
        dept_line = f"Твой отдел: {org.catalog()[department]['name']} (руководитель — {title}).\n"
        if objective:
            dept_line += f"Цель отдела от CEO: {objective}\n"
    tdd = architect.load()
    tdd_section = f"\n=== ТЕХНИЧЕСКОЕ ЗАДАНИЕ АРХИТЕКТОРА (кратко) ===\n{tdd[:3000]}\n" if tdd else ""
    # Портфельный слот (BOS §6.2): роли, видящие бизнес насквозь (CEO/лидеры/
    # надпроектные сервисные), получают обзор ВСЕХ проектов прямо в промпте, а не
    # только по запросу инструмента — чтобы решения уровня бизнеса принимались на
    # срезе портфеля, а не одного проекта. Воркеру этого нет: он заперт в своём.
    portfolio_section = portfolio_block(role)
    lessons_section = lessons.context_block(role)
    knowledge_section = knowledge.context_block(task, department=department)
    # Рекомендованный стек сайта — детерминированная ротация по нише (design_style):
    # без неё designer/developer всегда сваливались в один и тот же vanilla-HTML путь
    # («сайт всегда делается на html» — жалоба владельца). Формулировка стека
    # попадает в keywords нужного скилла при use_skill.
    stack_line = ""
    if role in ("designer", "developer"):
        from src.office import design_style
        stack_line = (f"Рекомендованный стек сайта проекта: {design_style.pick_stack_for(niche, audience)}. "
                      "Строишь/правишь сайт — вызови use_skill, НАЗВАВ этот стек, и работай по плейбуку. "
                      "Существующий сайт на другом стеке НЕ переписывай ради смены стека.\n")
    return (
        f"{biz_line}Цель ЭТОГО прогона офиса (что должен сделать офис для клиента — "
        f"НЕ то, что продаёт компания конечным покупателям): {goal}\n{stage}{dept_line}{skill_line}{stack_line}"
        f"Твоя задача от руководителя: {task}\n"
        f"{tdd_section}{portfolio_section}{knowledge_section}{lessons_section}\n"
        f"Если workspace непуст — начни с list_files, прежде чем писать новый файл, "
        f"чтобы не создать дубликат или не потерять чужую работу.\n"
        f"Выдай конкретный готовый результат. Если нужны свежие данные — web_search "
        f"или request_research. Если нужен доступ к внешнему сервису — get_connection или ask_user с инструкцией."
    )


# ── Лог собранных промптов ────────────────────────────────────────────────────
# Полный текст (system + task) — в prompts.jsonl тенанта; в trace — короткая
# запись-указатель (trace режет строки до 400 символов, целиком туда нельзя).
_PROMPTS_FILE = "prompts.jsonl"
_MAX_PROMPT_BYTES = 4_000_000  # ~4 МБ на тенанта; дальше оставляем хвост
_KEEP_LINES = 200


def log_prompt(agent_id: str, role: str, system: str, task: str) -> str:
    """Логирует собранный промпт целиком в prompts.jsonl и возвращает его prompt_id
    (стабильный идентификатор для сшивки в Observability: trace-запись исполнения и
    Decision, порождённые этим промптом, ссылаются на него по prompt_id)."""
    from src.saas import context as ctx
    from src.office import trace
    pid = f"p_{uuid.uuid4().hex[:8]}"
    try:
        p = ctx.tenant_dir() / _PROMPTS_FILE
        entry = {
            "id": pid,
            "ts": datetime.now().strftime("%H:%M:%S"),
            "t": round(time.time(), 3),
            "agent": agent_id, "role": role,
            "system_chars": len(system), "task_chars": len(task),
            "system": system, "task": task,
        }
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        if p.stat().st_size > _MAX_PROMPT_BYTES:
            keep = p.read_text(encoding="utf-8").splitlines()[-_KEEP_LINES:]
            p.write_text("\n".join(keep) + "\n", encoding="utf-8")
    except Exception:
        pass  # лог промптов не должен ронять офис
    try:
        trace.log("prompt", agent=agent_id, role=role, prompt_id=pid,
                  system_chars=len(system), task_chars=len(task))
    except Exception:
        pass
    return pid


def _read_prompts() -> list[dict]:
    from src.saas import context as ctx
    out: list[dict] = []
    try:
        p = ctx.tenant_dir() / _PROMPTS_FILE
        if not p.exists():
            return out
        for ln in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(ln))
            except Exception:
                continue
    except Exception:
        pass
    return out


def prompt_by_id(pid: str) -> dict | None:
    """Полная запись промпта по prompt_id (или None)."""
    if not pid:
        return None
    for e in reversed(_read_prompts()):
        if e.get("id") == pid:
            return e
    return None


def recent_prompts(n: int = 50) -> list[dict]:
    """Последние N промптов (метаданные без тела — для таймлайна)."""
    out = []
    for e in _read_prompts()[-n:]:
        out.append({k: v for k, v in e.items() if k not in ("system", "task")})
    return out
