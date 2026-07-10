"""
Регрессия: needs.is_bot_reference не должен ложно матчить «бот» внутри
«работать/доработать/обработать» (реальный прод-инцидент — см. handoff.md).

Корневая причина: `_BOT_WORDS`-подстрока «бот» совпадала с корнем «-работ-»
(доработать = до-РА-БОТ-ать). Auto-generated gap-задача marketer'а «Усилить
привлечение заявок: доработать оффер и CTA…» сама содержала слово «доработать»
→ ложно получила artifact=bot → acceptance потребовала bot.py с aiogram/
BOT_TOKEN → 3 провала приёмки → задача заблокирована → у отдела не осталось
другой работы → has_actionable_move() вернул False → офис молча замер без
единого сообщения в ленте (пользователь увидел это как «всё зависло»).

    python tests/test_needs.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.office import needs, plan, capability


# Заголовок ИЗ РЕАЛЬНОГО ИНЦИДЕНТА (gap._work_for_gap создаёт его дословно).
_GAP_TASK_TITLE = ("Усилить привлечение заявок: доработать оффер и CTA лендинга, "
                   "предложить дополнительный канал трафика")

_FALSE_POSITIVE_WORDS = (
    "разработать сайт", "обработать заявки", "заработать больше",
    "отработать смену", "наработать базу", "подработать текст",
    "работать над проектом", "работа над ошибками",
)

_REAL_BOT_MENTIONS = (
    "Настроить и запустить Telegram-бота сбора заявок",
    "Бот для записи клиентов",
    "нужен бота для чата",
    "aiogram интеграция",
    "чат-бот поддержки",
    "телеграм-бот",
)


def test_gap_task_title_is_not_bot():
    assert not needs.is_bot_reference(_GAP_TASK_TITLE)
    assert plan._derive_artifacts("marketer", _GAP_TASK_TITLE) == ["doc"]
    assert capability.derive_required({"title": _GAP_TASK_TITLE}) == []


def test_rabot_root_words_are_not_bot():
    for w in _FALSE_POSITIVE_WORDS:
        assert not needs.is_bot_reference(w), f"ложное срабатывание: {w!r}"


def test_real_bot_mentions_still_detected():
    for w in _REAL_BOT_MENTIONS:
        assert needs.is_bot_reference(w), f"пропущен реальный бот: {w!r}"
    assert capability.derive_required({"title": "Настроить Telegram-бота"}) == ["telegram_bot"]
    assert plan._derive_artifacts("developer", "Настроить Telegram-бота") == ["bot"]


def test_overlap_normalizes_by_union_not_raw_count():
    """Реальный кейс: способность с длинным description не должна побеждать за
    счёт того, что у неё просто больше слов, а не потому что она релевантнее."""
    need = "опубликовать лендинг клиенту"
    short_caps = needs.tokens("website publish_landing опубликовать лендинг сайта")
    long_caps = needs.tokens(
        "crm export_lead выгрузить лида в срм систему учёта клиентов сделки "
        "воронка продаж контакты история переписки менеджер клиент лендинг"
    )
    # У длинной способности случайно есть общее слово "лендинг" — с сырым
    # count пересечение было бы одинаковым/близким, с Jaccard длинная явно проигрывает.
    assert needs.overlap(need, short_caps) > needs.overlap(need, long_caps)


def test_overlap_zero_when_no_intersection():
    assert needs.overlap("что-то совсем другое", needs.tokens("опубликовать лендинг")) == 0.0


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
