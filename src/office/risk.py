"""
Risk — офис сам оценивает риск действия постфактум, не провайдер и не платформа
(docs/product-portrait-2026-07-19.md §5a/§16 п.1).

Оценка риска — Fact с provenance (docs/ai-office-canonical-spec.md §4.2), не
статическое число у Capability: изначально `inferred` (грубая эвристика по
видимости/необратимости типа действия — та же ось, что уже неявно кодирует
`autonomy._ACTION_MIN_LEVEL`), после реального исхода — `outcome` с пересчитанным
confidence. Это Outcome Learning (каноническая спека §6.5), применённый к риску
той же петлёй, что уже есть у знаний в `knowledge.py` — не отдельный механизм.

  record_outcome(action_type, ok, note)  — зафиксировать реальный исход действия
  level_for(action_type)                 — текущая оценка {level, confidence, source, reasons}
  escalated(action_type)                 — риск поднялся выше базовой гипотезы —
                                            `autonomy.needs_approval` подмешивает это
                                            ПОВЕРХ статической таблицы, не вместо неё
  severe_failure(action_type)            — провал именно там, где база уже "high"
                                            (publish_site/push_code) — триггер для
                                            автоматического отката уровня автономии
                                            (портрет §13, симметрично autonomy.upgrade())

Хранилище: data/tenants/<tid>/risk.json — {action_type: {fails, successes, notes}}.
"""

import time

from src.saas import context as ctx

_FILE = "risk.json"

# Базовая (inferred) гипотеза риска по типу действия — та же ось видимость×
# необратимость, что уже неявно есть в autonomy._ACTION_MIN_LEVEL (более строгий
# порог требуемого уровня доверия ⇒ выше базовый риск). СТАРТОВАЯ точка обучения,
# не финальное решение: конкретный провайдер/канал может эскалировать выше по
# реальным исходам, база не переписывается вручную.
_BASE_LEVEL = {
    "publish_site": "high",
    "push_code": "high",
    "launch_bot": "medium",
    "create_repo": "medium",
    "send_message": "medium",
    "use_integration": "low",
}
_DEFAULT_BASE = "low"
_LEVELS = ("low", "medium", "high")


def _load() -> dict:
    return ctx.read_json(_FILE, {})


def _save(d: dict) -> None:
    ctx.write_json(_FILE, d)


def record_outcome(action_type: str, ok: bool, note: str = "") -> None:
    """Зафиксировать реальный исход действия этого типа. Учится сам, не спрашивая —
    успех/провал видно по факту вызова (integration_tool_handlers._execute_integration)."""
    if not action_type:
        return
    d = _load()
    entry = d.setdefault(action_type, {"fails": 0, "successes": 0, "notes": []})
    if ok:
        entry["successes"] = entry.get("successes", 0) + 1
    else:
        entry["fails"] = entry.get("fails", 0) + 1
        if note:
            notes = entry.setdefault("notes", [])
            notes.append({"text": note[:200], "ts": round(time.time(), 3)})
            entry["notes"] = notes[-5:]
    _save(d)


def level_for(action_type: str) -> dict:
    """Текущая оценка риска действия: {level, confidence, source, reasons}.
    Без реальных провалов — inferred-гипотеза с низким confidence (0.3, та же
    отметка, что knowledge.SOURCES["inferred"]). Хотя бы один реальный провал —
    эскалация на ступень, source=outcome, confidence растёт с числом провалов."""
    entry = _load().get(action_type) or {}
    base = _BASE_LEVEL.get(action_type, _DEFAULT_BASE)
    fails = entry.get("fails", 0)
    if fails == 0:
        return {"level": base, "confidence": 0.3, "source": "inferred", "reasons": []}
    idx = min(_LEVELS.index(base) + 1, len(_LEVELS) - 1)
    conf = min(0.9, 0.5 + 0.1 * fails)
    reasons = [n["text"] for n in entry.get("notes", [])[-3:]]
    return {"level": _LEVELS[idx], "confidence": round(conf, 2), "source": "outcome",
            "reasons": reasons}


def escalated(action_type: str) -> bool:
    """True если обучение подняло риск действия выше базовой гипотезы —
    `autonomy.needs_approval` требует подтверждения ДАЖЕ на высоком уровне
    доверия/после разового одобрения, пока риск не переоценят вручную."""
    r = level_for(action_type)
    return r["source"] == "outcome" and r["level"] != _BASE_LEVEL.get(action_type, _DEFAULT_BASE)


def severe_failure(action_type: str) -> bool:
    """Провал именно на действии, чья БАЗОВАЯ гипотеза уже "high" (publish_site/
    push_code — самые видимые и малообратимые) — портрет §13: «серьёзная видимая
    ошибка» откатывает уровень автономии автоматически, не только внутренний trust."""
    entry = _load().get(action_type) or {}
    return _BASE_LEVEL.get(action_type) == "high" and entry.get("fails", 0) > 0


def reset() -> None:
    ctx.delete_file(_FILE)
