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

# Текст промпта архитектора — policies/architect.md (собирается prompt_builder.
# company_system со слотом Brief: niche/goal с подписью goal≠niche — архитектор
# был точкой путаницы goal/niche, теперь дизамбигуация приходит из единого слота).


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
    from src.office import prompt_builder
    system, _pid = prompt_builder.company_system("architect", agent_id, "architect", user)
    result = await llm.run_agent(
        system=system,
        user=user,
        model=models_module.for_agent(agent_id),
        max_tokens=5000,
        max_iterations=8,
        use_search=True,
        publish=publish,
        agent_id=agent_id,
    )

    _save(result)

    from src.office import state, workspace as ws_module
    state.save_deliverable(agent_id, "architect", "Техническое задание", result)
    # Сохраняем ТЗ в workspace — разработчик читает через list_files + read_file
    ws_module.write_file("docs/tech_design.md", result)

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
