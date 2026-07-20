"""
Unit-тесты Execution (Phase 6, расслоение loop.py) — чистые помощники и состояние
живости БЕЗ поднятия офис-цикла (run_task/assign требуют LLM и здесь не гоняются).

    python tests/test_execution.py
"""

import asyncio
import sys
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.office import execution as ex, workspace
from src.saas import context as ctx, context


def test_tk_isolates_by_tenant():
    ctx.set_tenant("t_a")
    assert ex.tk("developer_1") == "t_a:developer_1"
    ctx.set_tenant("t_b")
    assert ex.tk("developer_1") == "t_b:developer_1"


def test_current_milestone_state():
    ctx.set_tenant("exec_unit_ms")
    ex.set_cur_ms("build")
    assert ex.cur_ms() == "build"


def test_forget_tenant_clears_liveness():
    ctx.set_tenant("exec_unit_forget")
    ex.set_cur_ms("x")
    ex._thinking_since["exec_unit_forget:a"] = 1.0
    ex._agent_task["exec_unit_forget:a"] = "t1"
    ex._model_fail_count["exec_unit_forget:a"] = 2
    ex.forget_tenant("exec_unit_forget")
    assert not any(k.startswith("exec_unit_forget:") for k in ex._thinking_since)
    assert not any(k.startswith("exec_unit_forget:") for k in ex._agent_task)
    assert not any(k.startswith("exec_unit_forget:") for k in ex._model_fail_count)
    assert ex.cur_ms() == ""  # _current_ms этого тенанта тоже очищен


def test_engagement_needs_bot():
    ctx.set_tenant("exec_unit_bot")
    context.write_json("brief.json", {"goal": "нужен телеграм-бот записи", "niche": "салон"})
    assert ex.engagement_needs_bot() is True
    context.write_json("brief.json", {"goal": "лендинг под звонки", "niche": "потолки"})
    assert ex.engagement_needs_bot() is False
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


# ── Гейт синтаксиса JS/HTML перед публикацией (реальный прод-баг) ───────────
# Прод-кейс (ai-office-log-20260704_085755): designer на дешёвой модели написал
# сырой JSX («<div>») вместо React.createElement вопреки явному запрету скилла
# framer_motion_3d_site.md — site/app.js не парсился браузером («Unexpected
# token '<'»), а publish_site_auto публиковал сломанную версию на ЖИВОЙ URL
# БЕЗУСЛОВНО, до любых проверок. Пользователь увидел пустую страницу на ~17 минут
# и несколько циклов правок, пока «Unexpected token '<'» не поймал headless-
# браузер (review_site_visual) — а не node --check, который ловит это мгновенно.
_BROKEN_JS = "const x = <div>broken jsx</div>;"
_FIXED_JS = "const x = React.createElement('div', null, 'fixed');"
_INDEX_HTML = ("<!DOCTYPE html><html><body><div id='root'></div>"
               "<script type='module' src='./app.js'></script></body></html>")


async def _noop_publish(payload):
    pass


def test_verify_detects_broken_jsx_via_node_check():
    """Базовая проверка детектора, на котором строится гейт: node --check реально
    ловит сырой JSX (не гипотетически — тем же путём, что уронил прод)."""
    ctx.set_tenant("exec_unit_js_verify")
    workspace.write_file("site/index.html", _INDEX_HTML)
    workspace.write_file("site/app.js", _BROKEN_JS)
    v = workspace.verify()
    assert v["ok"] is False
    assert any("app.js" in e for e in v["errors"])
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_review_and_maybe_fix_blocks_publish_when_js_stays_broken():
    """Если правка НЕ помогла — сайт НЕ публикуется (не остаётся сломанным на живом URL)."""
    ctx.set_tenant("exec_unit_js_gate_blocked")
    workspace.write_file("site/index.html", _INDEX_HTML)
    workspace.write_file("site/app.js", _BROKEN_JS)

    async def fake_fn():
        return "не смог исправить"  # файл остаётся сломанным

    with patch("src.office.execution.agent_factory.create", return_value=fake_fn), \
         patch("src.office.execution.publish_site_auto", new=AsyncMock()) as mock_publish:
        asyncio.run(ex.review_and_maybe_fix(
            "designer", "designer_1", "собери сайт", "", "tech", "",
            _noop_publish, result="done", started_ts=0.0))
    mock_publish.assert_not_called()
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_review_and_maybe_fix_publishes_after_js_fixed():
    """Если правка ПОМОГЛА — сайт публикуется как обычно (гейт не душит здоровый путь)."""
    ctx.set_tenant("exec_unit_js_gate_fixed")
    workspace.write_file("site/index.html", _INDEX_HTML)
    workspace.write_file("site/app.js", _BROKEN_JS)

    async def fake_fn():
        workspace.write_file("site/app.js", _FIXED_JS)
        return "Изменения: исправил синтаксис"

    with patch("src.office.execution.agent_factory.create", return_value=fake_fn), \
         patch("src.office.execution.publish_site_auto", new=AsyncMock()) as mock_publish, \
         patch("src.office.critic.check_site", return_value=[]), \
         patch("src.office.critic.review_site_visual", new=AsyncMock(return_value=[])), \
         patch("src.office.critic.review_site_llm", new=AsyncMock(return_value=[])):
        asyncio.run(ex.review_and_maybe_fix(
            "designer", "designer_1", "собери сайт", "", "tech", "",
            _noop_publish, result="done", started_ts=0.0))
    mock_publish.assert_called_once()
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_review_and_maybe_fix_publishes_immediately_when_js_already_valid():
    """Здоровый путь (без ошибок) не трогается гейтом — ни одной лишней попытки правки."""
    ctx.set_tenant("exec_unit_js_gate_healthy")
    workspace.write_file("site/index.html", _INDEX_HTML)
    workspace.write_file("site/app.js", _FIXED_JS)

    with patch("src.office.execution.agent_factory.create") as mock_create, \
         patch("src.office.execution.publish_site_auto", new=AsyncMock()) as mock_publish, \
         patch("src.office.critic.check_site", return_value=[]), \
         patch("src.office.critic.review_site_visual", new=AsyncMock(return_value=[])), \
         patch("src.office.critic.review_site_llm", new=AsyncMock(return_value=[])):
        asyncio.run(ex.review_and_maybe_fix(
            "designer", "designer_1", "собери сайт", "", "tech", "",
            _noop_publish, result="done", started_ts=0.0))
    mock_publish.assert_called_once()
    mock_create.assert_not_called()  # без ошибок — доп. правка не запускается
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


# ── heal_stuck_agents: вотчдог персонально по агенту, не блокирует лечение
#    ВСЕХ агентов тенанта из-за ЧУЖОГО открытого вопроса (production-readiness
#    worklist п.5) ────────────────────────────────────────────────────────────

def test_heal_stuck_agents_only_protects_agent_with_own_pending_question():
    ctx.set_tenant("exec_unit_watchdog_scoped")
    from src.office import questions as questions_mod, registry as registry_mod
    registry_mod.reset()
    registry_mod.register("designer_1", "designer", "рисует лендинг", department="tech")
    registry_mod.register("developer_1", "developer", "зависший таск", department="tech")
    # Оба стартуют "thinking" — иначе assert "== idle" был бы истинен и без
    # лечения (register() по умолчанию ставит "idle"), проверка ничего не докажет.
    registry_mod.update_status("designer_1", "thinking")
    registry_mod.update_status("developer_1", "thinking")
    old = ex.MAX_THINK_SECS
    ex.MAX_THINK_SECS = 0.01  # мгновенный таймаут для теста
    try:
        # designer_1 реально спрашивает владельца — НЕ должен считаться зависшим
        async def _ask():
            qid, _fut = questions_mod.ask("Какой цвет бренда?", agent_id="designer_1")
            return qid
        asyncio.run(_ask())
        ex._thinking_since[ex.tk("designer_1")] = 0.0  # "давно" в прошлом
        ex._thinking_since[ex.tk("developer_1")] = 0.0  # тоже "давно", но БЕЗ вопроса
        asyncio.run(ex.heal_stuck_agents(_noop_publish))
        # designer_1 защищён своим вопросом — таймер продлён, не сброшен в idle
        assert ex.tk("designer_1") in ex._thinking_since
        assert registry_mod.get("designer_1").status != "idle"
        # developer_1 не имеет своего вопроса — лечится как обычно
        assert ex.tk("developer_1") not in ex._thinking_since
        assert registry_mod.get("developer_1").status == "idle"
    finally:
        ex.MAX_THINK_SECS = old
        ex._thinking_since.pop(ex.tk("designer_1"), None)
        ex._thinking_since.pop(ex.tk("developer_1"), None)
        registry_mod.reset()
        shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


# ── friendly error hints: сырое исключение не единственное, что видит владелец ──

def test_friendly_error_hints_cover_common_network_exceptions():
    for exc_name in ("ConnectionError", "TimeoutError"):
        assert exc_name in ex._FRIENDLY_ERROR_HINTS
        assert ex._FRIENDLY_ERROR_HINTS[exc_name]  # непустой текст


def _run():
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
            passed += 1
    print(f"ВСЕ {passed} ТЕСТОВ ПРОШЛИ")


if __name__ == "__main__":
    # Windows-консоль часто в cp1251 — "✓" ронял ЛЮБОЙ тест этого файла
    # UnicodeEncodeError ДО единой строки реального результата (found: весь
    # набор tests/*.py был непроверяем из этой сессии на Windows).
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    _run()
