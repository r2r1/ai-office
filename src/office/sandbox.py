"""
Sandbox — универсальный механизм «clone → check → merge/discard» (BOS §9).

НЕ фича Decision и НЕ отдельная сущность под каждый случай (engineering-principles
§7): один интерфейс над ЛЮБЫМ предметом (решение, стратегия, цены, бюджет, найм).
Sandbox сам НЕ применяет изменение к реальному миру — он клонирует срез предмета,
прогоняет детерминированные проверки над (клон, изменение) и выносит вердикт;
merge (применить) или discard (отклонить) решает вызывающий по результату.

  run(subject, change, checks) -> {ok, checks, vetoed_by}

Проверка (check) — callable(subject, change) -> {name, verdict, reason}:
  verdict ∈ 'pass' | 'warn' | 'veto'. Вето дают ТОЛЬКО детерминированные проверки;
  LLM-чекер, если появится, помечает свой вердикт как оценку и не имеет права вето.

Первый потребитель — Decision Engine (decision_engine.py), но механизм от него не
зависит: Sandbox Company (клон тенанта) подключит тот же run(), когда появится
конкретный потребитель (A/B стратегии, разработка скилла) — не строим ради полноты.
"""

from typing import Callable


def run(subject, change, checks: list[Callable]) -> dict:
    """Прогоняет проверки над (клон предмета, предлагаемое изменение). subject —
    неизменяемый срез (напр. world.snapshot()); change — предлагаемый diff. Возвращает
    вердикт без применения к реальному миру."""
    results: list[dict] = []
    for chk in checks:
        name = getattr(chk, "__name__", "check")
        try:
            r = chk(subject, change) or {}
        except Exception as e:  # проверка не должна ронять решение — фиксируем и идём
            r = {"name": name, "verdict": "pass", "reason": f"проверка пропущена: {e}"}
        r.setdefault("name", name)
        r.setdefault("verdict", "pass")
        r.setdefault("reason", "")
        results.append(r)
    vetoed = [r for r in results if r["verdict"] == "veto"]
    return {"ok": not vetoed, "checks": results,
            "vetoed_by": [r["name"] for r in vetoed]}
