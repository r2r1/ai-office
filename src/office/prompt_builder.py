"""
Prompt Builder — единая точка сборки системного промпта (см. docs/arhitecture.md).

Ни у одной роли нет собственного статического промпта: есть Role Definition
(roles.py) и инварианты команды, а итоговый системный промпт собирается здесь
под конкретного агента. Меняется формат под новую модель — правится только тут.

Иерархия (сверху вниз по приоритету):
  Role Definition (roles.render)
    + специализация в проекте (skill)
    + бриф клиента
    + 3-слойная память офиса (memory.context_block)
    + инварианты: автономность, «артефакты только через инструменты», межагентность

Философия и Конституция компании доходят до агента через слой знаний
(knowledge GLOBAL → task-контекст в loop._task_with_context), поэтому здесь не
дублируются — иначе платим за одни и те же токены дважды.
"""

from src.office import roles
from src.office import memory as memory_module


def build(role: str, task: str, agent_id: str, skill: str = "") -> str:
    """Системный промпт агента. Поведение 1:1 с прежней сборкой в agent_factory.create,
    но роль теперь — данные (roles.render), а сборка централизована."""
    # Инварианты и бриф остаются каноничными в agent_factory (CLAUDE.md фиксирует там
    # _TEAM_PREAMBLE) — берём лениво, чтобы не плодить дубли и не ловить цикл импорта.
    from src.agents import agent_factory as af

    base = roles.render(role)
    skill_line = f"\n\nТвоя специализация в этом проекте: {skill}" if skill else ""
    return (base + skill_line + af._brief_context() + memory_module.context_block()
            + af._AUTONOMY_RULES + af._TEAM_PREAMBLE + af._INTER_AGENT_SUFFIX)
