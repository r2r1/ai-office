"""
Тесты state._truncate_label/save_deliverable — реальный баг с UI-скриншота:
подпись артефакта "ЗАДАЧА ВЫПОЛНЕНА, КОГД" обрывалась прямо посреди слова
"КОГДА", потому что каждый вызывающий (agent_factory.py, execution.py)
резал составную строку (заголовок + "\n✅ ЗАДАЧА ВЫПОЛНЕНА, КОГДА: ...")
сырым text[:80]. Обрезка теперь единая — внутри save_deliverable, по
границе слова.

    python tests/test_state_deliverables.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import state


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


def test_truncate_label_short_text_unchanged():
    assert state._truncate_label("короткий заголовок") == "короткий заголовок"


def test_truncate_label_cuts_at_word_boundary_not_mid_word():
    text = ("Подключить аналитику и проверку приема заявок\n"
            "✅ ЗАДАЧА ВЫПОЛНЕНА, КОГДА: На сайт подключен счётчик аналитики.")
    result = state._truncate_label(text, limit=80)
    # не обрывается посреди слова "КОГДА" (реальный баг: "...КОГД" без "А")
    assert "КОГД " not in result and not result.rstrip("…").endswith("КОГД")
    assert result.endswith("…")
    assert len(result) <= 82  # лимит + многоточие, без резкого перебора


def test_truncate_label_no_nearby_space_falls_back_to_hard_cut():
    """Если пробела рядом нет вообще (одно длинное слово) — не режем в ноль,
    падаем на обычную обрезку по символу, лучше так, чем пустая строка."""
    text = "а" * 200
    result = state._truncate_label(text, limit=80)
    assert result == "а" * 80 + "…"


def test_save_deliverable_truncates_composite_task_string():
    _fresh("state_test_truncate")
    task = ("Собрать и опубликовать лендинг с посадочными блоками под КМВ\n"
            "✅ ЗАДАЧА ВЫПОЛНЕНА, КОГДА: Лендинг опубликован, содержит оффер, "
            "преимущества, города покрытия, формы заявки/кнопки звонка.")
    state.save_deliverable("dev_1", "developer", task, "готово")
    d = state._load()["deliverables"][0]
    assert d["task"].endswith("…")
    assert not d["task"].rstrip("…").endswith("КОГД")


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("state_test_*"):
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
