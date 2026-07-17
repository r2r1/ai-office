"""
Юнит-тесты Acceptance Layer (src/office/acceptance.py) — напрямую, не только
косвенно через test_execution.py (см. docs/prompts/system-audit-prompt.md,
раздел «Путь до идеального SaaS», Шаг 4: acceptance.py/world.py без прямого
покрытия — единственная защита инварианта «задача закрывается только через
приёмку» рисковала сломаться незамеченной при будущем рефакторинге).

    python tests/test_acceptance.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import acceptance, workspace


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


def test_empty_result_fails_acceptance():
    _fresh("acc_test_empty")
    v = acceptance.check("task", "marketer", "")
    assert not v["passed"]
    assert v["levels"]["acceptance"] == "fail"
    assert any("пуст" in p for p in v["problems"])


def test_process_chatter_fails_acceptance():
    _fresh("acc_test_chatter")
    v = acceptance.check("task", "marketer", "Давайте посмотрим на структуру сайта")
    assert not v["passed"]
    assert v["levels"]["acceptance"] == "fail"


def test_trailing_colon_counts_as_chatter():
    _fresh("acc_test_colon")
    v = acceptance.check("task", "marketer", "Сейчас проверю файл offer.md:")
    assert not v["passed"]


def test_real_report_not_flagged_as_chatter():
    _fresh("acc_test_real_report")
    v = acceptance.check("task", "marketer", "Собрал оффер и 3 варианта CTA в docs/offer.md")
    assert v["passed"]
    assert v["levels"]["acceptance"] == "ok"


def test_non_coding_role_skips_build_level():
    _fresh("acc_test_skip_build")
    v = acceptance.check("task", "marketer", "Готов текст оффера", artifacts=["doc"])
    assert v["levels"]["build"] == "skip"


def test_coding_role_with_broken_python_fails_build():
    _fresh("acc_test_broken_py")
    workspace.write_file("main.py", "def broken(:\n    pass")
    v = acceptance.check("task", "developer", "Написал main.py")
    assert v["levels"]["build"] == "fail"
    assert not v["passed"]
    assert any("код:" in p for p in v["problems"])


def test_coding_role_with_valid_python_passes_build():
    _fresh("acc_test_valid_py")
    workspace.write_file("main.py", "def ok():\n    return 1\n")
    v = acceptance.check("task", "developer", "Написал main.py")
    assert v["levels"]["build"] == "ok"
    assert v["passed"]


def test_coding_role_with_no_files_skips_build():
    """workspace.list_files() пуст → L2 не гейтит (нечего проверять компиляцией)."""
    _fresh("acc_test_no_files")
    v = acceptance.check("task", "developer", "Только обсудили план, файлов ещё нет")
    assert v["levels"]["build"] == "skip"


def test_business_level_open_when_gap_unmet():
    """L4 не гейтит (informational-only) — задача проходит, даже если бизнес-цель
    не достигнута, но levels['business'] сигналит 'open', не 'ok'."""
    _fresh("acc_test_business_open")
    from src.office import objectives, metrics as metrics_mod
    objectives.add("Заявки с сайта в неделю", desired="10 заявок/неделю",
                   measured_by="leads.count() за 7 дней", source="company")
    # metrics.latest("leads_7d") без snapshot вернёт 0 → gap = 10 - 0 = 10 > 0 → unmet
    v = acceptance.check("task", "developer", "Сайт опубликован", artifacts=["site"])
    assert v["passed"]  # L4 не должен проваливать приёмку
    assert v["levels"]["business"] == "open"
    assert any("разрыв" in w for w in v["warnings"])


def test_business_level_skipped_for_non_deliverable_task():
    """Задача без артефакта site/bot не проверяется на L4 вообще (не relevantна)."""
    _fresh("acc_test_business_skip")
    v = acceptance.check("task", "analyst", "Собрал отчёт по рынку", artifacts=["doc"])
    assert v["levels"]["business"] == "skip"


def test_designer_task_fails_without_ask_user():
    """Аудит логов 2026-07-17: designer выбирал стиль сам, ни разу не спросив
    владельца, хотя brand_book.md текстом требует ask_user. Программный гейт:
    без реального вызова questions.ask() этим агентом задача не проходит приёмку."""
    _fresh("acc_test_designer_no_ask")
    v = acceptance.check("Выбрать визуальное направление", "designer",
                          "Готово: зафиксировал стиль в docs/brand_book.md",
                          artifacts=["doc"], agent_id="designer_1")
    assert not v["passed"]
    assert any("не подтверждено владельцем" in p for p in v["problems"])


def test_designer_task_passes_after_ask_user():
    _fresh("acc_test_designer_asked")
    from src.office import questions
    import asyncio
    import time

    async def _run():
        started = time.time() - 5
        qid, fut = questions.ask("Какой стиль вам ближе: А, Б или В?",
                                  agent_id="designer_1")
        v = acceptance.check("Выбрать визуальное направление", "designer",
                              "Готово: зафиксировал стиль в docs/brand_book.md по ответу владельца",
                              artifacts=["doc"], started_ts=started, agent_id="designer_1")
        fut.cancel()
        return v

    v = asyncio.run(_run())
    assert v["passed"]


def test_claims_need_client_input_but_never_asked_fails():
    """Аудит логов 2026-07-17: integrator сдал «нужно получить от клиента номер
    счётчика Яндекс.Метрики», ни разу не вызвав ask_user — приёмка это пропустила."""
    _fresh("acc_test_needs_input_not_asked")
    v = acceptance.check("task", "integrator",
                          "Нужно получить от клиента номер счётчика Яндекс.Метрики — "
                          "без него не смогу подключить аналитику.",
                          agent_id="integrator_1")
    assert not v["passed"]
    assert any("вопрос ему не" in p for p in v["problems"])


def test_claims_need_client_input_but_actually_asked_passes():
    _fresh("acc_test_needs_input_asked")
    from src.office import questions
    import asyncio
    import time

    async def _run():
        started = time.time() - 5
        qid, fut = questions.ask("Какой номер счётчика Яндекс.Метрики использовать?",
                                  agent_id="integrator_1")
        v = acceptance.check("task", "integrator",
                              "Нужно получить от клиента номер счётчика Яндекс.Метрики — "
                              "без него не смогу подключить аналитику.",
                              started_ts=started, agent_id="integrator_1")
        fut.cancel()
        return v

    v = asyncio.run(_run())
    assert v["passed"]


def test_feedback_text_empty_when_passed():
    _fresh("acc_test_feedback_pass")
    v = acceptance.check("task", "marketer", "Готово, оффер в docs/offer.md")
    assert acceptance.feedback_text(v) == ""


def test_feedback_text_lists_problems_when_failed():
    _fresh("acc_test_feedback_fail")
    v = acceptance.check("task", "marketer", "")
    fb = acceptance.feedback_text(v)
    assert "ПРИЁМКА НЕ ПРОЙДЕНА" in fb
    assert "пуст" in fb


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("acc_test_*"):
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
