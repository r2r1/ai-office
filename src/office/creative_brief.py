"""
Creative Brief — вкус владельца, зафиксированный designer'ом в
docs/creative_brief.md (см. builtin_skills/brand_book.md, шаг 0).

⚠️ Это НЕ отдельное хранилище с capture()/load() — агенты не вызывают
произвольные Python-функции, только инструменты (write_file/read_file/
ask_user). Реальный путь: designer сам читает/пишет этот файл через
write_file, как design_style.ensure_style_line читает/пишет docs/
site_content.md. Этот модуль — только read-side для prompt_builder.py
(системный контекст задачи), не более того.
"""

from src.office import workspace

_FILE = "docs/creative_brief.md"


def is_set() -> bool:
    """Designer уже спрашивал владельца (файл существует и непуст)."""
    content = workspace.read_file(_FILE)
    return bool(content) and not content.startswith("Файл не найден")


def prompt_block() -> str:
    """Сырой контент файла как контекст — не парсим жёстко в поля (designer
    пишет свободным текстом), достаточно передать модели то, что уже узнали."""
    if not is_set():
        return ""
    content = workspace.read_file(_FILE).strip()[:800]
    return f"=== ВКУС ВЛАДЕЛЬЦА (docs/creative_brief.md, заполнил designer) ===\n{content}"
