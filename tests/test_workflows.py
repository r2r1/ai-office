"""
Тесты workflows.py (Layer 4 — составной бизнес-глагол) + интеграция с
plan.py/capability-гейтом: заголовок задачи, матчащий workflow, должен
получать ТОЧНЫЕ required_capabilities из декларации, а не угаданные по словам
заголовка (capability.derive_required их не видит вообще — "проанализировать
Битрикс" не содержит ни одного слова из capability._NEED_WORDS).

    python tests/test_workflows.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import workflows, plan, capability, brief


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


def test_crm_analysis_title_matches_workflow():
    wf = workflows.match("Проанализировать Битрикс и подготовить отчёт по сделкам")
    assert wf is not None
    assert wf.id == "crm_analysis"


def test_unrelated_title_does_not_match_any_workflow():
    assert workflows.match("Написать текст для лендинга") is None


def test_required_capabilities_of_returns_none_when_no_match():
    assert workflows.required_capabilities_of("Обычная задача без составного глагола") is None


def test_required_capabilities_of_returns_declared_list_when_matched():
    caps = workflows.required_capabilities_of("Проанализировать CRM за квартал")
    assert caps == ["crm"]


def test_plan_task_gets_workflow_capabilities_not_guessed_ones():
    """Реальный кейс: capability.derive_required не видит "crm" в заголовке
    вообще (её нет в _NEED_WORDS) — без workflows required_capabilities была
    бы пустой, и capability-гейт не узнал бы о зависимости заранее."""
    _fresh("wf_test_plan_caps")
    brief.set_brief({"goal": "тест"})
    title = "Проанализировать Битрикс и найти узкие места воронки"
    # без workflow (по чистым словам) capability не находит ничего
    assert capability.derive_required({"title": title}) == []
    plan.set_tasks([{"id": "t1", "title": title, "role": "analyst",
                     "done_criterion": "отчёт готов"}])
    t = plan.get_task("t1")
    assert t["required_capabilities"] == ["crm"]
    assert t["workflow_id"] == "crm_analysis"


def test_plan_task_without_workflow_keeps_old_behavior():
    _fresh("wf_test_plan_no_wf")
    brief.set_brief({"goal": "тест"})
    plan.set_tasks([{"id": "t1", "title": "Настроить Telegram-бота приёма заявок",
                     "role": "integrator", "done_criterion": "бот отвечает"}])
    t = plan.get_task("t1")
    assert t["required_capabilities"] == ["telegram_bot"]
    assert t["workflow_id"] == ""


def test_add_task_also_tags_workflow_id():
    _fresh("wf_test_add_task")
    brief.set_brief({"goal": "тест"})
    t = plan.add_task("Проанализировать Битрикс: воронка продаж", "analyst",
                       done_criterion="отчёт сформирован")
    assert t["workflow_id"] == "crm_analysis"
    assert t["required_capabilities"] == ["crm"]


def test_explicit_llm_capabilities_win_over_workflow():
    """Явная декларация из LLM-плана (required_capabilities в исходной задаче)
    всегда главнее — workflow только фолбэк, когда явного нет."""
    _fresh("wf_test_explicit_wins")
    brief.set_brief({"goal": "тест"})
    plan.set_tasks([{"id": "t1", "title": "Проанализировать Битрикс", "role": "analyst",
                     "done_criterion": "готово", "required_capabilities": ["email"]}])
    t = plan.get_task("t1")
    assert t["required_capabilities"] == ["email"]


def test_capability_gate_recognizes_crm_id():
    """capability.py знает про "crm" (для workflow из этого модуля) — без
    записи в _CATALOG capability.registry() отбросил бы способность как
    неизвестную и missing()/registry() тихо её не видели бы."""
    reg = capability.registry()
    ids = {i["id"] for i in reg["capabilities"]}
    assert "crm" in ids


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("wf_test_*"):
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
