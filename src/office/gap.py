"""
Gap Analysis — разрыв между желаемым и действительным (см. дорожная_карта Phase 4, BOS §3).

Замыкает измерительный полукруг кибернетического цикла: для каждой ИЗМЕРИМОЙ цели
(objectives.measurable) сравнивает текущее значение метрики (из Measurement) с
desired. Разница ВЫЧИСЛИМА, а не «ощущение CEO» — до этой фазы система была честным
Bootstrapping-режимом (Intent→Plan→Execution→Acceptance) без обратной связи по цели.

  compute()      — список разрывов [{objective, current, desired, gap, met}]
  context_block()— блок «Разрывы» для промпта CEO (world.context_block)
  replan()       — детерминированно создаёт работу под НЕзакрытый разрыв (Steady State)

Резолвер метрики по objective.measured_by пока покрывает «заявки/лиды» (единственная
измеримая цель, которую офис создаёт сам — objectives.ensure_leads_objective). Новая
измеримая цель → новая ветка резолвера, а не «ощущение».

⚠️ Раньше owner мог задать ЛЮБОЙ текст в measured_by через objectives.add() (например
«MRR», «конверсия в оплату») — objective проходила валидацию схемы, попадала в
world.snapshot() и показывалась в промпте CEO как «измеримая», но _current_value()
для неё молча возвращала None, и compute() тихо ИСКЛЮЧАЛ её из Gap Analysis —
владелец видел цель как отслеживаемую, а система её никогда не проверяла (реальная
находка docs/prompts/system-audit-prompt.md, «Бизнес-логика: находки», [КРИТИЧНО]
gap.py:31). `resolvable()` — явная точка правды «какие measured_by реально
поддерживаются», используемая и здесь, и в objectives.context_block()/world.snapshot()
для показа "измеримо по описанию, но резолвер не подключён" вместо тихого исчезновения.
"""

import re

# Единственный источник правды «какие measured_by реально резолвятся» — раньше
# было неявно зашито внутри _current_value(), теперь явная, переиспользуемая
# точка (см. предупреждение в докстринге модуля выше).
_METRIC_RESOLVERS: dict[str, tuple[str, ...]] = {
    "leads_7d": ("leads", "заявк", "лид"),
}


def resolvable(measured_by: str) -> bool:
    """Есть ли у measured_by реальный резолвер метрики (см. _METRIC_RESOLVERS)."""
    mb = (measured_by or "").lower()
    if not mb:
        return False
    return any(any(kw in mb for kw in keywords) for keywords in _METRIC_RESOLVERS.values())


def _first_number(text: str) -> float | None:
    m = re.search(r"\d[\d\s]*\d|\d", (text or "").replace(" ", " "))
    if not m:
        return None
    try:
        return float(m.group(0).replace(" ", ""))
    except ValueError:
        return None


def _current_value(objective: dict) -> float | None:
    """Текущее значение метрики цели (из Measurement). None — метрика не резолвится
    (тогда цель в gap-анализ не попадает, а не даёт ложный ноль)."""
    from src.office import metrics
    mb = (objective.get("measured_by") or "").lower()
    if any(kw in mb for kw in _METRIC_RESOLVERS["leads_7d"]):
        return float(metrics.latest("leads_7d") or 0)
    return None


def compute() -> list[dict]:
    """Разрывы по всем измеримым целям. gap = desired − current; met = gap ≤ 0."""
    from src.office import objectives
    out: list[dict] = []
    for o in objectives.measurable():
        cur = _current_value(o)
        des = _first_number(o.get("desired", ""))
        if cur is None or des is None:
            continue  # метрика/целевое число не резолвятся — разрыв не вычислим
        gap = round(des - cur, 2)
        out.append({
            "objective_id": o["id"], "title": o["title"],
            "current": cur, "desired": des, "gap": gap, "met": gap <= 0,
            "source": "факт",  # current — из фактической метрики leads_7d
        })
    return out


def unmet() -> list[dict]:
    return [g for g in compute() if not g["met"]]


def context_block() -> str:
    """Блок «Разрывы» для CEO — наравне с блокерами (world.context_block)."""
    gaps = compute()
    if not gaps:
        return ""
    lines = []
    for g in gaps:
        mark = "✅ достигнута" if g["met"] else f"⚠ разрыв {g['gap']}"
        lines.append(f"- {g['title']}: сейчас {g['current']} из {g['desired']} ({mark})")
    return "\n=== РАЗРЫВЫ ДО ЦЕЛЕЙ (Gap Analysis) ===\n" + "\n".join(lines) + "\n"


# Детерминированный маппинг «разрыв → работа» (тот же принцип, что _fallback_plan):
# конкретный вид разрыва порождает конкретную роль+задачу. Не «CEO придумывает» —
# правило зашито и проверяемо.
def _work_for_gap(g: dict) -> tuple[str, str, str] | None:
    """(role, title, done_criterion) для незакрытого разрыва — или None."""
    title_low = (g.get("title") or "").lower()
    if "заявк" in title_low or "лид" in title_low:
        return ("marketer",
                "Усилить привлечение заявок: доработать оффер и CTA лендинга, "
                "предложить дополнительный канал трафика",
                "рост числа заявок за неделю относительно текущего")
    return None


def replan() -> list[dict]:
    """Steady State: под каждый НЕзакрытый разрыв создаёт задачу и, если она попадает
    в свежий пустой активный проект, называет его по разрыву (BOS §3/§5: Gap создаёт
    Work, а не голую задачу без владельца-контекста).
    Дедуп по objective (requested_by=`gap:<oid>`) — не больше одной АКТИВНОЙ
    авто-задачи на цель одновременно, чтобы офис не спамил одинаковыми задачами
    каждый цикл (endless-retry — горизонт Phase X).

    Дедуп смотрит только на pending/in_progress задачи с этим тегом, а не на ВСЕ —
    иначе одна-единственная попытка (даже принятая с расхождением с контрактом,
    как в реальном кейсе: разрыв «10 заявок/неделю» остался 0/10, но одна
    сгенерированная задача с неизмеримым done_criterion была принята с
    предупреждением) блокировала повторные попытки для этой цели НАВСЕГДА, хотя
    разрыв так и остался открытым."""
    from src.office import plan, projects
    created = []
    active_tags = {t.get("requested_by", "") for t in plan.all_tasks()
                   if t.get("status") in ("pending", "in_progress")}
    for g in unmet():
        tag = f"gap:{g['objective_id']}"
        if tag in active_tags:
            continue  # авто-задача под этот разрыв уже в работе — не дублируем
        work = _work_for_gap(g)
        if not work:
            continue
        # Gap создаёт Work, а не голую задачу в чужом контексте (BOS §3): если
        # add_task вот-вот попадёт в свежесозданный ПУСТОЙ активный проект
        # (ensure_active() завела его от общего брифа), проверяем пустоту ДО
        # добавления задачи и после даём проекту название, отражающее разрыв.
        proj_before = projects.active()
        was_empty = bool(proj_before) and not plan.for_project(proj_before["id"])
        role, title, crit = work
        task = plan.add_task(title, role, crit, requested_by=tag)
        created.append(task)
        if was_empty:
            proj = projects.active()
            if proj:
                projects.rename(proj["id"], f"Закрыть разрыв: {g['title']}")
    return created
