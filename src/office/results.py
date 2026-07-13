"""
Реестр типов результата работы команды (BOS: "что команда произвела для
бизнеса" — отдельная ось от Work/Team, см. CLAUDE.md §Продукт vs процесс).

Тот же приём развязки, что у Tool Router (tool_router.py) и Skills (skills.py):
модуль-производитель результата (leads.py, sites.py, в будущем — tenant_apps.py,
интеграции сообщений) регистрирует себя ОДИН раз при импорте через `register()`.
Фронт (`ResultsView.tsx`) рендерит вкладки ПО ЭТОМУ реестру — добавление нового
типа результата не требует правки NavRail/App.tsx/этого файла, только:
(1) регистрация в модуле-производителе, (2) один компонент-рендерер во фронте.
"""

from dataclasses import dataclass
from typing import Callable

_REGISTRY: dict[str, "ResultKind"] = {}


@dataclass
class ResultKind:
    id: str
    label: str
    icon: str
    order: int
    # Счётчик для бейджа вкладки — по договорённости "число, требующее внимания"
    # (новые лиды, а не вообще все), а не обязательно общее количество.
    counter: Callable[[], int]


def register(kind: ResultKind) -> None:
    _REGISTRY[kind.id] = kind


def all_kinds() -> list[ResultKind]:
    return sorted(_REGISTRY.values(), key=lambda k: k.order)


def snapshot() -> dict:
    """Данные для /api/results — метаданные вкладок, БЕЗ самих items (их фронт
    уже получает через существующие /api/leads, /api/sites и т.п.)."""
    kinds = []
    for k in all_kinds():
        try:
            count = k.counter()
        except Exception:
            count = 0
        kinds.append({"id": k.id, "label": k.label, "icon": k.icon, "order": k.order, "count": count})
    return {"kinds": kinds}
