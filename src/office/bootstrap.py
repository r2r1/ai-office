"""
Bootstrap — единоразовый запуск офиса как отдельная подсистема (BOS §12).

Расслоение loop.py (Phase 6, финальный срез): всё, что относится к ПЕРВОМУ
запуску тенанта (наём стартовой команды + ресёрч → стратегия), вынесено из
бог-модуля цикла:

  hire_initial(publish)  — нанять CEO + штаб стратегии (один раз на тенанта)
  run(publish) -> str    — ресёрч → стратегия (возвращает текст стратегии)
  strategy_text()        — прочитать сохранённую стратегию тенанта
  save_strategy(text)    — сохранить стратегию тенанта

Модуль не владеет живостью в памяти процесса — вызывается один раз за жизнь
тенанта из loop._run_office и не разделяет состояние с циклами/watchdog.
loop импортирует bootstrap (одностороннее направление).
"""

import os

from src.office import milestones, brief
from src.agents import researcher, strategist
from src.saas import context as ctx

# Потолок одного шага BOOTSTRAP (deep-ресёрч): watchdog покрывает только циклы,
# не bootstrap — зависший первый шаг раньше замораживал офис навсегда.
BOOTSTRAP_STEP_TIMEOUT = int(os.getenv("BOOTSTRAP_STEP_TIMEOUT", "900"))


def strategy_text() -> str:
    f = ctx.tenant_dir() / "strategy.md"
    return f.read_text(encoding="utf-8") if f.exists() else ""


def save_strategy(strategy: str) -> None:
    (ctx.tenant_dir() / "strategy.md").write_text(strategy, encoding="utf-8")


async def _set_progress_note(note: str, publish) -> None:
    payload = milestones.progress_payload()
    payload["note"] = note
    await publish({"type": "progress", **payload})


async def hire_initial(publish) -> None:
    """CEO + штаб стратегии. Лидеры отделов и работники нанимаются по необходимости
    (CEO открывает отдел → нанимается лидер → лидер нанимает работников)."""
    from src.office import registry
    starters = [
        ("orchestrator_1", "orchestrator", "Управление компанией и отделами"),
        ("researcher_1", "researcher", "Исследование рынка и трендов"),
        ("strategist_1", "strategist", "Построение бизнес-стратегии"),
        ("architect_1", "architect", "Техническое проектирование решения"),
    ]
    for aid, role, task in starters:
        if not registry.has_role(role):
            rec = registry.register(aid, role, task)
            if rec:
                await publish({
                    "type": "hired", "agent_id": aid, "role": role, "desk": rec.desk, "task": rec.task,
                })


async def run(publish) -> str:
    """Ресёрч → стратегия. Возвращает текст стратегии (пустой при сбое — офис
    продолжает работу по одному брифу, а не падает)."""
    import asyncio

    # «Понимание компании» влияет на поведение (B4): при очень низком score офис
    # честно предупреждает, что работает с неполным брифом (не блокирует).
    try:
        from src.office import understanding
        score = understanding.payload().get("score", 100)
        if score < 30:
            await publish({"type": "system",
                           "text": f"ℹ️ Понимание бизнеса пока низкое ({score}/100) — офис стартует "
                                   f"с неполным брифом. Опишите бизнес и цель в чате CEO, чтобы "
                                   f"результат точнее попал в задачу."})
    except Exception:
        pass
    await publish({"type": "system", "text": "=== BOOTSTRAP: исследуем нишу клиента ==="})
    milestones.mark_active("research")
    await _set_progress_note("Исследуем рынок и тренды", publish)

    question = brief.research_question() or researcher.DEFAULT_QUESTION
    try:
        research = await asyncio.wait_for(researcher.deep(question, publish=publish),
                                          timeout=BOOTSTRAP_STEP_TIMEOUT)
    except asyncio.TimeoutError:
        await publish({"type": "system", "agent_id": "researcher_1",
                       "text": f"⏱ Исследование не уложилось в {BOOTSTRAP_STEP_TIMEOUT // 60} мин — "
                               f"продолжаю по брифу без глубокого ресёрча"})
        research = ""
    except Exception as e:
        await publish({"type": "error", "agent_id": "researcher_1", "text": str(e)[:100]})
        research = ""
    milestones.set_status("research", "done")
    milestones.set_summary("research", (research or "")[:400])

    milestones.mark_active("strategy")
    await _set_progress_note("Строим бизнес-стратегию", publish)
    strat_input = research
    if brief.summary():
        strat_input = f"БРИФ КЛИЕНТА:\n{brief.summary()}\n\nИССЛЕДОВАНИЕ РЫНКА:\n{research}"
    try:
        strategy = await strategist.run_async(strat_input, publish=publish)
        save_strategy(strategy)
    except Exception as e:
        await publish({"type": "error", "agent_id": "strategist_1", "text": str(e)[:100]})
        strategy = ""
    milestones.set_status("strategy", "done")
    milestones.set_summary("strategy", (strategy or "")[:400])
    return strategy
