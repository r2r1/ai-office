"""
Бизнес-дашборд — вкладка "Бизнес" (в отличие от "Офис": не ход работы агентов,
а цифры о самом бизнесе клиента). Без интеграций (CRM/ERP) реальных источников
мало — этот модуль сознательно НЕ рисует KPI-заглушки, а показывает только то,
что РЕАЛЬНО измеримо сейчас (лиды, прокси-выручка от среднего чека, расход на
ИИ), и честно называет источник (факт|оценка) — тот же принцип, что уже
проведён в metrics.py/gap.py (BOS §4 Measurement).

Два слоя виджетов:
  системные (`system_widgets`) — пересчитываются на каждый запрос из живых
      источников, НЕ хранятся на диске: появляются/пропадают сами по мере
      того, что стало/перестало быть измеримым (например прокси-выручка
      пропадает, если из брифа исчез средний чек) — не могут "протухнуть".
  кастомные (`custom_widgets`) — созданные по свободному запросу клиента
      ("построй график выручки по месяцам") через orchestrator.
      interpret_dashboard_request(): ответ LLM НЕ выполняется напрямую,
      только выбирает metric_id/chart_type/group_by из whitelist ниже —
      единственный способ добавить график, который не может сослаться на
      несуществующую метрику или произвольный код.

Расширяемость метрик (BOS §4 — гибкость сервиса, не хардкод под конкретный
сценарий): помимо трёх встроенных источников (лиды/прокси-выручка/расход),
`available_metrics()`/`resolve_series()` подхватывают ЛЮБУЮ метрику, которую
агент сам записал через инструмент record_metric → metrics.record() — так
разово попрошенный "курс доллара" не хардкодится сюда кодом, а становится
задачей развернуть скрипт+процесс, которые сами заводят метрику записью
значений (см. policies/dashboard_widget.md).

Расположение — свободный холст ("иконки на рабочем столе"): у каждого
виджета своя позиция и размер (`layout` в dashboard.json), а не список с
единственным порядком — перетаскивание и ресайз произвольны по обеим осям.
"""

import time
import uuid

from src.saas import context as ctx

_FILE = "dashboard.json"

ALLOWED_CHART_TYPES = ("line", "bar")
ALLOWED_GROUP_BY = ("day", "week", "month")
MAX_RANGE_DAYS = 730


def _load() -> dict:
    return ctx.read_json(_FILE, {"widgets": [], "layout": {}})


def _save(d: dict) -> None:
    ctx.write_json(_FILE, d)


def _bucket_key(ts: float, group_by: str) -> str:
    t = time.localtime(ts)
    if group_by == "month":
        return time.strftime("%Y-%m", t)
    if group_by == "week":
        return time.strftime("%G-W%V", t)  # ISO-неделя — сортируется как хронология
    return time.strftime("%Y-%m-%d", t)


def _bucket_sum(points: list[tuple[float, float]], group_by: str) -> list[dict]:
    buckets: dict[str, float] = {}
    for ts, val in points:
        k = _bucket_key(ts, group_by)
        buckets[k] = buckets.get(k, 0.0) + val
    return [{"label": k, "value": round(v, 2)} for k, v in sorted(buckets.items())]


def _date_to_ts(date_str: str) -> float:
    return time.mktime(time.strptime(date_str, "%Y-%m-%d"))


# ─────────────────────── встроенные источники (по метрике) ─────────────────
def leads_series(group_by: str = "day", since: float = 0.0) -> list[dict]:
    from src.office import leads as leads_module
    pts = [(l["ts"], 1.0) for l in leads_module.all_leads() if l.get("ts", 0) >= since]
    return _bucket_sum(pts, group_by)


def revenue_proxy_series(group_by: str = "day", since: float = 0.0) -> list[dict] | None:
    from src.office import leads as leads_module, brief
    check = brief.avg_check()
    if not check:
        return None
    pts = [(l["ts"], float(check)) for l in leads_module.all_leads() if l.get("ts", 0) >= since]
    return _bucket_sum(pts, group_by)


def spend_series(group_by: str = "day", since: float = 0.0) -> list[dict]:
    from src.office import costs as costs_module
    daily = costs_module.daily_series()
    pts = [(_date_to_ts(d["date"]), d["value"]) for d in daily if _date_to_ts(d["date"]) >= since]
    return _bucket_sum(pts, group_by)


def _generic_series(metric_id: str, group_by: str = "day", since: float = 0.0) -> list[dict]:
    """Ряд для ЛЮБОЙ метрики, записанной агентом через record_metric — общий
    путь расширяемости (см. докстринг модуля), не привязан к конкретному
    сценарию (валюта/склад/что угодно)."""
    from src.office import metrics as metrics_module
    pts = [(p["ts"], float(p["value"])) for p in metrics_module.series(metric_id, since=since)
           if isinstance(p.get("value"), (int, float))]
    return _bucket_sum(pts, group_by)


_BUILTIN_PROVIDERS = {
    "leads": leads_series,
    "revenue_proxy": revenue_proxy_series,
    "spend": spend_series,
}


def available_metrics() -> list[dict]:
    """Каталог того, что реально можно построить графиком СЕЙЧАС — единственный
    источник правды для orchestrator.interpret_dashboard_request (whitelist) и
    для системных карточек. Встроенные источники + всё, что когда-либо записал
    агент через record_metric (metrics.catalog()) — расширяемо без правки кода."""
    from src.office import leads as leads_module, brief, costs as costs_module, metrics as metrics_module
    out = []
    lds = leads_module.all_leads()
    if lds:
        earliest = min(l.get("ts", time.time()) for l in lds)
        out.append({"metric_id": "leads", "label": "Заявки", "unit": "шт",
                    "kind": "факт", "earliest_ts": earliest, "count": len(lds)})
        if brief.avg_check():
            out.append({"metric_id": "revenue_proxy", "label": "Прокси-выручка (заявки × средний чек)",
                        "unit": "деньги", "kind": "оценка", "earliest_ts": earliest, "count": len(lds)})
    daily_spend = costs_module.daily_series()
    if daily_spend:
        out.append({"metric_id": "spend", "label": "Расход на ИИ", "unit": "$",
                    "kind": "факт", "earliest_ts": _date_to_ts(daily_spend[0]["date"]),
                    "count": len(daily_spend)})
    out.extend(metrics_module.catalog())
    return out


def resolve_series(widget: dict) -> list[dict]:
    metric_id = widget.get("metric_id", "")
    provider = _BUILTIN_PROVIDERS.get(metric_id)
    since = time.time() - float(widget.get("range_days", 90)) * 86400
    if provider:
        return provider(widget.get("group_by", "day"), since) or []
    return _generic_series(metric_id, widget.get("group_by", "day"), since)


# ─────────────────────── системные карточки (не хранятся) ──────────────────
def system_widgets() -> list[dict]:
    from src.office import leads as leads_module, costs as costs_module, brief
    out = []
    lds = leads_module.all_leads()
    out.append({"id": "sys:leads_total", "kind": "metric", "system": True,
                "title": "Заявок всего", "value": len(lds), "unit": "шт", "source": "факт"})
    week = sum(1 for l in lds if l.get("ts", 0) >= time.time() - 7 * 86400)
    out.append({"id": "sys:leads_7d", "kind": "metric", "system": True,
                "title": "Заявок за 7 дней", "value": week, "unit": "шт", "source": "факт"})
    check = brief.avg_check()
    if check:
        out.append({"id": "sys:revenue_7d", "kind": "metric", "system": True,
                    "title": "Прокси-выручка за 7 дней", "value": round(week * check, 2),
                    "unit": "деньги", "source": "оценка",
                    "note": f"{week} заявок × {check:g} ср. чек"})
    t = costs_module.totals()
    out.append({"id": "sys:spend_total", "kind": "metric", "system": True,
                "title": "Расход на ИИ (всего)", "value": round(t["cost"], 4), "unit": "$", "source": "факт"})
    return out


# ─────────────────────── кастомные виджеты (хранятся) ───────────────────────
def custom_widgets() -> list[dict]:
    return list(_load().get("widgets", []))


def all_widgets() -> list[dict]:
    """Системные + кастомные, каждый со своим `layout` ({x,y,w,h} или None —
    None значит "ещё не расставляли руками", фронт сам вычисляет позицию по
    умолчанию при первом рендере)."""
    layout = _load().get("layout", {})
    widgets = system_widgets() + custom_widgets()
    for w in widgets:
        w["layout"] = layout.get(w["id"])
    return widgets


def add_custom(spec: dict) -> dict:
    """`spec` уже провалидирован вызывающим (orchestrator.interpret_dashboard_
    request) против ALLOWED_*/available_metrics() — здесь только сохранение."""
    d = _load()
    wid = f"w_{uuid.uuid4().hex[:8]}"
    widget = {"id": wid, "kind": "chart", "system": False, "created_ts": time.time(), **spec}
    d.setdefault("widgets", []).append(widget)
    _save(d)
    return widget


def remove_custom(widget_id: str) -> bool:
    d = _load()
    widgets = d.get("widgets", [])
    kept = [w for w in widgets if w["id"] != widget_id]
    if len(kept) == len(widgets):
        return False
    d["widgets"] = kept
    d.get("layout", {}).pop(widget_id, None)
    _save(d)
    return True


def set_layout(widget_id: str, x: float, y: float, w: float, h: float) -> None:
    """Позиция+размер одного виджета на свободном холсте — перетаскивание и
    ресайз одинаково пишут сюда (см. webapp BusinessDashboard: FreeCanvas)."""
    d = _load()
    layout = d.setdefault("layout", {})
    layout[widget_id] = {
        "x": round(float(x), 1), "y": round(float(y), 1),
        "w": round(float(w), 1), "h": round(float(h), 1),
    }
    _save(d)


def reset() -> None:
    ctx.delete_file(_FILE)
