"""
Unit-тесты Planning Engine и провайдер-классификаторов (Phase 6, расслоение loop.py).

Первые тесты в проекте. Смысл расслоения — чтобы планирование/маршрутизация
проверялись БЕЗ поднятия полного офис-цикла (LLM не вызывается, $0). Запуск:

    python tests/test_planning_engine.py

Покрыты юнитами только функции БЕЗ вызова LLM: чистые помощники (верх файла) +
`verify_and_fix_if_needed`/`hire_leader`/`forget_tenant` (финальный срез Phase 6).
`orchestrate`/`run_leaders`/`apply_company_decision` вызывают `orchestrator.
decide_company`/`leaders.decide` (LLM) и/или планируют фоновые `execution.assign`
(запустил бы попытку реального LLM-вызова в фоне) — они тестируются только живым
прогоном офиса, не юнитами.
"""

import asyncio
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core import llm
from src.office import planning_engine as pe
from src.office import registry, workspace
from src.saas import context as ctx


def test_provider_error_classifiers():
    assert llm.is_quota_error("Error 403: insufficient balance")
    assert llm.is_quota_error("额度不足")
    assert not llm.is_quota_error("connection timeout")
    assert llm.is_model_unavailable_error("model_not_found")
    assert llm.is_model_unavailable_error("no available channel")
    assert not llm.is_model_unavailable_error("rate limited")


def test_fallback_plan_is_deterministic():
    # Явная просьба бота → marketer → integrator
    assert [t["role"] for t in pe.fallback_plan("сделай бот записи")] == ["marketer", "integrator"]
    # Явная просьба сайта → marketer → designer → developer
    assert [t["role"] for t in pe.fallback_plan("нужен лендинг")] == ["marketer", "designer", "developer"]
    # Общая цель без продукта → одна задача «спросить клиента, что строить»
    generic = pe.fallback_plan("развивать бизнес")
    assert len(generic) == 1 and generic[0]["role"] == "marketer"


def test_has_orphan_tasks():
    ctx.set_tenant("pe_unit_test")
    from src.saas import context
    # researcher не входит ни в один отдел → orphan
    context.write_json("plan.json", {"generated": True, "tasks": [
        {"id": "t1", "title": "x", "role": "researcher", "status": "pending", "department": ""}]})
    assert pe.has_orphan_tasks() is True
    # marketer обслуживается отделом marketing → не orphan
    context.write_json("plan.json", {"generated": True, "tasks": [
        {"id": "t1", "title": "x", "role": "marketer", "status": "pending", "department": "marketing"}]})
    assert pe.has_orphan_tasks() is False
    import shutil
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_verify_and_fix_if_needed_dedup_and_critical():
    ctx.set_tenant("pe_unit_verify")
    from src.saas import context
    context.write_json("plan.json", {"generated": True, "tasks": []})
    published = []

    async def collect(e):
        published.append(e)

    # Нет сайта вовсе → check_site() критично («не найден index»), но задача должна
    # добавиться (нет открытой fix-задачи в очереди).
    added = asyncio.run(pe.verify_and_fix_if_needed(collect))
    assert added is True
    assert any("исправить критические" in t.get("title", "").lower()
               for t in context.read_json("plan.json", {}).get("tasks", []))
    assert any(e.get("type") == "system" for e in published)

    # Повторный вызов — fix-задача уже pending → НЕ дублируем.
    published.clear()
    added_again = asyncio.run(pe.verify_and_fix_if_needed(collect))
    assert added_again is False
    assert not published

    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_verify_and_fix_not_needed_when_site_ok():
    ctx.set_tenant("pe_unit_verify_ok")
    from src.saas import context
    context.write_json("plan.json", {"generated": True, "tasks": []})
    workspace.write_file("site/index.html",
        "<html lang='ru'><head><title>x</title><meta name='viewport' content='w'>"
        "<style>body{color:#000}</style></head><body>"
        "<form action='/api/site-lead' method='post'>"
        "<input name='contact'><button>Отправить</button></form>"
        + "текст " * 60 + "</body></html>")

    async def collect(e):
        pass

    added = asyncio.run(pe.verify_and_fix_if_needed(collect))
    assert added is False  # ни одной критической проблемы — доработка не нужна
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_hire_leader_registers_once():
    ctx.set_tenant("pe_unit_hire_leader")
    published = []

    async def collect(e):
        published.append(e)

    assert not registry.has_role("cto")
    asyncio.run(pe.hire_leader("tech", "цель отдела", collect))
    assert registry.has_role("cto")
    assert any(e.get("type") == "hired" and e.get("role") == "cto" for e in published)

    # Лидер уже есть — повторный вызов не публикует «hired» снова.
    published.clear()
    asyncio.run(pe.hire_leader("tech", "другая цель", collect))
    assert not published

    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_forget_tenant_clears_leader_signature():
    pe._last_leader_sig["pe_unit_forget:tech"] = ("assign|x|developer", 2)
    pe._last_leader_sig["board:pe_unit_forget:tech"] = ("board summary", 0)
    pe._last_leader_sig["other_tenant:tech"] = ("y", 1)
    pe.forget_tenant("pe_unit_forget")
    assert not any(k.startswith("pe_unit_forget:") or k.startswith("board:pe_unit_forget:")
                   for k in pe._last_leader_sig)
    assert "other_tenant:tech" in pe._last_leader_sig  # чужой тенант не задет
    pe._last_leader_sig.pop("other_tenant:tech", None)


def _run():
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
            passed += 1
    print(f"ВСЕ {passed} ТЕСТОВ ПРОШЛИ")


if __name__ == "__main__":
    _run()
