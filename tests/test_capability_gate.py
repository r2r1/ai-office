"""
capability.blocking_for_task() — гейт НА ДИСПЕТЧЕРИЗАЦИИ задачи (production-
readiness worklist п.3): раньше недостающая способность была видна только
один раз при BOOTSTRAP (missing_for_plan), ничего не мешало назначить задачу
исполнителю, который упирался в отсутствие доступа в середине работы.

    python tests/test_capability_gate.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import capability


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


def test_task_without_required_capability_is_never_blocked():
    _fresh("cap_gate_none")
    task = {"id": "t1", "title": "написать текст для соцсетей"}
    assert capability.blocking_for_task(task) == []


def test_task_needing_unconnected_gmail_is_blocked():
    _fresh("cap_gate_email")
    task = {"id": "t2", "title": "отправить письмо клиенту с предложением"}
    missing = capability.blocking_for_task(task)
    assert len(missing) == 1
    assert missing[0]["capability"] == "email"
    assert "hint" in missing[0]["acquire"] or "integration" in missing[0]["acquire"]


def test_task_needing_platform_capability_is_never_blocked():
    """landing_site backed_by="platform" — всегда have, независимо от
    подключений: сайт публикует сам офис, ключи не нужны."""
    _fresh("cap_gate_platform")
    task = {"id": "t3", "title": "опубликовать лендинг", "required_capabilities": ["landing_site"]}
    assert capability.blocking_for_task(task) == []


def test_explicit_required_capabilities_override_title_derivation():
    """task.required_capabilities — явная декларация, приоритетнее вывода
    по словам заголовка (тот же контракт, что required_of/derive_required)."""
    _fresh("cap_gate_explicit")
    task = {"id": "t4", "title": "просто заголовок без ключевых слов",
            "required_capabilities": ["email"]}
    missing = capability.blocking_for_task(task)
    assert len(missing) == 1
    assert missing[0]["capability"] == "email"


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("cap_gate_*"):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)


def _run():
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
    _run()
