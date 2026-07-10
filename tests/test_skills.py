"""
Тесты skills.py — match()/suggestions() покрывались только через реальные
встроенные скиллы попутно (в других тестах), сама развилка "нет явного
лидера → suggestions(), не match()" не проверялась явно.

    python tests/test_skills.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.office import skills


def _register_temp(skill: skills.Skill):
    """Регистрирует скилл на время теста и возвращает функцию отката —
    _BUILTIN общий на процесс, тесты не должны загрязнять друг друга."""
    existed = skills._BUILTIN.get(skill.id)
    skills.register(skill)

    def _restore():
        if existed is not None:
            skills._BUILTIN[skill.id] = existed
        else:
            skills._BUILTIN.pop(skill.id, None)
    return _restore


def test_match_returns_none_when_nothing_scores():
    assert skills.match("совершенно непересекающийся запрос про погоду xyzzy", role="__nonexistent_role__") is None


def test_match_picks_highest_scoring_skill():
    restore_a = _register_temp(skills.Skill(
        id="__test_skill_a", title="Skill A", description="тест",
        keywords=["уникальныйтест", "второе"], roles=["__test_role"],
    ))
    restore_b = _register_temp(skills.Skill(
        id="__test_skill_b", title="Skill B", description="тест",
        keywords=["уникальныйтест"], roles=["__test_role"],
    ))
    try:
        best = skills.match("уникальныйтест второе слово", role="__test_role")
        assert best is not None
        assert best.id == "__test_skill_a"  # больше совпадений keywords
    finally:
        restore_a()
        restore_b()


def test_suggestions_returns_ranked_top_n_when_ambiguous():
    """Когда несколько скиллов подходят примерно одинаково — suggestions()
    отдаёт топ-N по убыванию score, а не молчит."""
    restore_a = _register_temp(skills.Skill(
        id="__test_skill_c", title="Skill C", description="тест",
        keywords=["общееслово"], roles=["__test_role2"],
    ))
    restore_b = _register_temp(skills.Skill(
        id="__test_skill_d", title="Skill D", description="тест",
        keywords=["общееслово"], roles=["__test_role2"],
    ))
    restore_c = _register_temp(skills.Skill(
        id="__test_skill_e", title="Skill E", description="тест",
        keywords=["несвязанное"], roles=["__test_role2"],
    ))
    try:
        top = skills.suggestions("общееслово", role="__test_role2", top=3)
        ids = {s.id for s in top}
        assert ids == {"__test_skill_c", "__test_skill_d"}
        assert "__test_skill_e" not in ids  # не совпало — не в выдаче
    finally:
        restore_a()
        restore_b()
        restore_c()


def test_role_filter_excludes_skill_for_other_role():
    restore = _register_temp(skills.Skill(
        id="__test_skill_f", title="Skill F", description="тест",
        keywords=["специфичноеслово"], roles=["__role_only"],
    ))
    try:
        assert skills.match("специфичноеслово", role="__other_role") is None
        assert skills.match("специфичноеслово", role="__role_only") is not None
    finally:
        restore()


def test_negation_penalizes_matched_keyword():
    # keywords уникальные — иначе встроенный publish_landing (roles=[], т.е.
    # виден ВСЕМ ролям) может случайно тоже задеть общеупотребимое слово и
    # победить с положительным score, замаскировав то, что мы проверяем.
    restore = _register_temp(skills.Skill(
        id="__test_skill_g", title="Zzqx-скилл", description="тест",
        keywords=["zzqxвариант"], roles=["__neg_role"],
    ))
    try:
        assert skills.match("сделай проект без zzqxвариант", role="__neg_role") is None
    finally:
        restore()


def _run():
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
            passed += 1
    print(f"ВСЕ {passed} ТЕСТОВ ПРОШЛИ")


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    _run()
