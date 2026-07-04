"""
Org Graph — узлы и рёбра для вкладки «Сценарии»: оргструктура + живой поток
работы (см. docs/scenario-graph-tab-spec.md). Агрегирующая проекция уже
существующего состояния (org/registry/plan) — не новая модель данных, ровно
как world.snapshot() агрегирует world model для других целей.

НЕ дублирует план-граф задач (вкладка «Проект» уже показывает его линейно с
зависимостями) — здесь узлы это компания → отделы → сотрудники, каждый
сотрудник несёт СВОЮ текущую задачу, если она есть.
"""

from src.office import org, registry, plan, state


def _agent_node(a) -> dict:
    task_id = ""
    task_title = ""
    todo = plan.for_agent(a.agent_id)
    if todo:
        task_id, task_title = todo[0]["id"], todo[0].get("title", "")
    return {
        "id": f"agent:{a.agent_id}",
        "type": "agent",
        "agent_id": a.agent_id,
        "role": a.role,
        "label": a.agent_id,
        "status": "paused" if a.paused else a.status,
        "task_id": task_id,
        "task_title": task_title,
        "last_message": a.last_message,
    }


def build() -> dict:
    """Собирает {nodes, edges} для GET /api/org-graph."""
    nodes: list[dict] = []
    edges: list[dict] = []

    all_agents = registry.all_agents()
    ceo = next((a for a in all_agents if a.role == "orchestrator"), None)
    ceo_id = "ceo"
    nodes.append({
        "id": ceo_id, "type": "ceo",
        "agent_id": ceo.agent_id if ceo else "",
        "label": ceo.agent_id if ceo else "orchestrator",
        # CEO ещё не нанят (самое начало bootstrap) — status "hiring", НЕ "idle":
        # иначе фронт предлагает write-действия (пауза/чат) для agent_id, которого
        # не существует в registry ("" пустая строка → /api/agent//pause).
        "status": ceo.status if ceo else "hiring",
    })

    # Штаб CEO (researcher/strategist/architect/hr) — не отдел, подчиняются CEO напрямую.
    staff_roles = {"researcher", "strategist", "architect", "hr"}
    for a in all_agents:
        if a.role in staff_roles:
            node = _agent_node(a)
            nodes.append(node)
            edges.append({"from": ceo_id, "to": node["id"], "kind": "manages"})

    for dept_id, meta in org.catalog().items():
        dept_state = org.state_of(dept_id)
        is_open = dept_state.get("status") == "open"
        dept_node_id = f"dept:{dept_id}"
        nodes.append({
            "id": dept_node_id, "type": "department",
            "label": meta["name"], "status": "open" if is_open else "closed",
            "objective": dept_state.get("objective", ""),
        })
        edges.append({"from": ceo_id, "to": dept_node_id, "kind": "manages"})

        lead_id = org.lead_id(dept_id)
        for a in registry.members_of(dept_id):
            node = _agent_node(a)
            if a.agent_id == lead_id:
                node["type"] = "leader"
            nodes.append(node)
            edges.append({"from": dept_node_id, "to": node["id"], "kind": "member"})

    return {"nodes": nodes, "edges": edges}
