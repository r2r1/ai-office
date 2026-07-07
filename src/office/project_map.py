"""
Карта проекта (BOS §13, Knowledge materialized view) — короткий авто-обновляемый
файл `docs/_project_map.md` внутри workspace тенанта: дерево файлов + первые
строки ключевых .md/конфигов. Не новая сущность World Model — материализованный
кэш workspace.list_files(), который агент обнаруживает обычным list_files/
read_file, без правки prompt_builder.

Вызывается после успешного write_file (file_tool_handlers._handle_write_file),
с троттлингом — не чаще раза в 5 минут, чтобы не грузить workspace (запись
дёргает watchdog/reload, см. предупреждение в scripts/run.py) при частых записях.
"""

import time

from src.saas import context as ctx
from src.office import workspace as workspace_module

_MAP_FILE = "docs/_project_map.md"
_STATE_FILE = "project_map_state.json"
_THROTTLE_SECONDS = 300

_SUMMARY_EXTS = (".md", ".txt", ".json")
_SUMMARY_CHARS = 200
_MAX_SUMMARIZED_FILES = 20


def _last_refresh() -> float:
    return float(ctx.read_json(_STATE_FILE, {}).get("last_refresh", 0.0))


def _mark_refreshed() -> None:
    ctx.write_json(_STATE_FILE, {"last_refresh": time.time()})


def refresh(force: bool = False) -> str:
    """Пересобирает docs/_project_map.md. Возвращает записанный текст (или ""
    если пропущено из-за троттлинга). force=True игнорирует троттлинг (нужен
    первому вызову/тестам)."""
    now = time.time()
    if not force and (now - _last_refresh()) < _THROTTLE_SECONDS:
        return ""

    files = workspace_module.list_files()
    lines = [f"# Карта проекта (авто, обновлено {time.strftime('%Y-%m-%d %H:%M:%S')})", ""]
    if not files:
        lines.append("Workspace пуст.")
    else:
        lines.append(f"Всего файлов: {len(files)}")
        lines.append("")
        lines.append("## Дерево файлов")
        for f in files:
            lines.append(f"- {f['path']} ({f['size']} б)")
        summarized = 0
        summary_lines = []
        for f in files:
            if summarized >= _MAX_SUMMARIZED_FILES:
                break
            path = f["path"]
            if path == _MAP_FILE or not path.lower().endswith(_SUMMARY_EXTS):
                continue
            content = workspace_module.read_file(path)
            snippet = content.strip().replace("\n", " ")[:_SUMMARY_CHARS]
            if snippet:
                summary_lines.append(f"- **{path}**: {snippet}")
                summarized += 1
        if summary_lines:
            lines.append("")
            lines.append("## Краткое содержание ключевых файлов")
            lines.extend(summary_lines)

    text = "\n".join(lines) + "\n"
    workspace_module.write_file(_MAP_FILE, text)
    _mark_refreshed()
    return text
