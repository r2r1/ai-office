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


# ── Генератор шкалы оттенков (design tokens) ────────────────────────────────

def test_color_scale_500_equals_base_hex():
    scale = design_style.generate_color_scale("#3D5AFE")
    assert scale[500] == "#3D5AFE"


def test_color_scale_all_steps_present_and_valid_hex():
    scale = design_style.generate_color_scale("#C4592E")
    assert set(scale.keys()) == set(design_style._SCALE_STEPS)
    for hexv in scale.values():
        assert hexv.startswith("#") and len(hexv) == 7
        int(hexv[1:], 16)  # не бросает — валидный hex


def test_color_scale_darkens_monotonically_above_500():
    """600→900 должны становиться темнее (ниже яркость), не хаотично."""
    scale = design_style.generate_color_scale("#5B8C3E")
    brightness = [sum(int(scale[s][i:i+2], 16) for i in (1, 3, 5)) for s in (500, 600, 700, 800, 900)]
    assert brightness == sorted(brightness, reverse=True), brightness


def test_color_scale_lightens_toward_50():
    """50 должен быть светлее (выше суммарная яркость), чем 400."""
    scale = design_style.generate_color_scale("#2A8C93")
    b50 = sum(int(scale[50][i:i+2], 16) for i in (1, 3, 5))
    b400 = sum(int(scale[400][i:i+2], 16) for i in (1, 3, 5))
    assert b50 > b400


def test_all_directions_have_accent_hex():
    for name in design_style.DIRECTIONS:
        assert name in design_style.ACCENT_HEX, f"нет ACCENT_HEX для {name!r}"
        hexv = design_style.ACCENT_HEX[name]
        assert hexv.startswith("#") and len(hexv) == 7


def test_ensure_design_tokens_self_heals_and_is_idempotent():
    ctx.set_tenant("ds_unit_tokens")
    content = design_style.ensure_design_tokens("натяжной потолок", "новостройки")
    assert "design-tokens" in content
    assert "--accent-500" in content
    again = design_style.ensure_design_tokens("натяжной потолок", "новостройки")
    assert again.count("design-tokens") == 1
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_ensure_design_tokens_uses_same_direction_as_style_line():
    """Токены и «Стиль: …» не должны разъезжаться по разным направлениям."""
    ctx.set_tenant("ds_unit_tokens_consistency")
    workspace.write_file("docs/site_content.md", "Стиль: Прибрежное спокойствие — тест\n\nТекст")
    content = design_style.ensure_design_tokens("случайная ниша не совпадающая с направлением")
    accent = design_style.ACCENT_HEX["Прибрежное спокойствие"]
    assert f"--accent-500: {accent}" in content
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
