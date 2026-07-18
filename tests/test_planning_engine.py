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
from unittest.mock import AsyncMock, patch

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
    # Явная просьба сайта → marketer → developer (ОДНА production-задача, не
    # designer→developer: раньше это было два последовательных шага на один и
    # тот же сайт, и developer систематически пересобирал уже готовый сайт
    # заново вместо точечной проверки — см. planning_engine.fallback_plan
    # docstring/комментарий. Тест ожидал СТАРУЮ трёхролевую форму и не был
    # обновлён вместе с кодом — падал молча, потому что весь набор tests/*.py
    # не запускался на Windows из-за отдельного UnicodeEncodeError, см. фикс
    # выше в этом же файле).
    assert [t["role"] for t in pe.fallback_plan("нужен лендинг")] == ["marketer", "developer"]
    # Общая цель без продукта → одна задача «спросить клиента, что строить»
    generic = pe.fallback_plan("развивать бизнес")
    assert len(generic) == 1 and generic[0]["role"] == "marketer"


def test_fallback_plan_audits_existing_site_for_growth_stage():
    """Issue #22 branching: growth/mature клиент уже пользуется сайтом (иначе
    стадия не определилась бы так) — план не должен пересобирать его вслепую."""
    plan = pe.fallback_plan("нужен сайт", business_stage="growth")
    assert [t["role"] for t in plan] == ["analyst", "developer"]
    assert "точки роста" in plan[0]["title"].lower()
    assert "не переписывать" in plan[1]["title"].lower() or "точечно" in plan[1]["title"].lower()


def test_fallback_plan_mature_stage_same_as_growth():
    plan = pe.fallback_plan("сделай лендинг", business_stage="mature")
    assert [t["role"] for t in plan] == ["analyst", "developer"]


def test_fallback_plan_ignores_growth_stage_when_unconfirmed():
    """Фаза 2 (docs/first-investigation-plan-2026-07-16.md): "growth" почти без
    сигналов (например search_company нашёл только рынок, не саму компанию) не
    должен включать ветку "у клиента уже есть сайт" — это реальный риск, что
    разработчик будет искать несуществующий сайт для анализа."""
    plan = pe.fallback_plan("нужен сайт", business_stage="growth", stage_confidence="unconfirmed")
    assert [t["role"] for t in plan] == ["marketer", "developer"]  # обычный путь "собери с нуля"


def test_fallback_plan_ignores_stage_when_no_site_requested():
    """business_stage не должна влиять на бот-путь или общий путь — только на явную
    просьбу сайта, иначе "growth"-клиент, просящий бота, получил бы неправильный план."""
    assert [t["role"] for t in pe.fallback_plan("сделай бот записи", business_stage="growth")] == \
        ["marketer", "integrator"]


def test_fallback_plan_launch_and_idea_stage_unaffected():
    """launch/idea/пустая стадия — прежнее поведение (клиент ещё не пользуется
    сайтом, пересборка с нуля уместна)."""
    for stage in ("launch", "idea", ""):
        assert [t["role"] for t in pe.fallback_plan("нужен лендинг", business_stage=stage)] == \
            ["marketer", "developer"]


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


def test_free_worker_of_role_prefers_exact_project_match():
    """Параллельные Work: если у отдела есть работник, закреплённый ИМЕННО за
    project_id задачи, он в приоритете над универсальным/чужим."""
    ctx.set_tenant("pe_unit_project_exact")
    registry.register("developer_pA", "developer", department="tech", project_id="pA")
    registry.register("developer_pB", "developer", department="tech", project_id="pB")
    import time
    found = pe.free_worker_of_role("tech", "developer", time.time() + 1000, project_id="pA")
    assert found is not None and found.agent_id == "developer_pA"
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_free_worker_of_role_falls_back_to_generic_legacy_worker():
    """Тенант, нанявший работников ДО появления параллельных Work (project_id=""),
    должен продолжать работать как раньше — универсальный работник годится
    для любого проекта."""
    ctx.set_tenant("pe_unit_project_legacy")
    registry.register("developer_1", "developer", department="tech")  # project_id="" по умолчанию
    import time
    found = pe.free_worker_of_role("tech", "developer", time.time() + 1000, project_id="pX")
    assert found is not None and found.agent_id == "developer_1"
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_free_worker_of_role_excludes_worker_of_other_project():
    """Работник, закреплённый за ЧУЖИМ проектом, не подходит — иначе один
    developer съедал бы слот параллельности другого активного проекта."""
    ctx.set_tenant("pe_unit_project_exclude")
    registry.register("developer_pB", "developer", department="tech", project_id="pB")
    import time
    found = pe.free_worker_of_role("tech", "developer", time.time() + 1000, project_id="pA")
    assert found is None
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_has_role_for_project():
    ctx.set_tenant("pe_unit_has_role_for_project")
    registry.register("developer_pA", "developer", department="tech", project_id="pA")
    assert pe._has_role_for_project("tech", "developer", "pA") is True
    assert pe._has_role_for_project("tech", "developer", "pB") is False
    assert pe._has_role_for_project("tech", "designer", "pA") is False
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_dept_decision_sig_ignores_process_task_ticks():
    """Форензик-аудит 2026-07-18: старый board_sig (plan.board_summary, счётчик
    "✓N") менялся на КАЖДЫЙ тик повторяющегося процесса — CEO платно
    перевызывал LLM 7 раз подряд без единого реального изменения ситуации.
    _dept_decision_sig должен игнорировать задачи процессов (requested_by
    начинается с "process:") — тик процесса не меняет отпечаток."""
    from src.office import plan
    ctx.set_tenant("pe_unit_dept_sig_process")
    plan.add_task("Реальная задача разработчика", "developer", project_id="p1")
    sig_before = pe._dept_decision_sig("tech")
    # Тик процесса — новая задача, но НЕ от пользователя/CEO, а от процесса.
    plan.add_task("Ежедневный курс USD/RUB", "developer",
                  requested_by="process:proc1_123", project_id="p1")
    sig_after_tick = pe._dept_decision_sig("tech")
    assert sig_before == sig_after_tick, "тик процесса не должен менять отпечаток решения CEO"
    # А вот НОВАЯ обычная задача (не от процесса) — меняет.
    plan.add_task("Ещё одна реальная задача", "developer", project_id="p1")
    sig_after_real = pe._dept_decision_sig("tech")
    assert sig_after_real != sig_before, "реальная новая задача обязана менять отпечаток"
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_dept_decision_sig_still_reacts_to_process_task_blocker():
    """Блокер важен даже у задачи процесса — это НЕ фоновый шум, а реальный
    сигнал, что процесс застрял (см. Корень 6: эскалация повторных блокеров)."""
    from src.office import plan
    ctx.set_tenant("pe_unit_dept_sig_process_blocker")
    t = plan.add_task("Ежедневный курс USD/RUB", "developer",
                      requested_by="process:proc1_123", project_id="p1")
    sig_before = pe._dept_decision_sig("tech")
    plan.block(t["id"], "нет доступа к источнику курса")
    sig_after = pe._dept_decision_sig("tech")
    assert sig_before != sig_after, "блокер задачи процесса обязан менять отпечаток"
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_orchestrate_does_not_reopen_department_ceo_just_closed():
    """Форензик-аудит 2026-07-18: CEO закрывал отдел (close_department), а
    несколькими строками ниже в ТОМ ЖЕ вызове orchestrate() авто-открытие "по
    плану задач" тут же открывало его заново — close_department не трогает
    задачи отдела, и если хоть одна незакрытая задача оставалась,
    departments_needed() всё ещё её видел. Владелец видел «закрыт → открыт»
    подряд. orchestrator.decide_company замокан (LLM не вызывается,
    plan.is_generated()=True после add_task ниже отключает LLM-путь лидеров —
    см. planning_engine.run_leaders "План — ЕДИНСТВЕННЫЙ источник работы")."""
    from src.office import plan, org

    async def _test():
        ctx.set_tenant("pe_unit_no_reopen")
        org.open_department("marketing", reason="test", objective="test")
        # Задача отдела остаётся НЕЗАКРЫТОЙ — ровно тот случай, когда
        # departments_needed() продолжает требовать "marketing" после закрытия.
        plan.add_task("Написать пост", "marketer", project_id="p1")
        assert "marketing" in plan.departments_needed()

        events = []
        async def fake_publish(ev):
            events.append(ev)

        fake_decision = {"action": "close_department", "department": "marketing",
                         "thought": "цель отдела достигнута"}
        with patch("src.agents.orchestrator.decide_company", new=AsyncMock(return_value=fake_decision)):
            await pe.orchestrate("тест", fake_publish, cycle=0)

        assert "marketing" not in org.open_departments(), \
            "CEO явно закрыл отдел этим решением — авто-открытие не должно его тут же вернуть"

    asyncio.run(_test())
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
    # Windows-консоль часто в cp1251 — "✓" ронял ЛЮБОЙ тест этого файла
    # UnicodeEncodeError ДО единой строки реального результата (found: весь
    # набор tests/*.py был непроверяем из этой сессии на Windows).
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    _run()
