"""
Регрессия: борьба с «все сайты одинаковые» (см. handoff.md).

Эмпирическая находка при разборе прод-лога: `use_skill` designer/developer/
marketer в реальных прогонах ВСЕГДА матчился на `landing_conversion` (7 из 7
вызовов в разобранном логе), скилл за дизайн-токенами не был выбран НИ РАЗУ —
значит его инструкции (дизайн-токены, каталог направлений) почти никогда не
доходили до модели. Фикс: каталог именованных стилей переехал в
`landing_conversion.md` (реально читаемый файл) + explicit cross-reference на
`vite_react_site` (единственный системный скилл сайта после консолидации
стеков — Alpine/Vue/vanilla/esm.sh-3D скиллы удалены) за дизайн-токенами.

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
    # Cross-reference на дизайн-токены vite_react_site не потерян при правках.
    assert "React + Vite" in s.playbook and "Motion" in s.playbook


def test_realistic_agent_query_matches_landing_conversion():
    """Реалистичный текст потребности (как реально формулирует designer/developer)
    матчится на landing_conversion — это и есть причина, почему его контент должен
    содержать всё критичное для дизайна (каталог), а не только структуру секций."""
    need = "продающий лендинг для владельцев квартир в новостройках с оффером и CTA"
    m = skills.match(need, "designer")
    assert m is not None and m.id == "landing_conversion"


def test_explicit_query_still_reaches_vite_react_site():
    """Явный запрос за дизайн-токенами (как теперь инструктирует landing_conversion
    в cross-reference) обязан достучаться до vite_react_site — иначе
    инструкция-ссылка бессмысленна."""
    need = "React Vite сайт дизайн-токены"
    m = skills.match(need, "designer")
    assert m is not None and m.id == "vite_react_site"


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
