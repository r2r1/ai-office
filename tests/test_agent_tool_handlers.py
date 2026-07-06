"""
Юнит-тесты обработчиков инструментов agent_factory.py (docs/audit-dd-2026-07-06.md
§19 п.6 — эти обработчики были НЕ покрыты ни одним тестом, что и остановило
попытку декомпозиции 901-строчного agent_factory.py в этой же сессии: рефакторинг
без теста, фиксирующего текущее поведение, — риск тихо сломать wiring).

Обработчики — замыкания, создаваемые ВНУТРИ create() и передаваемые в
llm.run_agent(tool_handlers={...}) непосредственно перед реальным LLM-вызовом.
Чтобы получить к ним доступ БЕЗ реального (платного) вызова LLM — мокаем
llm.run_agent: он просто СОХРАНЯЕТ переданные kwargs (включая tool_handlers)
и возвращает фиктивный результат, реальный API не вызывается ни разу.

Запуск: python tests/test_agent_tool_handlers.py
"""

import asyncio
import shutil
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.agents import agent_factory
from src.office import connections, workspace, plan as plan_module


def _fresh_tenant(name: str) -> None:
    ctx.set_tenant(name)
    workspace.reset()
    connections.reset()
    plan_module.reset()


async def _captured_handlers(role="developer", agent_id="developer_1", task="test task") -> dict:
    """Вызывает agent_factory.create(), перехватывая tool_handlers из вызова
    llm.run_agent БЕЗ реального обращения к LLM API."""
    captured = {}

    async def fake_run_agent(**kwargs):
        captured.update(kwargs)
        return "фиктивный результат (LLM не вызывался)"

    events = []

    async def fake_publish(ev):
        events.append(ev)

    with patch("src.core.llm.run_agent", side_effect=fake_run_agent):
        fn = agent_factory.create(role, task, agent_id, fake_publish)
        await fn()
    return captured["tool_handlers"], events


def _run_async(coro):
    return asyncio.run(coro)


# ── _try_extract_connection (чистая функция, без моков) ─────────────────────

def test_extract_connection_detects_api_key():
    conn = agent_factory._try_extract_connection(
        "Какой у вас API-ключ для Telegram?", "abc123secret")
    assert conn is not None
    assert conn["name"] == "Telegram"
    assert conn["type"] == "api"
    assert conn["fields"]["key"] == "abc123secret"


def test_extract_connection_detects_login_password():
    conn = agent_factory._try_extract_connection(
        "Нужен логин и пароль для входа", "login: user1 password: pass1")
    assert conn is not None
    assert conn["type"] == "login"
    assert conn["fields"]["login"] == "user1"
    assert conn["fields"]["password"] == "pass1"


def test_extract_connection_returns_none_for_non_credential_questions():
    assert agent_factory._try_extract_connection("Как дела?", "хорошо") is None


def test_extract_connection_returns_none_for_empty_answer():
    assert agent_factory._try_extract_connection("Ваш API-ключ?", "") is None


# ── _handle_write_file: нормализация пути для site-файлов ───────────────────

def test_write_file_normalizes_bare_html_to_site_for_developer():
    _fresh_tenant("af_test_write_file")
    handlers, events = _run_async(_captured_handlers(role="developer"))
    result = _run_async(handlers["write_file"]({"path": "index.html", "content": "<h1>hi</h1>"}))
    assert "site/index.html" in result
    assert workspace.read_file("site/index.html").startswith("<h1>")


def test_write_file_does_not_touch_path_with_slash():
    _fresh_tenant("af_test_write_file2")
    handlers, events = _run_async(_captured_handlers(role="developer"))
    result = _run_async(handlers["write_file"]({"path": "assets/style.css", "content": "body{}"}))
    assert "assets/style.css" in result


def test_write_file_publishes_file_written_event_on_success():
    _fresh_tenant("af_test_write_file3")
    handlers, events = _run_async(_captured_handlers(role="developer"))
    _run_async(handlers["write_file"]({"path": "site/app.js", "content": "console.log(1)"}))
    assert any(e.get("type") == "file_written" for e in events)


# ── _handle_read_file / _handle_list_files ───────────────────────────────────

def test_read_file_roundtrips_write_file():
    _fresh_tenant("af_test_read_file")
    handlers, _ = _run_async(_captured_handlers(role="developer"))
    _run_async(handlers["write_file"]({"path": "notes.txt", "content": "hello world"}))
    content = _run_async(handlers["read_file"]({"path": "notes.txt"}))
    assert "hello world" in content


def test_list_files_reflects_written_files():
    _fresh_tenant("af_test_list_files")
    handlers, _ = _run_async(_captured_handlers(role="developer"))
    _run_async(handlers["write_file"]({"path": "a.txt", "content": "x"}))
    tree = _run_async(handlers["list_files"]({}))
    assert "a.txt" in tree


# ── _handle_delegate_task: валидация роли ────────────────────────────────────

def test_delegate_task_rejects_own_role():
    _fresh_tenant("af_test_delegate1")
    handlers, _ = _run_async(_captured_handlers(role="developer"))
    result = _run_async(handlers["delegate_task"]({"role": "developer", "title": "что-то"}))
    assert "сам" in result.lower()


def test_delegate_task_rejects_unknown_role():
    _fresh_tenant("af_test_delegate2")
    handlers, _ = _run_async(_captured_handlers(role="developer"))
    result = _run_async(handlers["delegate_task"]({"role": "нет_такой_роли", "title": "что-то"}))
    assert "не существует" in result.lower()


def test_delegate_task_creates_real_task_on_board():
    _fresh_tenant("af_test_delegate3")
    handlers, events = _run_async(_captured_handlers(role="developer", agent_id="developer_1"))
    result = _run_async(handlers["delegate_task"]({
        "role": "marketer", "title": "Написать оффер", "done_criterion": "готов текст"}))
    tasks = plan_module.all_tasks()
    assert any(t["title"] == "Написать оффер" and t["role"] == "marketer" for t in tasks)
    assert "поставлена" in result.lower()


# ── _handle_raise_event ───────────────────────────────────────────────────────

def test_raise_event_rejects_empty_summary():
    _fresh_tenant("af_test_raise1")
    handlers, _ = _run_async(_captured_handlers(role="marketer"))
    result = _run_async(handlers["raise_event"]({"kind": "problem", "summary": ""}))
    assert "суть" in result.lower()


def test_raise_event_creates_real_event():
    _fresh_tenant("af_test_raise2")
    from src.office import events as events_module
    handlers, _ = _run_async(_captured_handlers(role="marketer", agent_id="marketer_1"))
    _run_async(handlers["raise_event"]({"kind": "opportunity", "summary": "нашли канал"}))
    pending = events_module.pending()
    assert any("нашли канал" in e.get("summary", "") for e in pending)


# ── _handle_get_connection ────────────────────────────────────────────────────

def test_get_connection_returns_not_found_message_with_available_list():
    _fresh_tenant("af_test_getconn1")
    connections.save({"name": "GitHub", "type": "api", "fields": {"key": "ghtoken"}, "note": ""})
    handlers, _ = _run_async(_captured_handlers(role="integrator"))
    result = _run_async(handlers["get_connection"]({"name": "Notion"}))
    assert "не найдено" in result
    assert "GitHub" in result


def test_get_connection_returns_saved_credential():
    _fresh_tenant("af_test_getconn2")
    connections.save({"name": "GitHub", "type": "api", "fields": {"key": "ghtoken123"}, "note": ""})
    handlers, _ = _run_async(_captured_handlers(role="integrator"))
    result = _run_async(handlers["get_connection"]({"name": "GitHub"}))
    assert "ghtoken123" in result


# ── extra_tools: execute_code скрыт из каталога, когда исполнение выключено ──

def test_execute_code_tool_hidden_when_code_execution_disabled():
    import os
    os.environ["ALLOW_CODE_EXECUTION"] = "0"
    _fresh_tenant("af_test_exec_hidden")
    handlers, _ = _run_async(_captured_handlers(role="developer"))
    assert "execute_code" not in handlers


def test_execute_code_tool_present_when_enabled():
    import os
    os.environ["ALLOW_CODE_EXECUTION"] = "1"
    try:
        _fresh_tenant("af_test_exec_shown")
        handlers, _ = _run_async(_captured_handlers(role="developer"))
        assert "execute_code" in handlers
    finally:
        os.environ["ALLOW_CODE_EXECUTION"] = "0"


def _run():
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
            passed += 1
    print(f"ВСЕ {passed} ТЕСТОВ ПРОШЛИ")


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    _run()
