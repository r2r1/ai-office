"""
Детерминированный фолбэк направления стиля (см. docs/handoff.md, «сайт такой же»).

Прод-находка: инструкция в builtin_skills/landing_conversion.md («marketer пишет
«Стиль: <Название>» из каталога направлений») — СОВЕТ модели, не гарантия. В
реальном прогоне marketer под давлением токенов пропустил этот необязательный
шаг (написал оффер/CTA/FAQ/квиз, но НЕ строку стиля), а designer, не найдя её,
не спросил коллегу (тоже необязательный шаг) — и просто построил сайт по
собственным дефолтам, как будто каталога направлений не существовало. Инструкции
в тексте плейбука недостаточно (engineering-principles: LLM предлагает, код
решает) — нужна детерминированная подстраховка, которая СРАБОТАЕТ независимо
от того, выполнит ли модель шаг.

12 направлений — machine-readable зеркало каталога из
builtin_skills/landing_conversion.md (палитра/шрифты там расписаны для LLM
текстом; здесь — только имена, для стабильного детерминированного выбора).

  pick_for(niche, audience)  — стабильный выбор направления по нише (не hash()
                                Python — он рандомизирован по процессам/PYTHONHASHSEED,
                                нужна persistent-стабильность между рестартами сервера)
  ensure_style_line(...)     — гарантирует строку «Стиль: …» в docs/site_content.md:
                                если marketer её уже написал — не трогает; если нет —
                                детерминированно проставляет САМ, без LLM, $0.
"""

import hashlib

# Имена совпадают 1:1 с каталогом в builtin_skills/landing_conversion.md —
# правишь один — проверь второй (см. tests/test_design_skills.py).
DIRECTIONS: list[str] = [
    "Терракотовый ремесленный",
    "Графитовый индастриал",
    "Газетный минимализм",
    "Мягкий шалфейный wellness",
    "Нео-бруталист",
    "Изумрудный престиж",
    "Чистый геометричный SaaS",
    "Винтажный каталожный",
    "Прибрежное спокойствие",
    "Монохромный люкс",
    "Тёплый ночной неон",
    "Свежий фермерский",
]


def pick_for(niche: str = "", audience: str = "") -> str:
    """Детерминированный (стабильный между рестартами) выбор направления по нише:
    одна и та же ниша ВСЕГДА даёт одно и то же направление; разные ниши обычно
    получают разные (равномерный hash-разброс, НЕ keyword-словарь — не тот же
    класс долга, что уже выпиливали, §_WORDS-списки)."""
    key = (niche or "").strip().lower() or (audience or "").strip().lower() or "default"
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()
    return DIRECTIONS[int(digest, 16) % len(DIRECTIONS)]


def has_style_line(content: str) -> bool:
    return bool(content) and not content.startswith("Файл не найден") and "Стиль:" in content


def ensure_style_line(niche: str = "", audience: str = "") -> str:
    """Гарантирует строку «Стиль: …» в docs/site_content.md ДО того, как
    designer/developer начнут строить сайт. Идемпотентно: если строка уже
    есть (marketer выполнил инструкцию сам) — контент не трогаем. Если нет —
    детерминированно проставляем направление ПЕРВОЙ строкой (self-heal, без
    LLM-вызова). Возвращает итоговый контент файла."""
    from src.office import workspace
    content = workspace.read_file("docs/site_content.md")
    if has_style_line(content):
        return content
    direction = pick_for(niche, audience)
    line = f"Стиль: {direction} — направление подобрано автоматически (маркетинг не указал явно)\n\n"
    body = "" if not content or content.startswith("Файл не найден") else content
    new_content = line + body
    workspace.write_file("docs/site_content.md", new_content)
    return new_content
