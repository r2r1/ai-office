"""
Обработчики portfolio-инструментов (list_projects/list_project_files/
read_project_file) — иерархия доступа (BOS §6.1): лидеры/CEO/сервисные роли
видят бизнес НАСКВОЗЬ, читают файлы любого проекта тенанта, не только своего.

Read-only по построению: нет write-обёртки над чужим проектом (инвариант единой
ответственности за артефакт — менять чужой проект можно только делегировав в
него задачу). project_dir от модели валидируется через projects.valid_workspace_dir
(имя из реестра, не сырой путь) — отсечение path-инъекции.

Тот же контракт build(), что file_tool_handlers.py.
"""

from typing import Awaitable, Callable

from src.office import projects as projects_module
from src.office import workspace as workspace_module


def build(agent_id: str, role: str,
          publish: Callable[[dict], Awaitable[None]],
          publish_and_log: Callable[[dict], Awaitable[None]]) -> dict[str, Callable]:

    async def _handle_list_projects(args: dict) -> str:
        items = projects_module.portfolio()
        if not items:
            return "Проектов пока нет."
        return "\n".join(
            f"- {p['title'] or '(без названия)'} — статус: {p['status']}, папка: {p['workspace_dir'] or '(корень)'}"
            for p in items
        )

    async def _handle_list_project_files(args: dict) -> str:
        wd = projects_module.valid_workspace_dir(args.get("project_dir", ""))
        if wd is None:
            return "Проект не найден — возьми папку (workspace_dir) из list_projects."
        return workspace_module.tree_text_in(wd)

    async def _handle_read_project_file(args: dict) -> str:
        wd = projects_module.valid_workspace_dir(args.get("project_dir", ""))
        if wd is None:
            return "Проект не найден — возьми папку (workspace_dir) из list_projects."
        return workspace_module.read_file_in(wd, args.get("path", ""))

    return {
        "list_projects": _handle_list_projects,
        "list_project_files": _handle_list_project_files,
        "read_project_file": _handle_read_project_file,
    }
