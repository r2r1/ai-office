"""
Skills — встроенная бизнес-логика (второй способ Execution Engine из docs/3.md).

Задача может быть выполнена тремя способами:
  1. Встроенный AI (LLM) — основной путь (см. core/llm.py).
  2. Skill — готовая бизнес-логика: знает КАК сделать (структура, проверки),
     внутри может звать LLM/интеграции, но сама по себе детерминирована.
  3. External Worker — внешний сервис (Cursor/Lovable/n8n) — точка расширения.

Этот модуль фиксирует КОНТРАКТ Skill и реестр. Стартовые Skill'ы — тонкие
обёртки поверх уже существующей логики (публикация лендинга, запуск бота записи),
чтобы зафиксировать иерархию «Отдел → Skill → Execution Engine», не переписывая
агентов. Полное подключение к agent_factory — отдельная задача.
"""

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional


@dataclass
class Skill:
    """Декларативное описание навыка (по образцу integrations/base.Integration)."""
    id: str
    title: str
    description: str
    # Слова-триггеры в тексте задачи (грубый матч намерения).
    keywords: list[str] = field(default_factory=list)
    # Асинхронный исполнитель: получает params, возвращает строку-итог.
    handler: Optional[Callable[[dict], Awaitable[str]]] = None

    def score(self, task: str) -> int:
        """Насколько Skill подходит задаче (число совпавших ключевых слов)."""
        t = (task or "").lower()
        return sum(1 for k in self.keywords if k in t)

    def to_public(self) -> dict:
        return {"id": self.id, "title": self.title, "description": self.description,
                "keywords": self.keywords}


# ── Реестр ───────────────────────────────────────────────────────────────────
_SKILLS: dict[str, Skill] = {}


def register(skill: Skill) -> None:
    _SKILLS[skill.id] = skill


def all_skills() -> list[Skill]:
    return list(_SKILLS.values())


def match(task: str) -> Optional[Skill]:
    """Лучший Skill под задачу или None (тогда задачу делает LLM напрямую)."""
    ranked = sorted(_SKILLS.values(), key=lambda s: s.score(task), reverse=True)
    if ranked and ranked[0].score(task) > 0:
        return ranked[0]
    return None


def catalog_payload() -> list[dict]:
    return [s.to_public() for s in _SKILLS.values()]


# ── Стартовые Skill'ы (обёртки поверх существующей логики) ───────────────────
async def _publish_landing(params: dict) -> str:
    """Публикация лендинга — бэкенд website-интеграции хостит сам."""
    from src.integrations import registry as integrations_registry
    integ = integrations_registry.get("website")
    if not integ:
        return "Интеграция website недоступна."
    return ("Лендинг публикуется через website.publish_landing — "
            "файлы из site/ хостятся платформой автоматически.")


async def _launch_booking_bot(params: dict) -> str:
    """Запуск шаблонного Telegram-бота записи (готовый движок платформы)."""
    return ("Бот записи запускается через telegram.launch_bot — "
            "поведение задаётся конфигом тенанта (bot_config).")


register(Skill(
    id="publish_landing", title="Опубликовать лендинг",
    description="Хостит статический сайт из site/ и собирает лиды.",
    keywords=["лендинг", "landing", "сайт", "опубликовать", "publish"],
    handler=_publish_landing,
))
register(Skill(
    id="launch_booking_bot", title="Запустить бота записи",
    description="Готовый Telegram-бот записи клиентов: меню → имя/телефон → лид.",
    keywords=["бот записи", "booking", "запись", "telegram бот", "запустить бот"],
    handler=_launch_booking_bot,
))
