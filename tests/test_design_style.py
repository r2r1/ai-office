"""
Регрессия: детерминированный self-heal направления стиля (см. handoff.md).

Прод-находка: инструкция в скилле («marketer пишет «Стиль: …», designer читает»)
не гарантия — в реальном прогоне marketer пропустил шаг под давлением токенов,
designer не спросил коллегу, сайт строился по дефолтам модели одинаково для
любой ниши. `design_style.ensure_style_line` закрывает это детерминированно,
без LLM: если строки нет — код сам ставит её (стабильный выбор по нише), $0.

    python tests/test_design_style.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.office import design_style, workspace
from src.saas import context as ctx


def test_pick_for_is_deterministic_across_calls():
    assert design_style.pick_for("натяжной потолок", "новостройки") == \
        design_style.pick_for("натяжной потолок", "новостройки")


def test_pick_for_spreads_across_different_niches():
    niches = ["натяжной потолок", "юридические услуги", "кофейня",
              "автосервис", "детский сад", "ювелирный магазин"]
    picks = {design_style.pick_for(n) for n in niches}
    assert len(picks) >= 4, "разные ниши не должны массово сходиться в одно направление"


def test_names_match_landing_conversion_catalog():
    """Machine-readable список должен 1:1 совпадать с человекочитаемым каталогом
    в builtin_skills/landing_conversion.md — иначе designer декодирует «Стиль: X»
    в несуществующее направление."""
    skill_md = (Path(__file__).resolve().parents[1] /
                "src/office/builtin_skills/landing_conversion.md").read_text(encoding="utf-8")
    for name in design_style.DIRECTIONS:
        assert name in skill_md, f"направление {name!r} есть в design_style.py, но не в скилле"


def test_ensure_style_line_self_heals_when_missing():
    ctx.set_tenant("ds_unit_heal")
    d = design_style.pick_for("натяжной потолок", "новостройки")
    content = design_style.ensure_style_line("натяжной потолок", "новостройки")
    assert content.startswith(f"Стиль: {d}")
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_ensure_style_line_is_idempotent_when_marketer_wrote_it():
    ctx.set_tenant("ds_unit_idempotent")
    workspace.write_file("docs/site_content.md", "Стиль: Монохромный люкс — моё решение\n\nТекст")
    content = design_style.ensure_style_line("любая ниша")
    assert content.startswith("Стиль: Монохромный люкс — моё решение")
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
