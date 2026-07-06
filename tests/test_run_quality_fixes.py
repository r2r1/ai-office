"""
Регрессия багов прогона ai-office-log-20260704_014454 (marco-kmv.ru):

1. «Давайте посмотрим…» сдавалось как результат задачи и публиковалось как описание
   правки сайта → acceptance._is_process_chatter + llm (преамбула ≠ final_text).
2. Ниша «то же самое, что и на сайте» доходила до всех промптов, критик ВЫДУМАЛ
   бизнес («ремонт квартир» вместо доходной недвижимости) → onboarding подставляет
   title/meta_description из автоскана; summary_line включает их.
3. Сайт всегда строился на vanilla HTML → детерминированная ротация стеков
   (design_style.STACKS) + новые скиллы Vue/Alpine; каждый лейбл стека
   маршрутизируется use_skill в СВОЙ скилл.
4. CEO «обновил цель отдела» ×28 при неизменной доске → анти-шум delegate.

    python tests/test_run_quality_fixes.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.office import acceptance, design_style, skills, company_scan
from src.agents import onboarding
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


def test_self_referential_niche_enriched_from_scan():
    """«то же самое, что и на сайте» → реальное описание бизнеса из скана."""
    answers = [
        {"dimension": "product", "answer": "то же самое, что и на сайте"},
        {"dimension": "client", "answer": "владельцы квартир"},
        {"dimension": "goal", "answer": "новый сайт"},
    ]
    scan = {"ok": True, "url": "https://marco-kmv.ru/",
            "detected": {"title": "MARCO | Эксперты в доходной недвижимости",
                         "meta_description": "MARCO — эксперты в доходной недвижимости. "
                                             "Управление посуточной и долгосрочной арендой."}}
    brief = onboarding.build_brief_structured("business", answers, scan_result=scan)
    assert "доходной недвижимости" in brief["niche"], brief["niche"]
    # Сырой ответ клиента сохранён рядом — вдруг он имел в виду что-то ещё
    assert "то же самое" in brief["niche"]


def test_meaningful_product_not_replaced_by_scan():
    answers = [{"dimension": "product", "answer": "Натяжные потолки под ключ"}]
    scan = {"ok": True, "detected": {"title": "Другой заголовок"}}
    brief = onboarding.build_brief_structured("business", answers, scan_result=scan)
    assert brief["niche"].startswith("Натяжные потолки")


def test_summary_line_includes_title_and_description():
    fake = {"ok": True, "url": "https://x.ru",
            "detected": {"title": "MARCO | Эксперты в доходной недвижимости",
                         "meta_description": "Управление арендой и ремонт под ключ."}}
    line = company_scan.summary_line(fake)
    assert "доходной недвижимости" in line
    assert "Управление арендой" in line


def test_stack_rotation_deterministic_and_diverse():
    assert design_style.pick_stack_for("кухни") == design_style.pick_stack_for("кухни")
    picked = {design_style.pick_stack_for(n) for n in
              ("кухни", "потолки", "стоматология", "автосервис", "доходная недвижимость",
               "цветы", "фитнес", "юрист")}
    assert len(picked) >= 2, f"ротация выродилась в один стек: {picked}"


def test_each_stack_label_routes_to_own_skill():
    """use_skill с текстом лейбла стека должен попадать в СВОЙ скилл — иначе
    ротация бессмысленна (всё снова свалится в static_landing_site)."""
    expected = {
        "Vanilla HTML/CSS/JS": "static_landing_site",
        "React 18 + framer-motion": "framer_motion_3d_site",
        "Vue 3 через esm.sh": "vue_landing_site",
        "Alpine.js + Tailwind": "alpine_tailwind_landing",
    }
    for label, skill_id in expected.items():
        stack = next(s for s in design_style.STACKS if s.startswith(label.split()[0]))
        got = skills.match(f"построить сайт: {stack}", role="designer")
        assert got is not None, f"нет скилла под {label}"
        assert got.id == skill_id, f"{label} → {got.id}, ожидался {skill_id}"


def test_new_skills_registered_with_form_requirements():
    for sid in ("vue_landing_site", "alpine_tailwind_landing", "analytics_counter"):
        s = skills.get(sid)
        assert s is not None, f"скилл {sid} не зарегистрирован"
    assert "/api/site-lead" in skills.get("vue_landing_site").playbook
    assert "/api/site-lead" in skills.get("alpine_tailwind_landing").playbook
    assert "metrika.html" in skills.get("analytics_counter").playbook


def test_stack_line_self_heal_idempotent():
    ctx.set_tenant("stack_line_unit")
    from src.office import workspace
    content = design_style.ensure_stack_line("кухни", "семьи")
    assert "Стек:" in content
    again = design_style.ensure_stack_line("кухни", "семьи")
    assert again.count("Стек:") == 1
    # Стиль и стек сосуществуют в одном файле
    design_style.ensure_style_line("кухни", "семьи")
    final = workspace.read_file("docs/site_content.md")
    assert "Стиль:" in final and "Стек:" in final
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_task_context_contains_stack_hint_for_designer():
    ctx.set_tenant("stack_hint_unit")
    from src.saas import context
    context.write_json("brief.json", {"niche": "кухни", "goal": "сайт", "audience": "семьи"})
    from src.office import prompt_builder
    tc = prompt_builder.task_context("designer", "сделай сайт")
    assert "Рекомендованный стек" in tc
    tc_marketer = prompt_builder.task_context("marketer", "напиши оффер")
    assert "Рекомендованный стек" not in tc_marketer
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
