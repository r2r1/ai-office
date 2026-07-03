"""
Execution Policy — формальный выбор исполнения задачи (BOS §6).

Оси: стоимость × качество × скорость × доступность. Три решения в одной точке:

1. МОДЕЛЬ ПО ЗАДАЧЕ, не по отделу: рутинная задача (правка, проверка, публикация)
   не должна идти на дорогую reasoning-модель только потому, что её делает
   developer. `decide()` возвращает модель: точечные оверрайды владельца всегда
   главнее; без них рутина уходит на дешёвую модель, остальное — по capability
   роли (существующий путь models.for_agent).

2. ОЦЕНКА СТОИМОСТИ ДО ИСПОЛНЕНИЯ: `estimate_cost()` — грубая оценка $ вызова
   (типовые токены роли × прайс модели). Пишется в trace: расход виден ДО, а не
   только после (инвариант «каждое платное действие знает свой estimated_cost»).

3. CAPABILITY-ГЕЙТ ПРИ ПЛАНИРОВАНИИ: `missing_for_plan()` — каких способностей
   не хватает под задачи плана (телеграм-бот без токена, письма без Gmail).
   Проверяется на bootstrap: владелец узнаёт о недостающем доступе СРАЗУ,
   а не когда исполнитель упрётся в середине задачи.

Лестница исполнителей (детерминированный код > LLM — инвариант):
  детерминированный код → Skill+LLM-воркер → интеграция → внешний исполнитель
  → человек (ask_user, последний резерв). Сегодня лестницу проходит сам воркер
  (use_skill/use_capability); policy формализует выбор модели и доступность.
"""

from src.office import models as models_module

# Слова рутинных задач: не требуют reasoning-модели (правки/проверки/публикации).
_ROUTINE_WORDS = ("исправ", "провер", "почин", "обнови", "опубликуй", "запусти",
                  "настрой", "добав", "поправ", "fix", "check", "publish")

# Дешёвая модель для рутины (существует у провайдера всегда — дефолт-фолбэк офиса).
_ECONOMY_MODEL = models_module.DEFAULT_FREE_MODEL

# Типовой расход токенов на задачу по типу роли (по трейсам прод-прогонов, грубо).
_TYPICAL_TOKENS = {           # (in, out)
    "coding":    (12000, 8000),   # developer/designer/integrator: чтение файлов + код
    "reasoning": (6000, 1500),    # CEO/лидеры/стратег/архитектор
    "text":      (4000, 2000),    # marketer/salesman/hr
    "search":    (5000, 1500),    # researcher/analyst
}


def is_routine(task: dict) -> bool:
    """Рутинная ли задача (по явному tier из плана или по заголовку)."""
    if (task.get("tier") or "").strip().lower() == "routine":
        return True
    if (task.get("tier") or "").strip().lower() == "complex":
        return False
    title = (task.get("title") or "").lower()
    return any(w in title for w in _ROUTINE_WORDS)


def decide(task: dict, agent_id: str, role: str) -> dict:
    """
    Решение об исполнении: {"model": str, "tier": "routine"|"standard", "reason": str,
    "estimated_usd": float}. Точечные оверрайды владельца (per_agent/per_role/expert)
    всегда главнее эвристики — policy не спорит с явной волей.
    """
    from src.office import quality_modes
    cfg_model = models_module.for_agent(agent_id)
    overridden = (
        agent_id in models_module.assignments()
        or role in models_module.role_assignments()
        or quality_modes.get_mode() == "expert"
    )
    if not overridden and is_routine(task):
        model, tier, reason = _ECONOMY_MODEL, "routine", "рутинная задача → дешёвая модель"
    else:
        model, tier = cfg_model, "standard"
        reason = "оверрайд владельца" if overridden else "по capability роли"
    return {"model": model, "tier": tier, "reason": reason,
            "estimated_usd": estimate_cost(role, model)}


def estimate_cost(role: str, model: str) -> float:
    """Грубая оценка стоимости одного прогона задачи ($)."""
    from src.office import roles, costs
    cap = roles.capability_of(role)
    tin, tout = _TYPICAL_TOKENS.get(cap, _TYPICAL_TOKENS["text"])
    pin, pout = costs.price_for(model)
    return round((tin * pin + tout * pout) / 1_000_000, 4)


# ─────────────────── capability-гейт планирования ───────────────────

# Слова задачи → интеграция, которая должна быть подключена (детерминированно).
# website в списке нет: он без кредов и подключён всегда.
_TASK_CAPABILITY = [
    (("телеграм", "telegram", "бот", "bot"), "telegram", "токен Telegram-бота (@BotFather)"),
    (("письм", "email", "рассылк", "gmail"), "gmail", "подключение Gmail (OAuth в «Доступы»)"),
    (("таблиц", "sheets"), "google_sheets", "подключение Google Sheets (OAuth в «Доступы»)"),
    (("репозитор", "github", "git push"), "github", "GitHub (OAuth или PAT в «Доступы»)"),
    (("календар", "calendar"), "google_calendar", "подключение Google Calendar (OAuth)"),
]


def required_capability(task: dict) -> tuple[str, str] | None:
    """(имя интеграции, подсказка) для задачи — или None, если внешний доступ не нужен."""
    title = (task.get("title") or "").lower()
    for words, integration, hint in _TASK_CAPABILITY:
        if any(w in title for w in words):
            return integration, hint
    return None


def missing_for_plan() -> list[dict]:
    """Каких способностей не хватает под НЕвыполненные задачи плана.
    [{task_id, title, capability, hint}] — по одной записи на интеграцию."""
    from src.office import plan
    from src.integrations import registry as integrations_registry
    seen: set[str] = set()
    out: list[dict] = []
    for t in plan.all_tasks():
        if t.get("status") in ("done", "skipped"):  # снятая задача доступов не требует
            continue
        req = required_capability(t)
        if not req:
            continue
        name, hint = req
        if name in seen:
            continue
        integ = integrations_registry.get(name)
        if integ and not integrations_registry.is_connected(integ):
            seen.add(name)
            out.append({"task_id": t["id"], "title": t.get("title", "")[:80],
                        "capability": name, "hint": hint})
    return out
