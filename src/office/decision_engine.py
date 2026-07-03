"""
Decision Engine — решение как ТРАНЗАКЦИЯ над планом, а не прямая мутация (BOS §14 п.3).

Раньше interpret_directive/decide_company меняли план и оргструктуру напрямую, а
decisions.py был лишь журналом «Почему?». Теперь директива владельца выражается как
PlanDiff и проходит `propose → check → apply|reject`: Sandbox прогоняет
детерминированные проверки (бюджет, конфликт артефактов, вето Конституции) над
копией среза мира, и только прошедший diff применяется. Отклонённое решение
записывается с причиной — видно в /api/decisions.

PlanDiff = {
  add_tasks:    [{title, role, done_criterion}],
  milestone_ops:[{op, ...}],          # add|retitle|focus|note (как в interpret_directive)
  remove_tasks: [task_id],            # зарезервировано (директивы пока не порождают)
  dept_ops:     [{op, department}],   # зарезервировано
}

Sandbox — механизм (sandbox.py); Decision Engine — его первый потребитель. LLM даёт
только предложение (diff); вето выносят детерминированные проверки, не модель.
"""

from src.office import sandbox

_STEER_ROLES = ("developer", "designer", "integrator", "marketer", "salesman")

# Платные конструкторы, которые платформа не подключает без явного одобрения владельца
# (инвариант «реальный код, не платные конструкторы»). Раньше запрет жил только текстом
# в промпте CEO — LLM могла его проигнорировать; теперь это детерминированное вето.
_FORBIDDEN_CONSTRUCTORS = ("tilda", "тильда", "botsbox", "ботсбокс", "webflow", "wix",
                           "creatium", "platforma", "битрикс24", "bitrix")


# ── детерминированные проверки Sandbox ───────────────────────────────────────

def _budget_check(snapshot: dict, diff: dict) -> dict:
    """Вето, если суммарная оценка стоимости добавляемых задач выводит за бюджет
    (единая точка — costs.would_exceed, BOS §6). Оценка — по типовым токенам роли."""
    from src.office import execution_policy, costs, models
    est = 0.0
    for t in diff.get("add_tasks", []):
        role = (t.get("role") or "").strip()
        est += execution_policy.estimate_cost(role, models.get_default())
    if est > 0 and costs.would_exceed(est):
        return {"verdict": "veto",
                "reason": f"оценка стоимости решения ${est:.4f} выводит за бюджетный лимит"}
    return {"verdict": "pass", "reason": f"оценка ${est:.4f} в пределах бюджета"}


def _artifact_conflict_check(snapshot: dict, diff: dict) -> dict:
    """Вето, если решение добавляет site-задачу, пока другая site-задача в работе
    (мьютекс артефакта из Phase 2 — два агента затирают site/index.html). Читает
    ДЕКЛАРАЦИЮ артефактов, а не слова заголовка."""
    from src.office import plan
    busy = plan.site_task_in_progress()
    if not busy:
        return {"verdict": "pass", "reason": "конфликтов артефактов нет"}
    for t in diff.get("add_tasks", []):
        if "site" in plan.artifacts_of({"role": t.get("role", ""), "title": t.get("title", ""),
                                        "artifacts": t.get("artifacts")}):
            return {"verdict": "veto",
                    "reason": f"site-задача уже в работе ({busy}) — параллельная затрёт её; дождись завершения"}
    return {"verdict": "pass", "reason": "конфликтов артефактов нет"}


def _constitution_check(snapshot: dict, diff: dict) -> dict:
    """Вето Конституции: задача тянет платный конструктор без одобрения ИЛИ нарушает
    явное правило владельца (custom_rules «не …»). Раньше это жило только текстом в
    промпте (LLM могла проигнорировать) — теперь детерминированно."""
    from src.office import constitution
    custom = [r.lower() for r in (constitution.load().get("custom_rules") or [])]
    for t in diff.get("add_tasks", []):
        text = ((t.get("title") or "") + " " + (t.get("done_criterion") or "")).lower()
        for w in _FORBIDDEN_CONSTRUCTORS:
            if w in text:
                return {"verdict": "veto",
                        "reason": f"задача тянет платный конструктор «{w}» без одобрения владельца"}
        # Явный запрет владельца: правило вида «не BotsBox», «нельзя X» — если
        # запрещённое слово из правила встречается в задаче.
        for rule in custom:
            for neg in ("не ", "нельзя ", "без "):
                if neg in rule:
                    banned = rule.split(neg, 1)[1].strip().split()[:2]
                    for b in banned:
                        if len(b) > 3 and b in text:
                            return {"verdict": "veto",
                                    "reason": f"нарушает правило Конституции: «{rule[:80]}»"}
    return {"verdict": "pass", "reason": "правила Конституции соблюдены"}


_CHECKS = [_budget_check, _artifact_conflict_check, _constitution_check]


def check(diff: dict) -> dict:
    """Прогоняет diff через Sandbox над копией среза мира. {ok, checks, vetoed_by}."""
    from src.office import world
    return sandbox.run(world.snapshot(), diff, _CHECKS)


def _apply(diff: dict) -> list[str]:
    """Применяет прошедший проверки diff к реальному плану/вехам. Возвращает список
    человекочитаемых изменений (для ленты)."""
    from src.office import plan, milestones
    changes: list[str] = []
    for op in diff.get("milestone_ops", []):
        try:
            kind = (op.get("op") or "").strip()
            if kind == "add" and op.get("title"):
                milestones.insert_business_stage(op["title"], op.get("after"))
                changes.append(f"новый этап «{op['title'][:40]}»")
            elif kind == "retitle" and op.get("id") and op.get("title") and milestones.retitle(op["id"], op["title"]):
                changes.append(f"этап → «{op['title'][:40]}»")
            elif kind == "focus" and op.get("id"):
                milestones.mark_active(op["id"]); changes.append("сдвинут фокус этапов")
            elif kind == "note" and op.get("id") and op.get("text"):
                milestones.add_item(op["id"], op["text"], agent_id="orchestrator_1", role="orchestrator")
        except Exception:
            pass
    for t in diff.get("add_tasks", []):
        role = (t.get("role") or "").strip()
        title = (t.get("title") or "").strip()
        if role in _STEER_ROLES and title:
            plan.add_task(title, role, t.get("done_criterion", ""), requested_by="orchestrator_1")
            changes.append(f"задача «{title[:36]}» → {role}")
    return changes


def is_empty(diff: dict) -> bool:
    return not (diff.get("add_tasks") or diff.get("milestone_ops")
                or diff.get("remove_tasks") or diff.get("dept_ops"))


def decide(diff: dict, made_by: str = "orchestrator_1", thought: str = "",
           prompt_id: str = "") -> dict:
    """propose → check → apply|reject в одном вызове. Возвращает
    {decision_id, applied: bool, changes: [...], checks: [...], reason}.
    Пустой diff (question/smalltalk) решением не считается — ничего не пишет."""
    from src.office import decisions
    if is_empty(diff):
        return {"decision_id": "", "applied": False, "changes": [], "checks": [],
                "reason": "нет изменений"}

    verdict = check(diff)
    n_tasks = len(diff.get("add_tasks", []))
    n_ms = len(diff.get("milestone_ops", []))
    target = f"+{n_tasks} задач, {n_ms} правок этапов"

    if not verdict["ok"]:
        reason = "; ".join(r["reason"] for r in verdict["checks"] if r["verdict"] == "veto")
        did = decisions.record(
            action="directive", target=target, thought=thought,
            made_by=made_by, prompt_id=prompt_id, status="rejected",
            plan_diff=diff, checks=verdict["checks"], reject_reason=reason,
            expected_effect="решение отклонено проверками",
        )
        return {"decision_id": did, "applied": False, "changes": [],
                "checks": verdict["checks"], "reason": reason}

    changes = _apply(diff)
    did = decisions.record(
        action="directive", target=target, thought=thought,
        made_by=made_by, prompt_id=prompt_id, status="applied",
        plan_diff=diff, checks=verdict["checks"],
        expected_effect="; ".join(changes[:6]),
    )
    return {"decision_id": did, "applied": True, "changes": changes,
            "checks": verdict["checks"], "reason": ""}
