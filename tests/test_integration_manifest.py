"""
Манифест провайдера — поле produces_facts (docs/implementation-prompt.md §3.7,
docs/ai-office-canonical-spec.md §5.3, docs/product-portrait-2026-07-19.md §24):
интеграция декларирует, какие Facts она УМЕЕТ поставлять в World Model.

Проверяем: (1) дефолт — пустой список, старые интеграции без объявления не
ломаются; (2) to_public() сериализует поле для фронта/каталога; (3) провайдеры
с реальным read-действием (gmail/google_calendar/google_sheets) декларируют
непустой список; (4) export-only провайдеры (crm/crm_bitrix24/erp_1c — только
пишут лид наружу, не читают статус обратно) НЕ декларируют факты — честность
каталога важнее полноты.

    python tests/test_integration_manifest.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="backslashreplace")

os.environ.setdefault("DEMO_MODE", "1")


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(("[ok] " if cond else "[FAIL] ") + name)
        if not cond:
            failures.append(name)

    from src.integrations.base import Integration, Action

    async def _noop(creds, params):
        return "ok"

    bare = Integration(name="x", title="X", icon="x", description="d", how_to="h")
    check("дефолт produces_facts — пустой список", bare.produces_facts == [])
    check("to_public() сериализует produces_facts",
          bare.to_public()["produces_facts"] == [])

    declared = Integration(name="y", title="Y", icon="y", description="d", how_to="h",
                           produces_facts=["занятость по календарю"])
    check("непустой produces_facts проходит в to_public()",
          declared.to_public()["produces_facts"] == ["занятость по календарю"])

    from src.integrations.registry import all_integrations
    by_name = {i.name: i for i in all_integrations()}

    for name in ("gmail", "google_calendar", "google_sheets"):
        integ = by_name.get(name)
        check(f"{name} зарегистрирован в реестре", integ is not None)
        if integ:
            check(f"{name} декларирует хотя бы один Fact (реальное read-действие)",
                  len(integ.produces_facts) > 0)

    for name in ("crm", "crm_bitrix24", "erp_1c", "bitrix24"):
        integ = by_name.get(name)
        check(f"{name} зарегистрирован в реестре", integ is not None)
        if integ:
            check(f"{name} НЕ декларирует факты (export-only, нечего читать)",
                  integ.produces_facts == [])

    print()
    if failures:
        print(f"ПРОВАЛЕНО: {len(failures)}")
        return 1
    print("Все проверки манифеста провайдера прошли.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
