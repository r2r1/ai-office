"""
Результат первого впечатления клиента (BOS §5): аналитика + точки роста +
id инициатив, сгенерированные ОДИН РАЗ сразу после стратегии в BOOTSTRAP
(см. orchestrator.generate_onboarding_result, office/loop.py). Раньше
клиент после онбординга не видел ничего, кроме списка сотрудников — офис
уже что-то "думал" за его спиной, но не показывал результат.

Подтверждение (портрет §23) — тот же паттерн draft→confirmed, что уже есть
у `specification.py`: первый дашборд — самый нагруженный последствиями вывод
офиса о компании (если понимание неверно, а BOOTSTRAP уже спроектировал ТЗ и
план на его основе — циклы и доверие потрачены впустую). `office/loop.py`
ждёт `is_confirmed()`, ПРЕЖДЕ чем впервые звать architect.run_async — см.
докстринг в loop.py у этой проверки для деталей обратной совместимости.

Хранилище: data/tenants/<tid>/onboarding_result.json.
"""

import time

from src.saas import context as ctx

_FILE = "onboarding_result.json"


def exists() -> bool:
    """Генерировать нужно РОВНО ОДИН раз на тенанта — иначе рестарт офиса
    (bootstrap с уже сохранённой strategy.md) заново дёргал бы LLM и
    перезаписывал initiatives каждый раз, когда тенант перезапускается."""
    return bool(ctx.read_json(_FILE, None))


def get() -> dict:
    return ctx.read_json(_FILE, {})


def has_content(d: dict | None = None) -> bool:
    """Есть ли дашборду что подтверждать. Генерация могла упасть и сохранить
    пустой результат (см. loop.py: `result = {}` при исключении) — ждать
    подтверждения пользователя на пустоте было бы тупиком, не защитой."""
    d = d if d is not None else get()
    return bool(d.get("analysis") or d.get("growth_points") or d.get("initiative_ids"))


def is_confirmed() -> bool:
    return get().get("status") == "confirmed"


def confirm(note: str = "") -> dict:
    """Владелец посмотрел первый дашборд и подтвердил (портрет §23) — тот же
    ритуал, что `specification.confirm`. Разблокирует architect/milestones/
    plan в loop.py."""
    d = get()
    d["status"] = "confirmed"
    d["confirmed_note"] = (note or "").strip()[:300]
    d["confirmed_ts"] = time.time()
    ctx.write_json(_FILE, d)
    return d


def save(analysis: list[str], growth_points: list[str], initiative_ids: list[str]) -> dict:
    d = {
        "analysis": analysis, "growth_points": growth_points,
        "initiative_ids": initiative_ids, "ts": time.time(),
        "status": "draft",
    }
    ctx.write_json(_FILE, d)
    return d


def reset() -> None:
    ctx.delete_file(_FILE)
