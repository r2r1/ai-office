"""
World Model v1 — единый срез мира компании (см. docs/bos-architecture.md §4).

SSOT-агрегатор: НЕ хранит собственных данных — читает модули-источники истины
(brief, objectives, philosophy/constitution как DNA, plan, costs, sites, leads,
events, autonomy, trust) и собирает из них ОДИН копируемый, сравнимый снапшот.
Правило BOS: никто ничего не «знает» — все читают мир; промпту нужен факт,
которого здесь нет, — это дырка в модели мира, а не повод дописать шаблон.

  snapshot()      — полный срез (JSON-serializable, детерминированные ключи)
  diff(a, b)      — что изменилось между двумя снапшотами (плоские пути)
  save_snapshot() — зафиксировать срез в журнал (для Measurement/Sandbox)
  context_block() — компактный блок «ГДЕ КОМПАНИЯ СЕЙЧАС» для промпта CEO

Snapshot+diff — фундамент обоих Sandbox-механизмов (BOS §9): решение проверяется
на копии среза, merge — это применение diff.
"""

import json
import time
import uuid
from datetime import datetime

from src.saas import context as ctx

_SNAP_FILE = "world_snapshots.jsonl"
_KEEP_SNAPSHOTS = 100


# ─────────────────────────── снапшот ───────────────────────────

def snapshot() -> dict:
    """Полный срез мира текущего тенанта. Только чтение источников истины."""
    from src.office import (brief, objectives, philosophy, constitution, plan,
                            costs, sites, leads, events, autonomy, trust, org,
                            registry, questions, projects, metrics)

    b = brief.get()
    phil = philosophy.load()
    const = constitution.payload()

    # Business State: измеримое «сейчас» (BOS §4)
    plan_prog = plan.progress() if plan.is_generated() else {"total": 0, "done": 0, "percent": 0}
    doing = [t for t in plan.all_tasks() if t.get("status") == "in_progress"]
    blockers = [e for e in events.pending() if e.get("kind") == "blocker"]
    open_qs = questions.list_pending()
    totals = costs.totals()
    lim = costs.limits()

    return {
        "ts": round(time.time(), 3),
        "tenant": ctx.get_tenant(),
        # Identity (DNA v1 = философия + конституция; отдельная сущность DNA — след. шаг)
        "identity": {
            "mission": phil.get("mission", ""),
            "success_means": phil.get("success_means", ""),
            "never_sacrifice": phil.get("never_sacrifice", ""),
            "growth_style": phil.get("growth_style", ""),
            "risk_appetite": phil.get("risk_appetite", ""),
            "custom_rules": const.get("custom_rules", []),
        },
        # Brief: что за бизнес и чего хочет от офиса
        "brief": {
            "niche": b.get("niche", ""),
            "audience": b.get("audience", ""),
            "goal": b.get("goal", ""),
            "summary": b.get("summary", ""),
        },
        # Measurement (BOS §4): числа о бизнесе, каждое с источником факт|оценка.
        # ts у метрик снимаем — у снапшота свой ts; иначе world.diff() считал бы
        # метрики «изменёнными» на каждом срезе (шум в decision_chain).
        "metrics": [{k: v for k, v in m.items() if k != "ts"} for m in metrics.current()],
        # Objectives: desired state
        "objectives": [
            {"id": o["id"], "title": o["title"], "desired": o.get("desired", ""),
             "measured_by": o.get("measured_by", ""), "current_value": o.get("current_value", ""),
             "priority": o.get("priority", 50), "status": o.get("status", "active")}
            for o in objectives.all_objectives()
        ],
        # Projects: активный + история (что каждый оставил после себя)
        "projects": [
            {"id": p["id"], "title": p["title"], "status": p.get("status", ""),
             "left_behind": p.get("left_behind") or {}}
            for p in projects.all_projects()
        ],
        # Business State: текущее измеримое состояние
        "business_state": {
            "plan": plan_prog,
            "tasks_in_progress": [{"id": t["id"], "role": t.get("role", ""),
                                   "title": t.get("title", "")[:80]} for t in doing],
            "blockers": [{"id": e["id"], "summary": e.get("summary", "")} for e in blockers],
            "open_questions": len(open_qs),
            "sites": [{"slug": s.get("slug", ""), "revision": s.get("revision", 1)}
                      for s in sites.all_sites()],
            "leads_count": leads.count(),
            "spend_usd": totals.get("cost", 0.0),
            "budget_limit_usd": lim.get("total_usd", 0.0),
            "autonomy_level": autonomy.get_level(),
            "trust_score": trust.get_score(),
            "open_departments": org.open_departments(),
            "team_size": len(registry.all_agents()),
        },
    }


# ─────────────────────────── diff ───────────────────────────

def _flatten(obj, prefix: str = "") -> dict:
    """Снапшот → плоский словарь путей (для сравнения). Списки — по индексу/ид."""
    out: dict = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(_flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            key = v.get("id", i) if isinstance(v, dict) else i
            out.update(_flatten(v, f"{prefix}[{key}]"))
    else:
        out[prefix] = obj
    return out


def diff(a: dict, b: dict) -> dict:
    """Что изменилось между снапшотами a → b (ts/tenant не сравниваем).
    Возвращает {added: {path: new}, removed: {path: old}, changed: {path: [old, new]}}."""
    fa = {k: v for k, v in _flatten(a).items() if not k.startswith(("ts", "tenant"))}
    fb = {k: v for k, v in _flatten(b).items() if not k.startswith(("ts", "tenant"))}
    added = {k: fb[k] for k in fb.keys() - fa.keys()}
    removed = {k: fa[k] for k in fa.keys() - fb.keys()}
    changed = {k: [fa[k], fb[k]] for k in fa.keys() & fb.keys() if fa[k] != fb[k]}
    return {"added": added, "removed": removed, "changed": changed,
            "empty": not (added or removed or changed)}


# ─────────────────────────── журнал срезов ───────────────────────────

def save_snapshot(reason: str = "") -> dict:
    """Фиксирует текущий срез мира в журнал (Measurement-петля будет читать его).
    В снапшот проставляется `snapshot_id` — по нему Observability связывает срез
    с решением (decisions.set_snapshot) и считает world.diff «до/после»."""
    snap = snapshot()
    sid = f"s_{uuid.uuid4().hex[:8]}"
    snap["snapshot_id"] = sid
    try:
        p = ctx.tenant_dir() / _SNAP_FILE
        entry = {"snapshot_id": sid, "reason": reason,
                 "at": datetime.now().isoformat(timespec="seconds"), **snap}
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        lines = p.read_text(encoding="utf-8").splitlines()
        if len(lines) > _KEEP_SNAPSHOTS:
            p.write_text("\n".join(lines[-_KEEP_SNAPSHOTS:]) + "\n", encoding="utf-8")
    except Exception:
        pass  # журнал срезов не должен ронять офис
    return snap


def _read_snapshots() -> list[dict]:
    """Весь журнал срезов (по возрастанию времени)."""
    out: list[dict] = []
    try:
        p = ctx.tenant_dir() / _SNAP_FILE
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


def snapshot_by_id(sid: str) -> dict | None:
    if not sid:
        return None
    for s in reversed(_read_snapshots()):
        if s.get("snapshot_id") == sid:
            return s
    return None


def snapshot_before(target_sid: str) -> dict | None:
    """Срез, зафиксированный непосредственно ПЕРЕД срезом target_sid (или None) —
    вторая сторона diff «что изменилось при этом решении»."""
    snaps = _read_snapshots()
    for i, s in enumerate(snaps):
        if s.get("snapshot_id") == target_sid:
            return snaps[i - 1] if i > 0 else None
    return None


def snapshots_between(t0: float, t1: float) -> list[dict]:
    """Срезы, попавшие во временное окно [t0, t1] (для таймлайна)."""
    return [s for s in _read_snapshots() if t0 <= s.get("ts", 0) <= t1]


def last_snapshot() -> dict | None:
    """Последний зафиксированный срез (или None)."""
    snaps = _read_snapshots()
    return snaps[-1] if snaps else None


# ─────────────────────────── проекция в промпт ───────────────────────────

def context_block() -> str:
    """Компактный «ГДЕ КОМПАНИЯ СЕЙЧАС» для промпта CEO — единственный сериализатор
    Business State в промпт (собирается Prompt Builder'ом)."""
    from src.office import objectives
    s = snapshot()
    bs = s["business_state"]
    lines = [
        f"План: {bs['plan']['done']}/{bs['plan']['total']} задач ({bs['plan']['percent']}%)",
        f"В работе: " + ("; ".join(f"{t['id']}({t['role']})" for t in bs["tasks_in_progress"]) or "—"),
        f"Сайты: {len(bs['sites'])}, лиды: {bs['leads_count']}",
        f"Расход: ${bs['spend_usd']:.2f}" + (f" из ${bs['budget_limit_usd']:.2f}" if bs['budget_limit_usd'] else ""),
        f"Отделы открыты: {', '.join(bs['open_departments']) or 'нет'}; команда: {bs['team_size']}",
        f"Автономия: {bs['autonomy_level']}, доверие: {bs['trust_score']}",
    ]
    if bs["blockers"]:
        lines.append("⛔ Блокеры: " + "; ".join(e["summary"][:60] for e in bs["blockers"]))
    if bs["open_questions"]:
        lines.append(f"Открытых вопросов клиенту: {bs['open_questions']}")
    from src.office import projects, gap
    block = ("\n=== ГДЕ КОМПАНИЯ СЕЙЧАС (Business State) ===\n" + "\n".join(f"- {l}" for l in lines) + "\n")
    # Разрывы до целей — CEO видит их наравне с блокерами (Gap Analysis, Phase 4).
    return block + projects.context_block() + objectives.context_block() + gap.context_block()


def reset() -> None:
    try:
        ctx.delete_file(_SNAP_FILE)
    except Exception:
        pass
