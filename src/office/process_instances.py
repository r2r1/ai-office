"""
Process Instance — обобщённый движок для BOS-сущности `Process` (§5): работа,
которая никогда не завершается сама по себе (продажи, поддержка, контент-конвейер).
У Process нет единой «текущей стадии» — вместо этого набор Stage-определений
(шаблон конвейера) + поток Instance, у каждого своя текущая стадия и история
переходов.

`leads.py` (мини-CRM, продажи) — первая специализация: регистрирует процесс
"sales" поверх этого движка и оставляет свой файл (`leads.json`) и свой внешний
контракт (add/get/set_status/...) БЕЗ ИЗМЕНЕНИЙ — существующие потребители
(server.py, ResultsView.tsx, metrics.py, gap.py, world.py) ничего не замечают.
Новый процесс (тикеты поддержки, контент-конвейер) — это `register()` + тонкая
обёртка по образцу leads.py, а не копия всей механики.
"""

import time
import uuid

from src.saas import context as ctx

MAX_INSTANCES = 1000

_REGISTRY: dict[str, dict] = {}


def register(process: str, file: str, stages: tuple[str, ...], labels: dict[str, str],
             stage_field: str = "status") -> None:
    """Регистрирует процесс: где хранится, какие стадии, как называется поле стадии
    в записи (у leads.py это исторически "status" — не переименовываем ради
    обратной совместимости файла). Стадия по умолчанию для новых записей — stages[0]."""
    _REGISTRY[process] = {
        "file": file, "stages": stages, "labels": labels, "stage_field": stage_field,
    }


def _spec(process: str) -> dict:
    if process not in _REGISTRY:
        raise KeyError(f"Process '{process}' не зарегистрирован — вызови process_instances.register() первым")
    return _REGISTRY[process]


def _all(process: str) -> list[dict]:
    return ctx.read_json(_spec(process)["file"], [])


def _save(process: str, items: list[dict]) -> None:
    ctx.write_json(_spec(process)["file"], items)


def _migrate(process: str, inst: dict) -> dict:
    """Записи, заведённые до регистрации процесса (или до этого движка вообще),
    не имеют поля стадии/истории — достраиваем на лету, не переписывая файл целиком."""
    spec = _spec(process)
    sf = spec["stage_field"]
    if sf not in inst:
        inst = {**inst, sf: spec["stages"][0], "updated_ts": inst.get("ts", 0),
                "history": [{"ts": inst.get("ts", 0), "kind": "created", "text": "Создан"}]}
    return inst


def add(process: str, fields: dict) -> dict:
    """Создаёт новый Instance в начальной стадии (stages[0])."""
    spec = _spec(process)
    sf = spec["stage_field"]
    items = _all(process)
    ts = time.time()
    inst = {
        "id": uuid.uuid4().hex[:8], **fields, "ts": ts,
        sf: spec["stages"][0], "updated_ts": ts,
        "history": [{"ts": ts, "kind": "created", "text": "Создан"}],
    }
    items.append(inst)
    if len(items) > MAX_INSTANCES:
        del items[: len(items) - MAX_INSTANCES]
    _save(process, items)
    return inst


def all_instances(process: str) -> list[dict]:
    return sorted((_migrate(process, i) for i in _all(process)), key=lambda x: x["ts"], reverse=True)


def get(process: str, instance_id: str) -> dict | None:
    for i in all_instances(process):
        if i.get("id") == instance_id:
            return i
    return None


def set_stage(process: str, instance_id: str, stage: str, note: str = "") -> dict | None:
    """Переводит Instance на новую стадию, пишет запись в историю. None — если
    инстанс или стадия не найдены."""
    spec = _spec(process)
    if stage not in spec["stages"]:
        return None
    sf = spec["stage_field"]
    labels = spec["labels"]
    items = [_migrate(process, i) for i in _all(process)]
    for i in items:
        if i.get("id") == instance_id:
            prev = i.get(sf, spec["stages"][0])
            i[sf] = stage
            i["updated_ts"] = time.time()
            text = f"Стадия: {labels.get(prev, prev)} → {labels.get(stage, stage)}"
            if note:
                text += f" — {note.strip()[:200]}"
            i.setdefault("history", []).append({"ts": i["updated_ts"], "kind": "stage_change", "text": text})
            _save(process, items)
            return i
    return None


def add_note(process: str, instance_id: str, text: str, by: str = "") -> dict | None:
    text = (text or "").strip()
    if not text:
        return None
    items = [_migrate(process, i) for i in _all(process)]
    for i in items:
        if i.get("id") == instance_id:
            i["updated_ts"] = time.time()
            i.setdefault("history", []).append(
                {"ts": i["updated_ts"], "kind": "note", "text": text[:500], "by": by})
            _save(process, items)
            return i
    return None


def stale_in_first_stage(process: str, hours: float) -> list[dict]:
    """Instance, всё ещё в начальной стадии (stages[0]) дольше `hours` — кандидаты
    на follow-up/дожим (продажи) или эскалацию (поддержка)."""
    spec = _spec(process)
    sf, first = spec["stage_field"], spec["stages"][0]
    cutoff = time.time() - hours * 3600
    return [i for i in all_instances(process) if i.get(sf, first) == first and i.get("ts", 0) < cutoff]


def check_stale_events(process: str, hours: float, name_fields: tuple[str, ...] = (),
                        message: str = "{count} элемент(ов) без движения {hours}+ часов: {names}",
                        detail: str = "", event_kind: str = "opportunity", from_role: str = "crm") -> int:
    """Event Layer (BOS §10): залежавшиеся в первой стадии Instance — доменное
    событие, не отдельный механизм опроса. Раз в вызов поднимает ОДНО агрегированное
    событие на все новые залежавшиеся сразу, помечая их notified_stale, чтобы не
    спамить одним и тем же наблюдением каждый цикл. Возвращает число элементов в
    новом событии (0 — событие не поднято)."""
    from src.office import events as events_module
    spec = _spec(process)
    sf, first = spec["stage_field"], spec["stages"][0]
    items = [_migrate(process, i) for i in _all(process)]
    cutoff = time.time() - hours * 3600
    fresh_stale = [i for i in items if i.get(sf, first) == first
                   and i.get("ts", 0) < cutoff and not i.get("notified_stale")]
    if not fresh_stale:
        return 0
    for i in fresh_stale:
        i["notified_stale"] = True
    _save(process, items)

    def _display(i: dict) -> str:
        for f in name_fields:
            v = (i.get(f) or "").strip()
            if v:
                return v[:30]
        return "без имени"

    names = ", ".join(_display(i) for i in fresh_stale[:5])
    events_module.raise_event(
        event_kind, message.format(count=len(fresh_stale), hours=int(hours), names=names),
        detail=detail, from_role=from_role)
    return len(fresh_stale)


def count(process: str) -> int:
    return len(_all(process))


def count_since(process: str, ts: float) -> int:
    return sum(1 for i in _all(process) if i.get("ts", 0) >= ts)


def count_last_days(process: str, days: int = 7) -> int:
    return count_since(process, time.time() - days * 86400)


def reset(process: str) -> None:
    ctx.delete_file(_spec(process)["file"])
