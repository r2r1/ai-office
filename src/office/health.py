"""
Health Score — операционное здоровье компании по отделам.

Даёт пользователю реальные метрики (не «понимание»):
  Tech: 88 🟢  Marketing: 63 🟡  Sales: 91 🟢

Считается на лету из существующих данных (plan, registry, trust, events).
Не требует отдельного хранилища.
"""

import time
from src.saas import context as ctx


def _status(score: int) -> str:
    if score >= 75:
        return "🟢"
    if score >= 45:
        return "🟡"
    return "🔴"


def _dept_score(dept_id: str) -> dict:
    from src.office import plan as plan_mod
    from src.office import registry as reg_mod
    from src.office import org as org_mod
    from src.office import trust as trust_mod
    from src.office import events as events_mod

    board = plan_mod.board(dept_id)
    todo = len(board.get("todo") or [])
    doing = len(board.get("doing") or [])
    done = len(board.get("done") or [])
    total = todo + doing + done

    done_rate = done / max(total, 1)

    # Зависшие агенты отдела
    member_roles = org_mod.member_roles(dept_id) + [org_mod.lead_role(dept_id)]
    agents = [a for a in reg_mod.all_agents() if a.role in member_roles]
    now = time.time()
    stuck = sum(
        1 for a in agents
        if a.status == "thinking"
        and (now - (a.last_run or now)) > 240  # > 4 мин
    )
    agent_count = max(len(agents), 1)

    dept_trust = trust_mod.get_score(dept_id)

    # Нерешённые события типа blocker из этого отдела
    blockers = sum(
        1 for e in events_mod.recent(20)
        if e.get("kind") == "blocker" and not e.get("processed")
        and org_mod.department_of_role(e.get("from_role", "")) == dept_id
    )

    score = int(
        done_rate * 40
        + dept_trust * 0.35
        + (1 - stuck / agent_count) * 15
        + max(0, 10 - blockers * 5)
    )
    score = max(0, min(100, score))

    issues = []
    if stuck > 0:
        issues.append(f"{stuck} агент(а) завис(ли)")
    if blockers > 0:
        issues.append(f"{blockers} блокер(а) без решения")
    if done_rate < 0.3 and total > 0:
        issues.append("мало завершённых задач")

    return {
        "score": score,
        "status": _status(score),
        "done_rate": round(done_rate, 2),
        "stuck_agents": stuck,
        "trust": dept_trust,
        "tasks": {"todo": todo, "doing": doing, "done": done},
        "issues": issues,
    }


def payload() -> dict:
    from src.office import org as org_mod
    from src.office import trust as trust_mod
    from src.office import events as events_mod

    open_depts = org_mod.open_departments()
    dept_scores: dict[str, dict] = {}
    for dept in ["tech", "marketing", "sales"]:
        if dept in open_depts:
            dept_scores[dept] = _dept_score(dept)

    all_scores = [v["score"] for v in dept_scores.values()]
    company = int(sum(all_scores) / max(len(all_scores), 1)) if all_scores else trust_mod.get_score()

    # Активные риски
    risks = []
    for dept, ds in dept_scores.items():
        for issue in ds.get("issues") or []:
            risks.append(f"{dept}: {issue}")

    # Краткий вердикт
    if not dept_scores:
        summary = "Офис ещё не развернул отделы."
    elif company >= 75:
        summary = "Компания работает стабильно."
    elif company >= 45:
        dept_warn = [d for d, v in dept_scores.items() if v["score"] < 60]
        summary = f"Требует внимания: {', '.join(dept_warn)}." if dept_warn else "Есть небольшие отклонения."
    else:
        summary = "Компания испытывает трудности — нужно вмешательство."

    if risks:
        summary += " Риски: " + "; ".join(risks[:3]) + "."

    return {
        "company": company,
        "status": _status(company),
        "departments": dept_scores,
        "risks": risks,
        "summary": summary,
    }
