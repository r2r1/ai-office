"""
Sitemap — карта многостраничного сайта, которую designer пишет в
docs/sitemap.md (см. builtin_skills/sitemap_planning.md). Нужна ТОЛЬКО когда
проект — больше одной страницы; лендинг сам по себе sitemap не требует
(is_set() вернёт false, developer строит одну страницу как раньше).

Как и creative_brief.py — read-side helper поверх файла, который designer сам
читает/пишет через инструменты (write_file/read_file), НЕ отдельное хранилище
с save()/capture(), которое агент не может вызвать напрямую (агенты вызывают
только зарегистрированные тулы, не произвольные Python-функции office/*.py).
"""

from src.office import workspace

_FILE = "docs/sitemap.md"
_APPROVED_MARKER = "Статус: одобрено владельцем"


def is_set() -> bool:
    """Есть ли уже карта сайта (designer составил её для этого проекта)."""
    content = workspace.read_file(_FILE)
    return bool(content) and not content.startswith("Файл не найден")


def is_approved() -> bool:
    """Одобрил ли владелец карту явным «да» — маркер designer дописывает сам
    ПОСЛЕ подтверждения (см. skill, шаг 3), а не потому что файл существует."""
    if not is_set():
        return False
    return _APPROVED_MARKER in workspace.read_file(_FILE)


def prompt_block() -> str:
    """Контекст для developer — строить одну страницу или несколько по карте."""
    if not is_set():
        return ""
    content = workspace.read_file(_FILE).strip()[:1500]
    status = "ОДОБРЕНА владельцем" if is_approved() else "черновик, ЕЩЁ НЕ одобрен владельцем"
    return f"=== КАРТА САЙТА ({status}) — docs/sitemap.md ===\n{content}"
