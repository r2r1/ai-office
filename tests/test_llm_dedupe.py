"""
Тест _dedupe_repeated_output (src/core/llm.py) — реальный баг из живого аудита
(functional-gaps-round2-2026-07-20.md, U2-побочная): модель иногда отдаёт
итоговый ответ, задвоенный дословно без разделителя.

    python tests/test_llm_dedupe.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.llm import _dedupe_repeated_output, _build_user_message


def test_exact_duplicate_no_separator_is_trimmed():
    a = ("Принял, но сейчас в приоритете именно текущая задача из офиса: "
         "тексты кнопок и автоответ подтверждения для бота.")
    doubled = a + a
    assert _dedupe_repeated_output(doubled) == a


def test_duplicate_with_space_separator_is_trimmed():
    a = "Готово, файл записан в docs/offer.md, можно смотреть результат."
    doubled = a + " " + a
    assert _dedupe_repeated_output(doubled) == a


def test_short_text_is_left_untouched():
    short = "Ок, сделал."
    assert _dedupe_repeated_output(short) == short


def test_non_repeated_text_is_left_untouched():
    text = ("Первая часть ответа про одно. Вторая часть ответа совсем про "
            "другое, никакого повтора здесь нет вообще.")
    assert _dedupe_repeated_output(text) == text


def test_legitimately_repetitive_short_phrase_is_not_falsely_trimmed():
    # "Да да да" — намеренный повтор короткой фразы (< 40 символов) не должен резаться
    text = "Да да да, всё сделано!"
    assert _dedupe_repeated_output(text) == text


# ── _build_user_message (round2 audit, раунд1 #2b — загрузка фото + vision) ──

def test_build_user_message_without_images_is_plain_string():
    msg = _build_user_message("привет", None)
    assert msg == {"role": "user", "content": "привет"}


def test_build_user_message_with_images_uses_content_array():
    msg = _build_user_message("что на фото?", ["data:image/png;base64,AAAA"])
    assert msg["role"] == "user"
    assert isinstance(msg["content"], list)
    assert msg["content"][0] == {"type": "text", "text": "что на фото?"}
    assert msg["content"][1] == {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}


def test_build_user_message_empty_text_with_image_gets_default_prompt():
    msg = _build_user_message("", ["data:image/png;base64,AAAA"])
    assert msg["content"][0]["text"] == "Что на изображении?"


def test_build_user_message_caps_at_four_images():
    urls = [f"data:image/png;base64,{i}" for i in range(10)]
    msg = _build_user_message("много фото", urls)
    image_parts = [c for c in msg["content"] if c["type"] == "image_url"]
    assert len(image_parts) == 4


def test_build_user_message_empty_image_list_is_plain_string():
    msg = _build_user_message("привет", [])
    assert msg == {"role": "user", "content": "привет"}


def _run():
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
            passed += 1
    print(f"ВСЕ {passed} ТЕСТОВ ПРОШЛИ")


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    _run()
