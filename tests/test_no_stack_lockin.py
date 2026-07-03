"""
Регрессия: роли/ТЗ архитектора НЕ диктуют технический стек типовых артефактов
(сайт/лендинг/бот) — стек/техника исполнения живут ТОЛЬКО в скиллах
(engineering-principles.md №10 «Роль описывает кто/что нельзя. Способ живёт в
Skill»; BOS §7).

Прод-находка: `policies/architect.md` жёстко предписывал «Сайт = HTML5 + CSS3 +
Vanilla JS» — это ТЗ подмешивается в контекст КАЖДОЙ задачи воркера
(prompt_builder.task_context), поэтому designer/developer видели стек как «уже
решено» и не шли в use_skill (framer_motion_3d_site и др.) — вся цепочка
сходилась к одному стеку независимо от ниши/скилла. Аналогично `policies/
ceo_plan.md` зашивал «(HTML/CSS/JS)» в описание роли designer для генератора
плана. Оба места переписаны так, что стек типовых артефактов явно делегируется
use_skill; архитектор называет стек только для КАСТОМНОЙ логики без скилла.

    python tests/test_no_stack_lockin.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.office import prompt_builder

# Литералы стека, которые не должны диктоваться ролью/ТЗ для ТИПОВЫХ артефактов
# (сайт/лендинг) — они принадлежат скиллам (framer_motion_3d_site, static_landing_site).
_STACK_LOCKIN_PHRASES = ("HTML5 + CSS3 + Vanilla JS", "HTML/CSS/JS)")


def test_architect_policy_delegates_stack_to_skills():
    p = prompt_builder.policy("architect")
    for phrase in _STACK_LOCKIN_PHRASES:
        assert phrase not in p, f"архитектор снова диктует стек: {phrase!r}"
    assert "use_skill" in p, "архитектор должен явно делегировать стек use_skill"


def test_ceo_plan_policy_does_not_hardcode_designer_stack():
    p = prompt_builder.policy("ceo_plan")
    for phrase in _STACK_LOCKIN_PHRASES:
        assert phrase not in p, f"ceo_plan снова диктует стек designer'у: {phrase!r}"


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
