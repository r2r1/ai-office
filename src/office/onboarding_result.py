"""
Результат первого впечатления клиента (BOS §5): аналитика + точки роста +
id инициатив, сгенерированные ОДИН РАЗ сразу после стратегии в BOOTSTRAP
(см. orchestrator.generate_onboarding_result, office/loop.py). Раньше
клиент после онбординга не видел ничего, кроме списка сотрудников — офис
уже что-то "думал" за его спиной, но не показывал результат.

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


def save(analysis: list[str], growth_points: list[str], initiative_ids: list[str]) -> dict:
    d = {
        "analysis": analysis, "growth_points": growth_points,
        "initiative_ids": initiative_ids, "ts": time.time(),
    }
    ctx.write_json(_FILE, d)
    return d


def reset() -> None:
    ctx.delete_file(_FILE)
