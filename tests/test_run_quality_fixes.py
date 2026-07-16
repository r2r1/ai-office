"""
Регрессия багов прогона ai-office-log-20260704_014454 (marco-kmv.ru):

1. «Давайте посмотрим…» сдавалось как результат задачи и публиковалось как описание
   правки сайта → acceptance._is_process_chatter + llm (преамбула ≠ final_text).
2. Ниша «то же самое, что и на сайте» доходила до всех промптов, критик ВЫДУМАЛ
   бизнес («ремонт квартир» вместо доходной недвижимости) → summary_line включает
   title/meta_description автоскана в бриф. (Исходный фикс жил в
   onboarding.build_brief_structured — удалён в Фазе 6 first-investigation-plan
   вместе со всем MODES-интервью; сама причина бага — обходится по-другому: живой
   агент в office/investigation.py верифицирует бизнес через web_search вместо
   доверия текстовой отсылке "то же самое".)
3. Сайт всегда строился на vanilla HTML → сначала лечили ротацией 4 стеков
   (design_style.STACKS + Vue/Alpine скиллы), потом консолидировали в ОДИН
   системный стек платформы (React + Vite + Framer Motion, vite_react_site) —
   ротация без пользы разбрасывала баг-классы по 4 скиллам вместо одного набора
   проверок; альтернативный стек клиент подключает сам как установленный скилл.
4. CEO «обновил цель отдела» ×28 при неизменной доске → анти-шум delegate.

    python tests/test_run_quality_fixes.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.office import acceptance, design_style, skills, company_scan
from src.saas import context as ctx


def test_process_chatter_detected():
    # Реальные строки из прод-лога, которыми закрывались задачи
    for bad in (
        "Давайте посмотрим на структуру сайта, чтобы понять, что нужно доработать:",
        "Теперь давайте проверим файл offer.md, чтобы понять оффер компании:",
        "Файл index.html слишком длинный, не могу увидеть полностью. Давайте посмотрим файл metrika.html:",
        "Для выполнения задачи по подключению аналитики мне нужно уточнить у клиента детали по аналитике.",
    ):
        assert acceptance._is_process_chatter(bad), f"не поймано: {bad!r}"


def test_real_reports_not_flagged_as_chatter():
    for good in (
        "Изменения: переписал оффер под владельцев квартир, заменил CTA, добавил кейсы.",
        "Готово: собрал сайт в site/index.html и site/styles.css, форма шлёт POST /api/site-lead.",
        "Исправил site/metrika.html: убрал пустую заглушку, заменил на корректный HTML.",
        # Длинный отчёт со словом «посмотрим» внутри — не реплика, а результат
        "Сделал полный редизайн. " + "Детали правок по секциям. " * 30 + "Посмотрим на метрики через неделю.",
    ):
        assert not acceptance._is_process_chatter(good), f"ложное срабатывание: {good!r}"


def test_summary_line_includes_title_and_description():
    fake = {"ok": True, "url": "https://x.ru",
            "detected": {"title": "MARCO | Эксперты в доходной недвижимости",
                         "meta_description": "Управление арендой и ремонт под ключ."}}
    line = company_scan.summary_line(fake)
    assert "доходной недвижимости" in line
    assert "Управление арендой" in line


def test_no_stack_rotation_helpers_left():
    """Ротация стеков (design_style.STACKS/pick_stack_for/ensure_stack_line)
    удалена вместе с конкурирующими скиллами — платформа держит ОДИН системный
    стек, не выбирает между несколькими на каждую нишу."""
    assert not hasattr(design_style, "STACKS")
    assert not hasattr(design_style, "pick_stack_for")
    assert not hasattr(design_style, "ensure_stack_line")


def test_website_query_routes_to_single_system_skill():
    """Любая формулировка «построить сайт» маршрутизируется в ЕДИНСТВЕННЫЙ
    системный скилл сайта — не разбегается по 4 конкурирующим стекам.
    2026-07-14: роль сборки сайта — только developer (designer вернулась
    отдельной ролью для бренд-бука ДО кода, не строит сайт сама)."""
    for need in ("построить сайт с 3D-эффектами", "сделать премиальный лендинг",
                 "лендинг с анимациями при скролле"):
        got = skills.match(need, role="developer")
        assert got is not None, f"нет скилла под {need!r}"
        assert got.id == "vite_react_site", f"{need!r} → {got.id}, ожидался vite_react_site"


def test_new_skills_registered_with_form_requirements():
    for sid in ("vite_react_site", "analytics_counter"):
        s = skills.get(sid)
        assert s is not None, f"скилл {sid} не зарегистрирован"
    assert "/api/site-lead" in skills.get("vite_react_site").playbook
    assert "metrika.html" in skills.get("analytics_counter").playbook


def test_removed_competing_stack_skills_not_registered():
    """Alpine/Vue/vanilla/esm.sh-3D скиллы убраны — один системный стек сайта."""
    for sid in ("alpine_tailwind_landing", "static_landing_site",
                "vue_landing_site", "framer_motion_3d_site"):
        assert skills.get(sid) is None, f"скилл {sid} должен быть удалён"


def test_style_line_self_heal_idempotent():
    ctx.set_tenant("style_line_unit")
    from src.office import workspace
    content = design_style.ensure_style_line("кухни", "семьи")
    assert "Стиль:" in content
    again = design_style.ensure_style_line("кухни", "семьи")
    assert again.count("Стиль:") == 1
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_task_context_contains_stack_hint_for_developer_only():
    """Подсказка про стек (текст зависит от site_builder.build_allowed() — сборка
    вкл/выкл — но она всегда присутствует) — ТОЛЬКО у developer, единственной
    роли, которая строит сайт. 2026-07-14: designer вернулась отдельной ролью
    (бренд-бук ДО кода, roles.py.ROLE_META["designer"]) — раньше подсказка
    ошибочно шла и ей (когда designer была алиасом developer), что толкало её
    строить сайт самой, нарушая границу артефактов (plan._derive_artifacts)."""
    ctx.set_tenant("stack_hint_unit")
    from src.saas import context
    context.write_json("brief.json", {"niche": "кухни", "goal": "сайт", "audience": "семьи"})
    from src.office import prompt_builder
    tc = prompt_builder.task_context("developer", "сделай сайт")
    assert "use_skill" in tc and ("системным стеком" in tc or "сборка" in tc.lower())
    tc_marketer = prompt_builder.task_context("marketer", "напиши оффер")
    assert "React + Vite + Framer Motion" not in tc_marketer
    tc_designer = prompt_builder.task_context("designer", "выбери направление")
    assert "React + Vite + Framer Motion" not in tc_designer
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
    # Windows-консоль часто в cp1251 — "✓" ронял ЛЮБОЙ тест этого файла
    # UnicodeEncodeError ДО единой строки реального результата (found: весь
    # набор tests/*.py был непроверяем из этой сессии на Windows).
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    _run()
