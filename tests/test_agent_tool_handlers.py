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
from src.office import connections, workspace, plan as plan_module, office_channel, questions as questions_module


def _fresh_tenant(name: str) -> None:
    """ctx.wipe() удаляет ВСЮ директорию тенанта на диске (не только
    отдельные *.reset()) — раньше здесь чистились только workspace/
    connections/plan, и залипшая запись в memory.json от ОДНОГО out-of-band
    ручного прогона (см. историю отладки test_ask_user_resolves_when_answered)
    несколько раз молча ломала повторный запуск того же теста с той же
    memory-подсказкой «уже отвечали» — реальный, воспроизводимый баг
    изоляции тестов, не продакшен-кода."""
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)  # wipe() не трогает ContextVar, но директория пересоздаётся лениво


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


# ── _handle_write_file / _handle_delete_file: enforcement границ роли ────────

def test_designer_write_to_site_is_denied():
    _fresh_tenant("af_test_role_boundary1")
    handlers, events = _run_async(_captured_handlers(role="designer"))
    result = _run_async(handlers["write_file"]({"path": "site/index.html", "content": "<h1>hi</h1>"}))
    assert result.startswith("Ошибка:")
    assert workspace.read_file("site/index.html").startswith("Файл не найден")


def test_designer_write_to_docs_is_allowed():
    _fresh_tenant("af_test_role_boundary2")
    handlers, _ = _run_async(_captured_handlers(role="designer"))
    result = _run_async(handlers["write_file"]({"path": "docs/brand_book.md", "content": "# Стиль"}))
    assert "docs/brand_book.md" in result
    assert workspace.read_file("docs/brand_book.md").startswith("# Стиль")


def test_developer_write_to_site_is_allowed():
    _fresh_tenant("af_test_role_boundary3")
    handlers, _ = _run_async(_captured_handlers(role="developer"))
    result = _run_async(handlers["write_file"]({"path": "site/index.html", "content": "<h1>hi</h1>"}))
    assert "site/index.html" in result


def test_designer_delete_in_site_is_denied():
    _fresh_tenant("af_test_role_boundary4")
    handlers, _ = _run_async(_captured_handlers(role="developer"))
    _run_async(handlers["write_file"]({"path": "site/index.html", "content": "x"}))
    handlers_designer, _ = _run_async(_captured_handlers(role="designer", agent_id="designer_1"))
    result = _run_async(handlers_designer["delete_file"]({"path": "site/index.html"}))
    assert result.startswith("Ошибка:")
    assert workspace.read_file("site/index.html") == "x"


# ── analyze_image: гейт по роли + реальный вызов через мокнутый describe_image ─

def test_analyze_image_available_to_designer():
    _fresh_tenant("af_test_vision1")
    handlers, _ = _run_async(_captured_handlers(role="designer"))
    assert "analyze_image" in handlers


def test_analyze_image_not_available_to_marketer():
    _fresh_tenant("af_test_vision2")
    handlers, _ = _run_async(_captured_handlers(role="marketer"))
    assert "analyze_image" not in handlers


def test_analyze_image_calls_describe_image_and_returns_result():
    _fresh_tenant("af_test_vision3")
    handlers, _ = _run_async(_captured_handlers(role="designer"))

    async def fake_describe_image(image_url, question, agent_id="agent", model=None):
        assert image_url == "https://example.com/frame.png"
        return "Тёплая терракотовая палитра, засечковый заголовок."

    with patch("src.core.llm.describe_image", side_effect=fake_describe_image):
        result = _run_async(handlers["analyze_image"](
            {"image_url": "https://example.com/frame.png", "question": "опиши палитру"}))
    assert "терракотовая" in result.lower()


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


# ── _handle_read_office_chat ──────────────────────────────────────────────────

def test_read_office_chat_empty():
    _fresh_tenant("af_test_chat_empty")
    handlers, _ = _run_async(_captured_handlers(role="marketer"))
    result = _run_async(handlers["read_office_chat"]({}))
    assert "пуст" in result.lower()


def test_read_office_chat_returns_recent_messages():
    _fresh_tenant("af_test_chat_msgs")
    office_channel.post("developer_1", "developer", "собрал лендинг")
    handlers, _ = _run_async(_captured_handlers(role="marketer"))
    result = _run_async(handlers["read_office_chat"]({"n": 5}))
    assert "собрал лендинг" in result


# ── _handle_ask_user: путь из памяти (детерминированный, без ожидания future) ─

def test_ask_user_returns_cached_answer_from_memory_without_asking():
    _fresh_tenant("af_test_ask_user_cache")
    from src.office import memory as memory_module
    memory_module.remember("Какой у вас телефон поддержки?", "+7 123 456")
    handlers, events = _run_async(_captured_handlers(role="salesman"))
    result = _run_async(handlers["ask_user"]({"question": "Какой у вас телефон поддержки?"}))
    assert result == "+7 123 456"
    assert any(e.get("type") == "speech" and "из памяти" in e.get("text", "") for e in events)


# ── _handle_ask_user: реальный вопрос → ответ пользователя резолвит future ────

def test_ask_user_resolves_when_answered():
    """asyncio.sleep(0)-петля для ожидания «дошёл ли обработчик до await» —
    недетерминированный таймингistov приём (проявилось флейки при прогоне через
    tests/run_all.py, хотя одиночный запуск файла стабильно проходил) — заменено
    на явный asyncio.Event, выставляемый publish() РОВНО в момент нужного события."""
    _fresh_tenant("af_test_ask_user_real2")

    async def scenario():
        events = []
        question_published = asyncio.Event()

        async def fake_publish(ev):
            events.append(ev)
            if ev.get("type") == "agent_message":
                question_published.set()

        async def fake_run_agent(**kwargs):
            return "n/a"

        with patch("src.core.llm.run_agent", side_effect=fake_run_agent):
            fn = agent_factory.create("developer", "test", "developer_1", fake_publish)
            captured = {}

            async def fake_run_agent2(**kw):
                captured.update(kw)
                return "ok"
            with patch("src.core.llm.run_agent", side_effect=fake_run_agent2):
                await fn()

        handler = captured["tool_handlers"]["ask_user"]
        task = asyncio.ensure_future(handler({"question": "Уникальный вопрос теста?"}))
        await asyncio.wait_for(question_published.wait(), timeout=5)
        qid = next(e["question_id"] for e in events if e.get("type") == "agent_message")
        questions_module.answer(qid, "мой ответ")
        return await task

    result = _run_async(scenario())
    assert result == "мой ответ"


# ── _handle_ask_colleague: делает СВОЙ, отдельный llm.run_agent-вызов ─────────

def test_ask_colleague_rejects_same_role():
    _fresh_tenant("af_test_ask_colleague1")
    handlers, _ = _run_async(_captured_handlers(role="developer"))
    result = _run_async(handlers["ask_colleague"]({"role": "developer", "question": "как дела?"}))
    assert "сам" in result.lower()


def test_ask_colleague_returns_answer_from_mocked_llm_call():
    """ask_colleague делает СВОЙ llm.run_agent (не тот, что уже замокан и вышел
    из контекста в _captured_handlers) — нужен отдельный patch на момент вызова
    самого обработчика, иначе тест дёрнул бы реальный API."""
    _fresh_tenant("af_test_ask_colleague2")
    handlers, events = _run_async(_captured_handlers(role="developer", agent_id="developer_1"))

    async def fake_colleague_reply(**kwargs):
        assert kwargs["user"] == "какой у нас оффер?"
        return "Оффер: бесплатный замер + скидка 10%"

    with patch("src.core.llm.run_agent", side_effect=fake_colleague_reply):
        result = _run_async(handlers["ask_colleague"]({"role": "marketer", "question": "какой у нас оффер?"}))
    assert "бесплатный замер" in result


def test_ask_colleague_handles_llm_failure_gracefully():
    _fresh_tenant("af_test_ask_colleague3")
    handlers, _ = _run_async(_captured_handlers(role="developer"))

    async def failing_call(**kwargs):
        raise RuntimeError("provider timeout")

    with patch("src.core.llm.run_agent", side_effect=failing_call):
        result = _run_async(handlers["ask_colleague"]({"role": "marketer", "question": "?"}))
    assert "реши сам" in result.lower()


# ── _handle_use_capability: реальный роутер + встроенная интеграция website ───

def test_use_capability_finds_website_publish_without_credentials():
    """website — единственная интеграция без cred_fields (всегда «подключена»),
    удобный детерминированный кандидат для проверки Tool Router без сети."""
    _fresh_tenant("af_test_use_capability")
    handlers, events = _run_async(_captured_handlers(role="developer"))
    result = _run_async(handlers["use_capability"]({
        "need": "опубликовать лендинг", "params": {}}))
    assert "website" in result.lower() or "не найден" not in result.lower()


def test_use_capability_empty_need_asks_to_describe():
    _fresh_tenant("af_test_use_capability_empty")
    handlers, _ = _run_async(_captured_handlers(role="developer"))
    result = _run_async(handlers["use_capability"]({"need": ""}))
    assert "опиши" in result.lower()


# ── _handle_use_skill / _handle_find_skills ───────────────────────────────────

def test_use_skill_no_match_lists_available_or_says_none():
    _fresh_tenant("af_test_use_skill")
    handlers, _ = _run_async(_captured_handlers(role="developer"))
    result = _run_async(handlers["use_skill"]({"need": "совершенно случайная тарабарщина xyzzy123"}))
    assert isinstance(result, str) and result

def test_find_skills_empty_query_lists_catalog_or_says_none():
    _fresh_tenant("af_test_find_skills")
    handlers, _ = _run_async(_captured_handlers(role="developer"))
    result = _run_async(handlers["find_skills"]({"query": ""}))
    assert isinstance(result, str) and result


# ── _handle_list_integrations ─────────────────────────────────────────────────

def test_list_integrations_mentions_website():
    _fresh_tenant("af_test_list_integrations")
    handlers, _ = _run_async(_captured_handlers(role="developer"))
    result = _run_async(handlers["list_integrations"]({}))
    assert "website" in result.lower()


def _cleanup_test_tenants() -> None:
    """Тесты создают реальные data/tenants/af_test_* директории (ctx.wipe() в
    _fresh_tenant чистит ПЕРЕД тестом, не после) — без этого шага мусор копится
    на диске с каждым прогоном (найдено при отладке флейки в этом же файле:
    залипшая запись в memory.json ОДНОГО ручного прогона ломала повторные
    запуски). data/ в .gitignore, так что в репозиторий это не попадает, но
    захламляет диск разработчика."""
    for d in ctx.ROOT.glob("af_test_*"):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)


def _run():
    passed = 0
    try:
        for name, fn in sorted(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
                print(f"  ✓ {name}")
                passed += 1
    finally:
        _cleanup_test_tenants()
    print(f"ВСЕ {passed} ТЕСТОВ ПРОШЛИ")


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    _run()
