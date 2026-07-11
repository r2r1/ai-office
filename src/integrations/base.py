"""
Базовые структуры для описания интеграции.

Интеграция — это декларативное описание внешнего сервиса:
  • какие учётные данные ему нужны (`cred_fields`) и как их получить (`how_to`);
  • какие действия (`actions`) он умеет выполнять реальными вызовами API.

Реализация действия — async-функция вида `handler(creds, params) -> str`, где
`creds` это словарь `fields` из сохранённого подключения (см. connections.py),
а `params` — аргументы от агента. Функция возвращает человекочитаемый текст
результата (его увидит и агент, и пользователь в событиях).
"""

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


@dataclass
class CredField:
    """Одно поле учётных данных, которое нужно интеграции."""
    key: str               # ключ внутри connections fields (например "token")
    label: str             # человекочитаемое название для UI
    secret: bool = True    # скрывать ли значение в интерфейсе


@dataclass
class Action:
    """Одно действие интеграции — реальный вызов внешнего API."""
    name: str
    description: str
    handler: Callable[[dict, dict], Awaitable[str]]
    params: dict[str, dict] = field(default_factory=dict)   # JSON-schema properties
    required: list[str] = field(default_factory=list)
    # Слова, которыми агент/клиент описывает потребность СВОБОДНО («лендинг»,
    # «письмо»), но которых нет в name/description этого действия — раньше жили
    # ТОЛЬКО в отдельном захардкоженном словаре src/office/tool_router.py
    # (_INTENT_HINTS), физически оторванном от файла интеграции: автор новой
    # интеграции мог не узнать, что такой словарь вообще существует, и его
    # интеграция подхватывалась бы роутером хуже остальных без единой ошибки.
    # Теперь синонимы — часть декларации самого действия, тот же принцип
    # развязки, что уже применён к cred_fields/actions.
    synonyms: list[str] = field(default_factory=list)


@dataclass
class Integration:
    """Описание внешнего сервиса целиком."""
    name: str              # короткий идентификатор латиницей ("telegram")
    title: str             # отображаемое название ("Telegram")
    icon: str              # эмодзи для UI
    description: str       # что умеет интеграция (1-2 предложения)
    how_to: str            # как получить учётные данные (3-5 шагов)
    cred_fields: list[CredField] = field(default_factory=list)
    actions: dict[str, Action] = field(default_factory=dict)
    oauth_url: str = ""   # если задан — подключение через кнопку «Войти», а не ввод ключа
    category: str = "other"  # для группировки каталога в UI: communication/publishing/productivity/dev
    # Способность закреплена за отделом ('' = общая, доступна любой роли —
    # прежнее поведение, инвариант "общие доступы" из CLAUDE.md никуда не делся
    # по умолчанию). Заполнено — вызвать может только роль из этого отдела или
    # portfolio-роль (CEO/лидер/штаб, org.is_portfolio_role) — see
    # integration_tool_handlers._execute_integration. Не про креды (те и так
    # общие), а про то, КОМУ ИМЕЕТ СМЫСЛ дёргать это действие — 1С/бухгалтерия
    # не должна вызываться salesman'ом просто потому что ключ технически есть.
    department: str = ""

    def cred_keys(self) -> list[str]:
        return [c.key for c in self.cred_fields]

    def to_public(self) -> dict:
        """Сериализация для фронта/агентов (без значений кредов)."""
        return {
            "name": self.name,
            "title": self.title,
            "icon": self.icon,
            "description": self.description,
            "how_to": self.how_to,
            "oauth_url": self.oauth_url,
            "category": self.category,
            "department": self.department,
            "cred_fields": [
                {"key": c.key, "label": c.label, "secret": c.secret}
                for c in self.cred_fields
            ],
            "actions": [
                {
                    "name": a.name,
                    "description": a.description,
                    "params": a.params,
                    "required": a.required,
                }
                for a in self.actions.values()
            ],
        }
