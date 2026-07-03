"""
Measurement Layer v1 — числа о бизнесе (см. docs/дорожная_карта.md Phase 3, BOS §3/§4).

Без Measurement измерительный полукруг кибернетического цикла (Metrics → Gap →
Priorities → replan) нечем питать — половина BOS заблокирована этим компонентом.
Здесь минимум: фактические метрики (лиды) и прокси-оценки (выручка = лиды × чек),
КАЖДАЯ помечена источником (`факт` | `оценка`) — решение на оценке не имеет права
выглядеть так же уверенно, как на факте (engineering-principles §9).

  current()   — текущие показания (чистое чтение источников: leads + brief)
  collect()   — зафиксировать текущие показания в журнал (тренд во времени)
  series(id)  — история одной метрики

Хранилище: data/tenants/<tid>/metrics.json — {"points": [...]} (append + потолок).
Точка правды по значениям — источники (leads/brief); журнал нужен для тренда/Gap.
"""

import time

from src.saas import context as ctx

_FILE = "metrics.json"
_MAX_POINTS = 2000

FACT = "факт"
ESTIMATE = "оценка"


def current() -> list[dict]:
    """Текущие показания метрик — ЧИСТОЕ ЧТЕНИЕ (leads + типизированный brief).
    Прокси-выручка появляется только когда известен средний чек (иначе оценки нет)."""
    from src.office import leads, brief
    now = round(time.time(), 3)
    total = leads.count()
    week = leads.count_last_days(7)
    out = [
        {"metric_id": "leads_total", "label": "Заявок всего", "value": total,
         "source": FACT, "unit": "шт", "ts": now},
        {"metric_id": "leads_7d", "label": "Заявок за 7 дней", "value": week,
         "source": FACT, "unit": "шт", "ts": now},
    ]
    check = brief.avg_check()
    if check:
        out.append({
            "metric_id": "revenue_proxy_7d", "label": "Прокси-выручка за 7 дней",
            "value": round(week * check, 2), "source": ESTIMATE, "unit": "деньги",
            "ts": now, "basis": f"{week} заявок × {check} чек"})
    return out


def _load() -> dict:
    return ctx.read_json(_FILE, {"points": []})


def record(metric_id: str, value, source: str, label: str = "",
           artifact_id: str = "", unit: str = "") -> dict:
    """Записать одно показание метрики в журнал (для тренда/Gap). source обязателен."""
    d = _load()
    pts = d.get("points", [])
    point = {"metric_id": metric_id, "value": value, "source": source,
             "label": label, "artifact_id": artifact_id, "unit": unit,
             "ts": round(time.time(), 3)}
    pts.append(point)
    if len(pts) > _MAX_POINTS:
        del pts[: len(pts) - _MAX_POINTS]
    d["points"] = pts
    ctx.write_json(_FILE, d)
    return point


def collect() -> list[dict]:
    """Зафиксировать текущие показания в журнал (снимок во времени для тренда).
    Вызывается офисом периодически / при событиях (публикация, новый лид)."""
    recorded = []
    for r in current():
        recorded.append(record(r["metric_id"], r["value"], r["source"],
                               label=r.get("label", ""), unit=r.get("unit", "")))
    return recorded


def series(metric_id: str, since: float | None = None) -> list[dict]:
    """История одной метрики (по возрастанию времени), опционально с момента since."""
    pts = [p for p in _load().get("points", []) if p.get("metric_id") == metric_id]
    if since is not None:
        pts = [p for p in pts if p.get("ts", 0) >= since]
    return pts


def latest(metric_id: str):
    """Последнее значение метрики из текущих показаний (или None)."""
    for r in current():
        if r["metric_id"] == metric_id:
            return r["value"]
    return None


def reset() -> None:
    ctx.delete_file(_FILE)
