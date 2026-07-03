"""
История решений CEO — структурированный лог с объяснениями.

Каждое важное решение сохраняется вместе с:
- вариантами, которые рассматривались
- уровнем уверенности
- рисками
- ожидаемым эффектом
- данными, которые использовались

После завершения задачи — обновляется фактический результат.
Используется для: UI «Почему?», аудита, обучения системы.
"""

import time
import uuid
from src.saas import context as ctx

_MAX = 200  # максимум записей


def _load() -> list:
    return ctx.read_json("decisions", None) or []


def _save(items: list) -> None:
    ctx.write_json("decisions", items[-_MAX:])


def record(
    action: str,
    target: str = "",
    thought: str = "",
    alternatives: list | None = None,
    confidence: int = 50,
    risks: list | None = None,
    expected_effect: str = "",
    data_used: list | None = None,
    made_by: str = "orchestrator_1",
    prompt_id: str = "",
    status: str = "applied",
    plan_diff: dict | None = None,
    checks: list | None = None,
    reject_reason: str = "",
) -> str:
    """Сохранить решение CEO. Возвращает id записи. `prompt_id` — ссылка на
    промпт (prompt_builder.log_prompt), породивший решение: по нему Observability
    строит цепочку промпт → решение → исполнение → diff мира.

    Поля решения-как-транзакции (BOS §14 п.3, Phase 5): `status` (applied|rejected),
    `plan_diff` (предложенный diff плана/мира), `checks` (вердикты Sandbox-проверок),
    `reject_reason` (почему отклонено) — отклонённое решение видно в /api/decisions."""
    did = f"d_{uuid.uuid4().hex[:8]}"
    items = _load()
    items.append({
        "id": did,
        "ts": time.time(),
        "made_by": made_by,
        "action": action,
        "target": target,
        "thought": thought,
        "alternatives": alternatives or [],
        "confidence": confidence,
        "risks": risks or [],
        "expected_effect": expected_effect,
        "data_used": data_used or [],
        "prompt_id": prompt_id or "",
        "snapshot_id": "",     # ставится world.save_snapshot после применения решения
        "status": status,      # applied | rejected (решение-транзакция)
        "plan_diff": plan_diff or {},
        "checks": checks or [],
        "reject_reason": (reject_reason or "")[:300],
        "confirmed_by": None,  # "user" | "auto" — кем подтверждено
        "result": None,
        "result_ts": None,
    })
    _save(items)
    return did


def get(did: str) -> dict | None:
    """Запись решения по id (или None)."""
    for item in _load():
        if item.get("id") == did:
            return item
    return None


def set_snapshot(did: str, snapshot_id: str) -> None:
    """Привязать к решению id среза мира, зафиксированного ПОСЛЕ его применения —
    Observability берёт этот срез и предыдущий, чтобы показать world.diff решения."""
    items = _load()
    for item in items:
        if item.get("id") == did:
            item["snapshot_id"] = snapshot_id
            break
    _save(items)


def set_result(did: str, result: str, confirmed_by: str = "auto") -> None:
    """Обновить результат решения после завершения задачи."""
    items = _load()
    for item in items:
        if item["id"] == did:
            item["result"] = result
            item["result_ts"] = time.time()
            if not item.get("confirmed_by"):
                item["confirmed_by"] = confirmed_by
            break
    _save(items)


def confirm(did: str) -> None:
    """Пользователь явно одобрил действие."""
    items = _load()
    for item in items:
        if item["id"] == did:
            item["confirmed_by"] = "user"
            break
    _save(items)


def recent(n: int = 20) -> list:
    items = _load()
    return list(reversed(items[-n:]))


def payload() -> dict:
    items = recent(30)
    return {"decisions": items, "total": len(_load())}

