"""
Workflows — реестр составных бизнес-глаголов (Layer 4).

Слои инструментов агента (снизу вверх): примитивы (write_file/execute_code) →
skills («как» делать одну генеративную задачу) → capabilities/integrations
(одно внешнее действие) → capability-гейт (что вообще умеем). Composite verb —
следующий уровень: формулировка вроде «проанализировать Битрикс» или «запустить
контент-завод» не закрывается ни одним примитивом, ни одним внешним действием —
это ЦЕПОЧКА шагов, а её потребность во внешних доступах нельзя вывести из
одного слова заголовка (capability.derive_required на это не рассчитан).

Workflow — ТОЛЬКО декларация: что глагол требует (required_capabilities — идёт
в capability-гейт ДО старта задачи, а не выясняется по факту проваленной
приёмки), какая роль его обычно тянет, какой skill даёт «как», разовый он или
повторяющийся (recurring). Само исполнение НЕ меняется — задача с
workflow_id идёт через тот же agent_factory.create(role, skill, task), что и
любая другая; workflow просто даёт точные данные вместо угаданных по словам.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Workflow:
    id: str
    label: str
    keywords: list[str] = field(default_factory=list)
    required_capabilities: list[str] = field(default_factory=list)
    suggested_role: str = "developer"
    skill: str = ""
    recurring: bool = False

    def score(self, text: str) -> int:
        """Единый скорер потребностей (needs.py, BOS §5) — тот же приём, что у
        Skill.score и tool_router."""
        from src.office import needs
        return needs.score_keywords(text, self.keywords)

    def to_public(self) -> dict:
        return {"id": self.id, "label": self.label,
                "required_capabilities": self.required_capabilities,
                "suggested_role": self.suggested_role, "skill": self.skill,
                "recurring": self.recurring}


_CATALOG: dict[str, Workflow] = {}


def register(wf: Workflow) -> None:
    _CATALOG[wf.id] = wf


def all_workflows() -> list[Workflow]:
    return list(_CATALOG.values())


def get(workflow_id: str) -> Optional[Workflow]:
    return _CATALOG.get(workflow_id)


def match(text: str) -> Optional[Workflow]:
    """Лучший составной глагол под текст (обычно заголовок задачи), или None —
    тогда задача обычная, required_capabilities выводятся как раньше."""
    ranked = sorted(_CATALOG.values(), key=lambda w: w.score(text), reverse=True)
    if ranked and ranked[0].score(text) > 0:
        return ranked[0]
    return None


def required_capabilities_of(title: str) -> Optional[list[str]]:
    """required_capabilities составного глагола, если заголовок его матчит,
    иначе None (вызывающий код падает обратно на capability.derive_required)."""
    wf = match(title)
    return list(wf.required_capabilities) if wf else None


def catalog_payload() -> list[dict]:
    return [w.to_public() for w in _CATALOG.values()]


# ── Встроенный каталог ──────────────────────────────────────────────────────
# Пополняется по мере обнаружения реальных составных глаголов в прод-прогонах —
# не превентивно на все случаи разом (см. обсуждение фазы 5).

register(Workflow(
    id="crm_analysis",
    label="Анализ CRM",
    keywords=["проанализир", "анализ crm", "анализ битрикс", "аналитика продаж",
              "статистика лидов", "отчёт по сделкам", "отчет по сделкам"],
    required_capabilities=["crm"],
    suggested_role="analyst",
    recurring=False,
))

register(Workflow(
    id="content_factory",
    label="Контент-завод",
    keywords=["контент-завод", "контент завод", "конвейер контента",
              "регулярный контент", "контентный конвейер"],
    required_capabilities=[],
    suggested_role="marketer",
    recurring=True,
))
