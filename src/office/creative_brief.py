"""
Creative Brief — быстрый интейк вкуса владельца ДО того, как designer/marketer
примет решение о тоне или палитре (см. builtin_skills/brand_book.md).

Раньше стиль решал маркетолог единолично («Стиль: …» в site_content.md) —
решение реального человека нигде не спрашивалось, только придумывалось
агентом. Здесь — три точных вопроса через ask_user, ОДИН раз на тенанта
(не на каждую задачу), результат кешируется и используется как контекст для
выбора направления в каталоге (builtin_skills/brand_book.md).

Хранение — как у philosophy.py: простой JSON, per-tenant через context.py.
"""

from src.saas import context as ctx

_FILE = "creative_brief"

_DEFAULT: dict = {
    "tone": "",
    "reference": "",
    "avoid": "",
}


def load() -> dict:
    data = ctx.read_json(_FILE, None) or {}
    return {**_DEFAULT, **data}


def capture(tone: str = "", reference: str = "", avoid: str = "") -> dict:
    """Сохраняет ответ владельца. Пустые поля — осознанное «на ваше усмотрение»,
    не блокер (see builtin_skills/brand_book.md — не переспрашивать повторно)."""
    data = {
        "tone": (tone or "").strip()[:200],
        "reference": (reference or "").strip()[:200],
        "avoid": (avoid or "").strip()[:200],
    }
    ctx.write_json(_FILE, data)
    return data


def is_set() -> bool:
    """Спрашивали ли уже владельца — не «есть ли непустой ответ» (пустой = тоже
    ответ, «на ваше усмотрение»). Наличие файла = вопрос уже задан один раз."""
    return ctx.read_json(_FILE, None) is not None


def prompt_block() -> str:
    """Блок для промпта designer/marketer — что владелец сказал про вкус."""
    d = load()
    if not (d["tone"] or d["reference"] or d["avoid"]):
        return ""
    lines = ["=== ВКУС ВЛАДЕЛЬЦА (из интервью, учитывай при выборе направления) ==="]
    if d["tone"]:
        lines.append(f"Тон: {d['tone']}")
    if d["reference"]:
        lines.append(f"Референс: {d['reference']}")
    if d["avoid"]:
        lines.append(f"Избегать: {d['avoid']}")
    return "\n".join(lines)
