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

import colorsys
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

# Акцентный hex каждого направления — зеркало каталога в landing_conversion.md
# (accent из его палитры). Нужен как СЕМЯ для generate_color_scale — раньше
# designer/developer видели только 5 фиксированных hex направления и сами
# придумывали hover/active-оттенки на глаз (непоследовательно между файлами).
ACCENT_HEX: dict[str, str] = {
    "Терракотовый ремесленный": "#C4592E",
    "Графитовый индастриал": "#FF7A45",
    "Газетный минимализм": "#B3261E",
    "Мягкий шалфейный wellness": "#6B8F71",
    "Нео-бруталист": "#FFDE59",
    "Изумрудный престиж": "#C9A227",
    "Чистый геометричный SaaS": "#3D5AFE",
    "Винтажный каталожный": "#8A3324",
    "Прибрежное спокойствие": "#2A8C93",
    "Монохромный люкс": "#101010",
    "Тёплый ночной неон": "#FF5FA2",
    "Свежий фермерский": "#5B8C3E",
}


def pick_for(niche: str = "", audience: str = "") -> str:
    """Детерминированный (стабильный между рестартами) выбор направления по нише:
    одна и та же ниша ВСЕГДА даёт одно и то же направление; разные ниши обычно
    получают разные (равномерный hash-разброс, НЕ keyword-словарь — не тот же
    класс долга, что уже выпиливали, §_WORDS-списки)."""
    key = (niche or "").strip().lower() or (audience or "").strip().lower() or "default"
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()
    return DIRECTIONS[int(digest, 16) % len(DIRECTIONS)]


# ── Генератор шкалы оттенков (design tokens) ────────────────────────────────
# Портировано из паттерна ui-design-system (claude-skills/product-team): HSV-шкала
# 50→900 из ОДНОГО акцентного hex, а не ручной подбор hover/active-оттенков моделью
# на глаз (несогласованно между файлами/страницами). Шаги 50-400: фиксированная
# высокая яркость + растущая насыщенность (светлые тона); 500: оригинал без
# изменений; 600-900: падающая яркость + растущая насыщенность (тёмные тона).
_SCALE_STEPS = (50, 100, 200, 300, 400, 500, 600, 700, 800, 900)


def _hex_to_hsv(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return colorsys.rgb_to_hsv(r, g, b)


def _hsv_to_hex(h: float, s: float, v: float) -> str:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, max(0.0, min(1.0, s)), max(0.0, min(1.0, v)))
    return "#{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255), round(b * 255))


def generate_color_scale(base_hex: str) -> dict[int, str]:
    """Шкала 50-900 из одного hex — детерминированно, без LLM. 500 = базовый цвет
    как есть; 50-400 — светлее и менее насыщенно (фоны/бордеры/disabled); 600-900 —
    темнее и насыщеннее (hover/active/текст на светлом фоне)."""
    hue, sat, val = _hex_to_hsv(base_hex)
    scale: dict[int, str] = {}
    for step in _SCALE_STEPS:
        if step == 500:
            scale[step] = base_hex.upper() if base_hex.startswith("#") else f"#{base_hex.upper()}"
        elif step < 500:
            # 50→400: яркость почти максимальная (фон), насыщенность растёт к 500
            light_idx = _SCALE_STEPS.index(step)  # 0..3
            t = light_idx / 4.0  # 0.0 .. 0.75
            scale[step] = _hsv_to_hex(hue, sat * (0.3 + 0.32 * t), max(val, 0.95))
        else:
            dark_idx = _SCALE_STEPS.index(step) - 5  # 1..4 (600..900)
            factor = 1.0 - dark_idx * 0.2  # 0.8, 0.6, 0.4, 0.2
            scale[step] = _hsv_to_hex(hue, min(1.0, sat + dark_idx * 0.06), val * factor)
    return scale


def tokens_css_block(direction: str) -> str:
    """CSS-блок :root с полной шкалой оттенков акцента направления + базовая
    типографическая/spacing шкала — designer/developer копируют ДОСЛОВНО вместо
    того, чтобы придумывать hover/active-оттенки на глаз (несогласованно между
    файлами страницы)."""
    accent = ACCENT_HEX.get(direction, "#3D5AFE")
    scale = generate_color_scale(accent)
    scale_lines = "\n".join(f"  --accent-{step}: {hexv};" for step, hexv in scale.items())
    return (
        "```css\n"
        "/* design-tokens: сгенерировано автоматически из акцента направления «"
        f"{direction}»; используй эти переменные, не изобретай свою шкалу */\n"
        ":root {\n"
        f"{scale_lines}\n"
        "  --space-1: 4px; --space-2: 8px; --space-3: 16px; --space-4: 24px;\n"
        "  --space-5: 32px; --space-6: 48px; --space-7: 72px; --space-8: 120px;\n"
        "  --text-sm: 14px; --text-base: 16px; --text-lg: 20px; --text-xl: 25px;\n"
        "  --text-2xl: 31px; --text-3xl: 39px; --text-4xl: 49px; --text-5xl: 61px;\n"
        "}\n"
        "```\n"
    )


def has_tokens_block(content: str) -> bool:
    return bool(content) and not content.startswith("Файл не найден") and "design-tokens" in content


def ensure_design_tokens(niche: str = "", audience: str = "") -> str:
    """Гарантирует готовый CSS-блок токенов в docs/site_content.md — та же
    механика self-heal, что у ensure_style_line. Использует ТО ЖЕ направление,
    что уже выбрано (или будет выбрано) ensure_style_line — иначе токены и
    «Стиль: …» могли бы разъехаться по разным направлениям."""
    from src.office import workspace
    content = workspace.read_file("docs/site_content.md")
    if has_tokens_block(content):
        return content
    # Направление берём из уже записанной строки «Стиль: …», если она есть —
    # иначе то же детерминированное pick_for, что использует ensure_style_line.
    direction = None
    if has_style_line(content):
        for name in DIRECTIONS:
            if name in content:
                direction = name
                break
    direction = direction or pick_for(niche, audience)
    block = tokens_css_block(direction) + "\n"
    body = "" if not content or content.startswith("Файл не найден") else content
    new_content = body + ("\n" if body and not body.endswith("\n") else "") + block
    workspace.write_file("docs/site_content.md", new_content)
    return new_content


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
