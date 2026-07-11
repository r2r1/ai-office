"""
Тесты department-скоупа для Integration (BOS: модуль соответствует своему
отделу) + отдела finance (cfo/accountant) — раньше любая роль могла дёрнуть
ЛЮБУЮ интеграцию, у которой технически есть креды, независимо от того, что
она делает (1С мог вызвать salesman). Integration.department=""  (по
умолчанию) — общий доступ, прежнее поведение НЕ меняется; заполнено —
только своя роль или portfolio-роль (CEO/лидер/штаб).

    python tests/test_department_scope.py
"""

import asyncio
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv()

from src.saas import context as ctx
from src.office import org
from src.office import roles as roles_module
from src.integrations import erp_1c
from src.agents import integration_tool_handlers


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


def _run(coro):
    return asyncio.run(coro)


def _handlers(role: str, agent_id="a1"):
    events = []

    async def _publish(ev):
        events.append(ev)

    return integration_tool_handlers.build(agent_id, role, _publish, _publish), events


# ── org/roles: отдел finance зарегистрирован корректно ─────────────────────

def test_finance_department_registered():
    assert "finance" in org.DEPARTMENTS
    assert org.lead_role("finance") == "cfo"
    assert org.lead_title("finance") == "CFO"


def test_accountant_is_member_not_lead():
    assert org.member_roles("finance") == ["accountant"]
    assert roles_module.department_of("cfo") == "finance"
    assert roles_module.department_of("accountant") == "finance"


def test_cfo_is_portfolio_role_lead_is_not_gated():
    assert org.is_portfolio_role("cfo") is True
    assert "cfo" in org.LEAD_ROLES


def test_erp_integration_has_finance_department():
    assert erp_1c.INTEGRATION.department == "finance"


# ── гейт исполнения: чужая роль блокируется, своя/portfolio — проходит ─────

def test_unrelated_role_blocked_from_finance_integration():
    _fresh("dept_test_blocked")
    handlers, _ = _handlers("salesman")
    result = _run(handlers["use_integration"]({
        "name": "erp_1c", "action": "check_connection", "params": {},
    }))
    assert "отдел" in result.lower()
    assert "CFO" in result


def test_own_department_role_passes_gate():
    """accountant проходит гейт — дальше упирается в обычную нехватку кредов
    (не в блокировку по отделу): сообщение про отдел отсутствует."""
    _fresh("dept_test_own_role")
    handlers, _ = _handlers("accountant")
    result = _run(handlers["use_integration"]({
        "name": "erp_1c", "action": "check_connection", "params": {},
    }))
    assert "закреплена за отделом" not in result
    assert "не подключён" in result.lower() or "how_to" in result.lower() or "1С" in result


def test_portfolio_role_bypasses_gate_even_from_other_department():
    """CEO (orchestrator) видит бизнес целиком — гейт его не касается, даже
    хотя формально orchestrator не относится ни к одному отделу."""
    _fresh("dept_test_ceo_bypass")
    handlers, _ = _handlers("orchestrator")
    result = _run(handlers["use_integration"]({
        "name": "erp_1c", "action": "check_connection", "params": {},
    }))
    assert "закреплена за отделом" not in result


def test_lead_role_of_other_department_bypasses_gate():
    """CTO — лидер ДРУГОГО отдела (tech), но лидеры — portfolio-роли, гейт их
    не блокирует (в отличие от рядового работника tech)."""
    _fresh("dept_test_lead_bypass")
    handlers, _ = _handlers("cto")
    result = _run(handlers["use_integration"]({
        "name": "erp_1c", "action": "check_connection", "params": {},
    }))
    assert "закреплена за отделом" not in result


def test_department_empty_integration_available_to_any_role_as_before():
    """Регрессия: интеграция БЕЗ department (website — как раньше) доступна
    любой роли — инвариант "общие доступы" не тронут."""
    _fresh("dept_test_shared_integration")
    handlers, _ = _handlers("salesman")
    result = _run(handlers["use_integration"]({
        "name": "website", "action": "list_pages", "params": {},
    }))
    assert "закреплена за отделом" not in result


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("dept_test_*"):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)


def _run_all():
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
    _run_all()
