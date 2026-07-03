"""
Unit-тесты Planning Engine и провайдер-классификаторов (Phase 6, расслоение loop.py).

Первые тесты в проекте. Смысл расслоения — чтобы планирование/маршрутизация
проверялись БЕЗ поднятия полного офис-цикла (LLM не вызывается, $0). Запуск:

    python tests/test_planning_engine.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core import llm
from src.office import planning_engine as pe
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
