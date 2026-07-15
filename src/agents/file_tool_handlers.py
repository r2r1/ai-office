"""
Обработчики файловых инструментов агента (write_file/read_file/list_files/
verify_code/execute_code/delete_file/configure_bot) — вынесены из
agent_factory.py (901 → 566 строк после первого прохода, см. tool_schemas.py;
это второй проход декомпозиции того же god-модуля, docs/audit-dd-2026-07-06.md
§19 п.6). Сделано ПОСЛЕ того, как tests/test_agent_tool_handlers.py зафиксировал
текущее поведение — извлечение непокрытых тестами замыканий было прямой
причиной, по которой этот же рефакторинг не делался раньше в этой сессии.

`build()` — фабрика: принимает то немногое, что реально нужно замыканиям
(agent_id, role, publish, publish_and_log), и возвращает словарь обработчиков —
тот же контракт, что agent_factory.create() передаёт в
llm.run_agent(tool_handlers={...}).
"""

from typing import Awaitable, Callable

from src.office import workspace as workspace_module
from src.office import project_map
from src.office import roles as roles_module


def build(agent_id: str, role: str,
          publish: Callable[[dict], Awaitable[None]],
          publish_and_log: Callable[[dict], Awaitable[None]]) -> dict[str, Callable]:

    async def _handle_write_file(args: dict) -> str:
        path = (args.get("path") or "").strip()
        content = args.get("content", "")
        # Самолечение: developer/designer/integrator иногда забывают префикс site/ у
        # веб-файла (видели в проде: 9 html-страниц подряд ушли в корень workspace
        # вместо site/) — тогда авто-публикация начинает читать/показывать клиенту
        # РАСХОДЯЩУЮСЯ копию, а правки в реальном site/ становятся невидимы. Нормализуем
        # путь ДО записи, а не патчим последствия на стороне чтения.
        if (role in ("developer", "designer", "integrator") and path
                and "/" not in path and path.lower().endswith((".html", ".css", ".js"))):
            path = f"site/{path}"
        denial = roles_module.path_denied(role, path)
        if denial:
            await publish_and_log({"type": "speech", "agent_id": agent_id, "text": f"🚫 {denial}"})
            return denial
        res = workspace_module.write_file(path, content)
        await publish_and_log({"type": "speech", "agent_id": agent_id, "text": f"📝 {res}"})
        if res.startswith("Файл сохранён:"):
            # Извлекаем реальный путь из ответа: «Файл сохранён: <path> (N символов).»
            actual_path = res.split(":", 1)[1].strip().split(" (")[0]
            await publish({"type": "file_written", "agent_id": agent_id, "path": actual_path,
                           "text": f"📝 {agent_id}: {res}"})
            if actual_path != project_map._MAP_FILE:
                try:
                    project_map.refresh()
                except Exception:
                    pass
        return res

    async def _handle_read_file(args: dict) -> str:
        return workspace_module.read_file(args.get("path", ""))

    async def _handle_list_files(args: dict) -> str:
        return workspace_module.tree_text()

    async def _handle_verify_code(args: dict) -> str:
        res = workspace_module.verify_text()
        await publish_and_log({"type": "speech", "agent_id": agent_id, "text": f"🧪 {res}"})
        return res

    async def _handle_execute_code(args: dict) -> str:
        path = args.get("path", "")
        stdin = args.get("stdin", "")
        await publish_and_log({"type": "speech", "agent_id": agent_id, "text": f"▶️ Запускаю {path}…"})
        res = workspace_module.execute_code(path, stdin)
        short = res.replace("\n", " ")
        await publish_and_log({"type": "speech", "agent_id": agent_id, "text": f"📤 {short}"})
        await publish({"type": "code_executed", "agent_id": agent_id, "path": path,
                       "text": f"▶️ {agent_id}: {path} → {short}"})
        return res

    async def _handle_delete_file(args: dict) -> str:
        path = args.get("path", "")
        denial = roles_module.path_denied(role, path)
        if denial:
            await publish_and_log({"type": "speech", "agent_id": agent_id, "text": f"🚫 {denial}"})
            return denial
        res = workspace_module.delete_file(path)
        await publish_and_log({"type": "speech", "agent_id": agent_id, "text": f"🗑 {res}"})
        return res

    async def _handle_configure_bot(args: dict) -> str:
        from src.office import bot_config
        patch = {}
        for k in ("services", "ask_fields", "greeting", "success_message"):
            if args.get(k) is not None:
                patch[k] = args[k]
        cfg = bot_config.update(patch)
        await publish_and_log({"type": "speech", "agent_id": agent_id,
                               "text": f"⚙️ Настроил бота: услуги={cfg.get('services') or '—'}"})
        return (f"Конфиг бота обновлён. Услуги: {cfg.get('services') or 'нет (спросит имя+телефон)'}, "
                f"поля: {cfg.get('ask_fields')}. Теперь можно launch_bot.")

    return {
        "write_file": _handle_write_file,
        "read_file": _handle_read_file,
        "list_files": _handle_list_files,
        "verify_code": _handle_verify_code,
        "execute_code": _handle_execute_code,
        "delete_file": _handle_delete_file,
        "configure_bot": _handle_configure_bot,
    }
