"""
DNA — единый снимок идентичности компании (issue #4, docs/architecture-
improvements.md). `philosophy.py` и `constitution.py` ОСТАЮТСЯ двумя файлами
хранения (`philosophy.json`/`constitution.json`) — их API и потребители
(`server.py` `/api/philosophy`/`/api/constitution`, фронт `ProfileTab`,
`loop.py`.`requires_ok`) не трогаем: мигрировать хранение без функциональной
причины — дорогой риск ради косметики.

Что реально было НЕ единым — ЧТЕНИЕ: `world.py` и `prompt_builder.py` каждый
собирали identity вручную из двух источников. `snapshot()` — одна точка
чтения обеих частей вместе; `version()` — детерминированный хеш содержимого
(не счётчик в файле: не требует, чтобы philosophy.py/constitution.py знали
про dna.py и вызывали bump — исключает и лишнюю связанность, и гонку записи).
"""

import hashlib
import json

from src.office import philosophy, constitution


def _raw() -> dict:
    phil = philosophy.load()
    const = constitution.load()
    return {
        "mission": phil.get("mission", ""),
        "success_means": phil.get("success_means", ""),
        "never_sacrifice": phil.get("never_sacrifice", ""),
        "growth_style": phil.get("growth_style", ""),
        "risk_appetite": phil.get("risk_appetite", ""),
        "budget_auto_limit": const.get("budget_auto_limit", 0),
        "rules_override": const.get("rules_override", {}),
        "custom_rules": const.get("custom_rules", []),
    }


def version() -> str:
    """Детерминированный хеш текущего DNA — меняется сам, как только меняется
    любая из двух частей (philosophy.save/constitution.save/set_action_rule/
    add_custom_rule), без явного bump-вызова откуда-либо."""
    raw = json.dumps(_raw(), sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:10]


def snapshot() -> dict:
    """Единый срез идентичности компании — то, что раньше world.py собирал
    вручную из philosophy.load()+constitution.payload() построчно."""
    return {**_raw(), "version": version()}


def context_block() -> str:
    """Единый промпт-блок идентичности — философия + конституция вместе,
    вместо двух раздельных вызовов в prompt_builder.py."""
    parts = [philosophy.context_block(), constitution.rule_block()]
    return "\n\n".join(p for p in parts if p)
