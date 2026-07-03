"""
Регрессия: борьба с «все сайты одинаковые» (см. handoff.md).

Эмпирическая находка при разборе прод-лога: `use_skill` designer/developer/
marketer в реальных прогонах ВСЕГДА матчился на `landing_conversion` (7 из 7
вызовов в разобранном логе), `static_landing_site` не был выбран НИ РАЗУ —
значит его инструкции (дизайн-токены, каталог направлений, вариативность
стека) почти никогда не доходили до модели. Фикс: каталог именованных стилей
переехал в `landing_conversion.md` (реально читаемый файл) + explicit
cross-reference на `static_landing_site` за дизайн-токенами/esm.sh-библиотеками.

    python tests/test_design_skills.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.office import skills


def test_landing_conversion_has_style_catalog():
    s = skills.get("landing_conversion")
    assert s is not None
    # Каталог направлений присутствует (хотя бы несколько именованных стилей).
    for name in ("Терракотовый ремесленный", "Графитовый индастриал", "Свежий фермерский"):
        assert name in s.playbook, f"направление {name!r} пропало из каталога"
    # Cross-reference на дизайн-токены static_landing_site не потерян при правках.
    assert "Премиальный сайт (без 3D)" in s.playbook


def test_realistic_agent_query_matches_landing_conversion():
    """Реалистичный текст потребности (как реально формулирует designer/developer)
    матчится на landing_conversion — это и есть причина, почему его контент должен
    содержать всё критичное для дизайна (каталог), а не только структуру секций."""
    need = "продающий лендинг для владельцев квартир в новостройках с оффером и CTA"
    m = skills.match(need, "designer")
    assert m is not None and m.id == "landing_conversion"


def test_explicit_query_still_reaches_static_landing_site():
    """Явный запрос за дизайн-токенами (как теперь инструктирует landing_conversion
    в cross-reference) обязан достучаться до static_landing_site — иначе
    инструкция-ссылка бессмысленна."""
    need = "премиальный статический сайт дизайн-токены"
    m = skills.match(need, "designer")
    assert m is not None and m.id == "static_landing_site"


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
