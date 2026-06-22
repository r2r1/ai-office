"""
Architect Agent — технический архитектор офиса.

Получает бизнес-стратегию и формирует Техническое Техническое Задание (ТТЗ):
  • конкретный стек технологий
  • список микросервисов / компонентов
  • задачи на разработку с чёткими интерфейсами
  • последовательность реализации

ТТЗ сохраняется в reports/tech_design.md и загружается в контекст
директора и всех рабочих агентов — это исключает "архитектурные галлюцинации"
когда разработчики сами придумывают непоследовательные решения.
"""

from typing import Optional, Callable, Awaitable

from src.core import llm
from src.saas import context as ctx

_TECH_DESIGN = "tech_design.md"

SYSTEM_PROMPT = """Ты — технический архитектор AI-офиса. На вход ты получаешь бизнес-стратегию
и цель клиента. Твоя задача — создать Техническое Задание (ТЗ) для рабочих агентов.

ТЗ должно быть настолько конкретным, чтобы агент-разработчик мог взять любую задачу и
начать работу немедленно, без домыслов о технологиях или архитектуре.

🚫 ВАЖНО про сайт сбора заявок (типовой случай — держи стек МИНИМАЛЬНЫМ):
- Сайт = СОБСТВЕННЫЙ статический код (HTML5 + CSS3 + Vanilla JS), публикуется через
  встроенную интеграцию `website`. Форма шлёт POST на /api/site-lead — заявки попадают
  в раздел «Лиды» АВТОМАТИЧЕСКИ. Бэкенд писать НЕ нужно — он уже есть у платформы.
- НЕ закладывай: свой backend/FastAPI/SQLite, Google Sheets, email-рассылки (SendGrid),
  аналитику (Метрика/VK API), платные конструкторы (Tilda/Webflow/Wix), внешние CRM
  (amoCRM/Bitrix24) — НИЧЕГО из этого, если клиент не попросил явно. Это всё лишнее и
  только тормозит работу. Стек лид-сайта: статика + интеграция `website`. Точка.

Используй web_search для проверки актуальности технологий, наличия бесплатных тарифов,
наличия Python-библиотек.

Формат ТЗ:
## Техническое задание

### 1. Выбранный стек
- Язык/рантайм: (Python 3.11, Node.js, etc.)
- Фреймворк/основная библиотека: (aiogram 3, FastAPI, etc.)
- Хранилище данных: (SQLite / PostgreSQL / Google Sheets API / Notion API)
- Дополнительные сервисы: (только те, что реально нужны)

### 2. Компоненты системы
Для каждого компонента:
- Название
- Что делает (1-2 предложения)
- Входные данные / выходные данные
- Используемые API / библиотеки

### 3. Задачи разработки (в порядке приоритета)
Для каждой задачи:
- [ЗАДАЧА] Чёткое название
- Описание: что именно написать/настроить
- API-ключи/доступы, которые потребуются
- Ожидаемый результат (проверяемый)

### 4. Интеграции (API которые нужны)
Для каждой интеграции:
- Сервис и для чего
- Где получить ключ (3-4 шага)
- Тарифный план (бесплатный / платный)

### 5. Порядок внедрения
Пронумерованный список: сначала что, потом что. Без параллельных зависимостей.

Пиши КОНКРЕТНО. Не "выбрать подходящую БД" — а "использовать SQLite через aiosqlite".
Не "интегрировать мессенджер" — а "aiogram 3.x, webhook на домене, polling для разработки".
Пиши по-русски."""


async def run_async(
    strategy: str,
    goal: str,
    publish: Optional[Callable[[dict], Awaitable[None]]] = None,
    agent_id: str = "architect_1",
) -> str:
    if publish:
        await publish({"type": "thinking", "agent_id": agent_id,
                       "text": "Проектирую техническую архитектуру решения..."})

    user = (
        f"Цель клиента: {goal}\n\n"
        f"Бизнес-стратегия:\n{strategy[:3000]}\n\n"
        "Создай подробное Техническое Задание для команды разработчиков-агентов."
    )

    from src.office import models as models_module
    result = await llm.run_agent(
        system=SYSTEM_PROMPT,
        user=user,
        model=models_module.for_agent(agent_id),
        max_tokens=5000,
        max_iterations=8,
        use_search=True,
        publish=publish,
        agent_id=agent_id,
    )

    _save(result)

    from src.office import state
    state.save_deliverable(agent_id, "architect", "Техническое задание", result)

    if publish:
        await publish({"type": "task_done", "agent_id": agent_id,
                       "summary": result[:300]})

    return result


def load() -> str:
    """Загружает ТЗ текущего тенанта (пустая строка если нет)."""
    f = ctx.tenant_dir() / _TECH_DESIGN
    return f.read_text(encoding="utf-8") if f.exists() else ""


def _save(content: str) -> None:
    (ctx.tenant_dir() / _TECH_DESIGN).write_text(content, encoding="utf-8")
