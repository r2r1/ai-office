"""
Единый тип Artifact — тонкий адаптер поверх уже существующих модулей-
производителей (`sites.py`, `tenant_apps.py`, дальше — что зарегистрируется),
НЕ переписывание их (issue #2, docs/architecture-improvements.md).

Тот же приём развязки, что у `results.py`/Tool Router/Skills: модуль-
производитель регистрирует себя один раз (`register()`), потребитель
(World Model, закрытие Project — «что оставил после себя», будущая приёмка)
получает единый список артефактов компании без знания деталей конкретного
модуля. Раньше это приходилось делать руками в каждом потребителе отдельно —
`world.py` напрямую вызывал `sites.all_sites()`, а появление нового типа
результата (приложения, боты) требовало находить и править то же место снова.
"""

from dataclasses import dataclass
from typing import Callable

_REGISTRY: dict[str, "ArtifactKind"] = {}


@dataclass
class ArtifactKind:
    id: str
    label: str
    # Возвращает сырые записи модуля-производителя как есть (leads.py/sites.py
    # уже дают готовые list[dict] — переиспользуем, не дублируем).
    lister: Callable[[], list[dict]]
    # Приводит одну сырую запись к общей форме
    # {title, ref, project_id, created_ts, updated_ts}.
    normalize: Callable[[dict], dict]


def register(kind: ArtifactKind) -> None:
    _REGISTRY[kind.id] = kind


def all_kinds() -> list[ArtifactKind]:
    return list(_REGISTRY.values())


def all_artifacts() -> list[dict]:
    """Единый список артефактов компании по всем зарегистрированным типам,
    свежие сверху. Ошибка одного производителя не должна ронять остальных —
    отсутствие Docker для tenant_apps не должно скрывать сайты."""
    out: list[dict] = []
    for kind in all_kinds():
        try:
            raws = kind.lister()
        except Exception:
            raws = []
        for raw in raws:
            item = kind.normalize(raw)
            item["kind"] = kind.id
            item["kind_label"] = kind.label
            out.append(item)
    out.sort(key=lambda a: a.get("updated_ts") or a.get("created_ts") or 0, reverse=True)
    return out


def for_project(project_id: str) -> list[dict]:
    """Артефакты конкретного проекта — источник для Project.left_behind
    («что проект оставил после себя», BOS §5) без опроса каждого модуля вручную."""
    if not project_id:
        return []
    return [a for a in all_artifacts() if a.get("project_id") == project_id]
