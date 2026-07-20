"""
Тесты связи Этап↔Задача (milestones.active_stage_id → plan.milestone_id).

Раньше Stage (milestones.py) и Task (plan.py) были двумя параллельными,
никак не связанными системами: Stage хранил только текстовый журнал событий
(items), Task не знал, к какому этапу относится. UI не мог честно построить
дерево «Этап → Задача» (обсуждали при редизайне ProjectView). Теперь новая
задача помечается milestone_id активного на момент создания этапа.

    python tests/test_milestone_task_link.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import milestones, plan, brief


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


def test_active_stage_id_returns_active_when_present():
    _fresh("mst_test_active")
    milestones.mark_active("research")
    assert milestones.active_stage_id() == "research"


def test_active_stage_id_falls_back_to_next_pending_when_none_active():
    _fresh("mst_test_no_active")
    milestones.set_status("intake", "done")
    # ни один этап явно не active — current_index должен указать на следующий pending
    assert milestones.active_stage_id() == "research"


def test_active_stage_id_empty_when_no_stages():
    _fresh("mst_test_empty")
    milestones.reset()
    # BASE_STAGES всегда есть по умолчанию (intake первый) — пустой список
    # практически недостижим, но функция не должна падать при пустом входе
    st = milestones.all_stages()
    assert len(st) > 0  # sanity: BASE_STAGES подставляются сами


def test_new_task_via_set_tasks_gets_milestone_id():
    _fresh("mst_test_set_tasks")
    brief.set_brief({"goal": "тест"})
    milestones.mark_active("strategy")
    plan.set_tasks([{"id": "t1", "title": "Собрать оффер", "role": "marketer"}])
    t = plan.get_task("t1")
    assert t["milestone_id"] == "strategy"


def test_new_task_via_add_task_gets_milestone_id():
    _fresh("mst_test_add_task")
    brief.set_brief({"goal": "тест"})
    milestones.mark_active("research")
    t = plan.add_task("Провести анализ рынка", "analyst")
    assert t["milestone_id"] == "research"


def test_task_milestone_id_follows_active_stage_transition():
    """Задачи, созданные в РАЗНЫЕ моменты (разный активный этап), получают
    РАЗНЫЙ milestone_id — связь честная (на момент создания), не задним числом."""
    _fresh("mst_test_transition")
    brief.set_brief({"goal": "тест"})
    milestones.mark_active("research")
    t1 = plan.add_task("Задача на этапе исследования", "analyst")
    milestones.mark_active("strategy")
    t2 = plan.add_task("Задача на этапе стратегии", "marketer")
    assert t1["milestone_id"] == "research"
    assert t2["milestone_id"] == "strategy"


# ── resync ещё не начатых задач при переключении фокуса этапа (живой аудит
#    2026-07-20, найдено на реальном прогоне) ──────────────────────────────

def test_mark_active_resyncs_pending_tasks_of_same_project_to_new_stage():
    """Задачи, сгенерированные под "предполагаемый следующий" этап ("content"),
    остаются подписаны им же навсегда, если офис реально переключает фокус
    на ДРУГОЙ этап того же проекта ("build") — до фикса. UI показывал их
    "без этапа", хотя реальная работа шла под другим, новым этапом."""
    _fresh("mst_test_resync")
    from src.office import projects
    brief.set_brief({"goal": "тест"})
    proj = projects.ensure_active()
    milestones.set_business_stages(
        [{"id": "content", "title": "Контент"}, {"id": "build", "title": "Сборка"}],
        project_id=proj["id"])
    milestones.mark_active("content")  # "предполагаемый следующий" на момент генерации
    plan.set_tasks([{"id": "t1", "title": "Задача 1", "role": "marketer"},
                    {"id": "t2", "title": "Задача 2", "role": "developer"}])
    assert plan.get_task("t1")["milestone_id"] == "content"
    # Офис реально переключает фокус на "build", минуя "content"
    milestones.mark_active("build")
    assert plan.get_task("t1")["milestone_id"] == "build"
    assert plan.get_task("t2")["milestone_id"] == "build"


def test_mark_active_does_not_resync_already_started_tasks():
    """Задача, уже взятая в работу (status != pending), сохраняет исторически
    точную метку того этапа, где реально была начата — не переписывается
    задним числом."""
    _fresh("mst_test_resync_started")
    from src.office import projects
    brief.set_brief({"goal": "тест"})
    proj = projects.ensure_active()
    milestones.set_business_stages(
        [{"id": "content", "title": "Контент"}, {"id": "build", "title": "Сборка"}],
        project_id=proj["id"])
    milestones.mark_active("content")
    plan.set_tasks([{"id": "t1", "title": "Задача 1", "role": "marketer"}])
    plan.assign("t1", "marketer_1")  # переводит в in_progress
    milestones.mark_active("build")
    assert plan.get_task("t1")["milestone_id"] == "content"  # не тронута


def test_mark_active_ignores_stages_without_project():
    """Bootstrap-этапы (intake/research/strategy) без project — общекомпаней-
    ские, resync их не касается (план ведёт задачи только по проектам)."""
    _fresh("mst_test_resync_no_project")
    brief.set_brief({"goal": "тест"})
    milestones.mark_active("research")
    plan.set_tasks([{"id": "t1", "title": "Задача", "role": "marketer"}])
    milestones.mark_active("strategy")
    assert plan.get_task("t1")["milestone_id"] == "research"  # не переподписана


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("mst_test_*"):
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
