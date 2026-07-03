"""
Observability — единая временная шкала жизни офиса (см. docs/дорожная_карта.md Phase 0.5).

Не создаёт логирование с нуля: сшивает уже существующие журналы (trace.jsonl,
prompts.jsonl, decisions, world_snapshots.jsonl) в одну шкалу с перекрёстными
ссылками. Диагностика инцидента (реальный кейс — зависание на ресёрчере) делалась
именно через trace — наблюдаемость и есть первичный инструмент отладки, и без неё
дальнейшая миграция ядра идёт вслепую.

  timeline(since, until)  — все записи четырёх источников, слитые по времени
  decision_chain(did)     — полная цепочка ОДНОГО решения: промпт, его вызвавший →
                            trace-записи исполнения → world.diff «до/после»

Идентификаторы связи: prompt_id (prompt_builder.log_prompt) и snapshot_id
(world.save_snapshot) кладутся в запись Decision (decisions.record/set_snapshot).
Где явной ссылки ещё нет (worker-промпты, CEO до Phase 1) — сшивка по времени.
"""

import time

from src.office import trace, decisions, prompt_builder, world

# Окно, в котором trace-записи считаются относящимися к решению, если явной
# ссылки (decision_id/prompt_id) в них нет — соседние по времени события цикла.
_DECISION_WINDOW_SECS = 45.0


def _prompt_for_decision(dec: dict) -> dict | None:
    """Промпт, породивший решение: по явному prompt_id, иначе — ближайший промпт
    того же автора ПЕРЕД временем решения (сшивка по времени, пока Phase 1 не
    начнёт логировать CEO-промпт с явным prompt_id)."""
    pid = dec.get("prompt_id") or ""
    if pid:
        p = prompt_builder.prompt_by_id(pid)
        if p:
            return p
    made_by = dec.get("made_by", "")
    ts = dec.get("ts", 0)
    best = None
    for p in prompt_builder.recent_prompts(100):
        if p.get("agent") != made_by:
            continue
        pt = p.get("t", 0)
        if pt <= ts and (best is None or pt > best.get("t", 0)):
            best = p
    return best


def _trace_for_decision(dec: dict) -> list[dict]:
    """Trace-записи исполнения решения: явно помеченные decision_id/prompt_id либо
    попавшие в временное окно вокруг момента решения."""
    ts = dec.get("ts", 0)
    did = dec.get("id", "")
    pid = dec.get("prompt_id") or ""
    out = []
    for e in trace.tail(1000):
        et = e.get("t", 0)
        if e.get("decision_id") == did or (pid and e.get("prompt_id") == pid):
            out.append(e)
        elif abs(et - ts) <= _DECISION_WINDOW_SECS:
            out.append(e)
    return out


def decision_chain(did: str) -> dict:
    """Полная цепочка одного решения (Phase 0.5 DoD): само решение → промпт,
    который его вызвал → trace-записи исполнения → world.diff до/после."""
    dec = decisions.get(did)
    if not dec:
        return {"error": "decision_not_found", "id": did}

    prompt = _prompt_for_decision(dec)
    tr = _trace_for_decision(dec)

    world_diff = None
    sid = dec.get("snapshot_id") or ""
    if sid:
        after = world.snapshot_by_id(sid)
        before = world.snapshot_before(sid)
        if after and before:
            world_diff = world.diff(before, after)
        elif after:
            world_diff = {"note": "нет предыдущего среза для сравнения"}

    return {
        "decision": dec,
        "prompt": prompt,          # полная запись (system+task) или None
        "trace": tr,               # записи исполнения
        "world_diff": world_diff,  # что решение изменило в мире (или None)
    }


def timeline(since: float | None = None, until: float | None = None,
             limit: int = 400) -> list[dict]:
    """Слитая по времени шкала четырёх источников. Каждая запись — {t, ts, source,
    kind, ...}. source ∈ {trace, prompt, decision, snapshot}. Сортировка по t."""
    until = until if until is not None else time.time()
    since = since if since is not None else (until - 3600)  # по умолчанию последний час
    items: list[dict] = []

    for e in trace.tail(2000):
        t = e.get("t", 0)
        if since <= t <= until:
            items.append({"source": "trace", "t": t, "ts": e.get("ts", ""),
                          "kind": e.get("kind", ""),
                          "detail": {k: v for k, v in e.items()
                                     if k not in ("t", "ts", "kind")}})

    for p in prompt_builder.recent_prompts(200):
        t = p.get("t", 0)
        if since <= t <= until:
            items.append({"source": "prompt", "t": t, "ts": p.get("ts", ""),
                          "kind": "prompt", "id": p.get("id", ""),
                          "agent": p.get("agent", ""), "role": p.get("role", ""),
                          "system_chars": p.get("system_chars", 0),
                          "task_chars": p.get("task_chars", 0)})

    for d in decisions.recent(200):
        t = d.get("ts", 0)
        if since <= t <= until:
            items.append({"source": "decision", "t": t, "kind": d.get("action", ""),
                          "id": d.get("id", ""), "made_by": d.get("made_by", ""),
                          "thought": d.get("thought", ""),
                          "confidence": d.get("confidence", 0),
                          "prompt_id": d.get("prompt_id", ""),
                          "snapshot_id": d.get("snapshot_id", "")})

    for s in world.snapshots_between(since, until):
        items.append({"source": "snapshot", "t": s.get("ts", 0),
                      "kind": "snapshot", "id": s.get("snapshot_id", ""),
                      "reason": s.get("reason", ""), "at": s.get("at", "")})

    items.sort(key=lambda x: x.get("t", 0))
    return items[-limit:]
