"""
Первое расследование компании (Company Investigation) — docs/first-investigation-
plan-2026-07-16.md, Фаза 4: живой агентский диалог вместо жёсткого 2-шагового
скрипта (спросить фиксированные вопросы → собрать один ответ → собрать бриф,
см. прежнюю реализацию `_intake_from_chat` в server.py и office/intake.py).

Агент сам решает, когда спрашивать клиента (короткий вопрос), а когда искать
самостоятельно (`web_search` — тот же generic-инструмент run_agent, что у любой
другой роли; `max_searches` — суббюджет за один ход, тот же принцип "агент сам
решает, когда поиск даст ценность", что и у company_scan.search_company, Фаза 1).
Заканчивает расследование ЯВНЫМ вызовом `finish_investigation` — бриф реально
сохраняется только тогда, а не когда модель просто перестала звать инструменты.

Состояние — по тенанту: data/tenants/<tid>/investigation.json — простая история
user/assistant реплик (НЕ сырой tool-call transcript run_agent — тот специально
живёт только внутри одного вызова; здесь помнится только то, что реально сказано
человеку и агентом, тот же контракт, что у history-параметра run_agent).

office/intake.py (прежний жёсткий discovery-скрипт) намеренно НЕ удалён и не
трогается — судьба мёртвого онбординг-кода решается централизованно в Фазе 6
(вместе с onboarding.MODES/_INTERVIEW/make_questions), не по частям.
"""

from src.saas import context as ctx

_FILE = "investigation.json"

_STAGES = ("idea", "launch", "growth", "mature")
_CONFIDENCE = ("confirmed", "inferred", "unconfirmed")

# Максимум реплик истории, которые тащим в промпт следующего хода — расследование
# не должно длиться десятками сообщений; если за это не собрали достаточно,
# агент и так обязан спросить прямо или честно сдаться (см. принцип 6 в промпте).
_MAX_HISTORY = 20

SYSTEM_PROMPT = """Ты — CEO AI-офиса, который проводит ПЕРВОЕ РАССЛЕДОВАНИЕ компании клиента. Это не анкета и не форма — живой разговор.

Цель — честно понять: что продаёт компания, кому, какая цель ЭТОГО прогона офиса (не то, что продаёт бизнес — а что клиент хочет получить ОТ ОФИСА), и на какой стадии сейчас бизнес (идея / запуск / рост / зрелость).

ПРИНЦИПЫ (не нарушать):
1. Усилие тратишь ТЫ, а не клиент. Прежде чем спросить что-то у человека — попробуй узнать это сам через web_search (по названию компании, нише, региону — если они уже прозвучали). Никогда не предлагай клиенту "заполнить анкету" или "ответить на несколько вопросов списком".
2. Ищи, только если есть за что зацепиться (конкретное название или ниша+регион). Если данных совсем мало — не выдумывай запрос, а спроси коротко, одним-двумя словами по смыслу.
3. Вопросы клиенту — короткие, по одному-два за раз, не абзацем и не списком. Не спрашивай то, что можно узнать поиском.
4. Если поиск ничего не дал — это честный, нормальный исход (компания может быть совсем новой, только начинает). Так и скажи, не притворяйся, что нашёл больше, чем нашёл.
5. Каждую находку в вебе (сайт/соцсети/2ГИС/отзывы/упоминания) — озвучивай клиенту прямо ("Нашёл вас в 2ГИС, 4.6 звезды, отзывы есть"), а не молчи о ней.
6. Как только знаешь достаточно (продукт, аудитория, цель, честная гипотеза о стадии) — сразу вызови finish_investigation. Не тяни разговор дольше, чем реально нужно.
7. Никогда не выдавай гипотезу о стадии бизнеса как факт: confirmed — только если клиент САМ явно подтвердил; unconfirmed — если сигналов почти нет; inferred — для всего остального (нашёл реальные, но не проверенные владельцем сигналы)."""

FINISH_TOOL = {
    "type": "function",
    "function": {
        "name": "finish_investigation",
        "description": ("Завершить расследование и передать собранный бриф в работу офиса. "
                        "Вызывай, когда знаешь достаточно — не раньше, но и не позже, чем нужно."),
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Краткое резюме бизнеса и задачи, 2-4 предложения"},
                "niche": {"type": "string", "description": "Ниша — что бизнес продаёт"},
                "goal": {"type": "string", "description": "Цель ЭТОГО прогона офиса — что клиент хочет от AI-офиса"},
                "audience": {"type": "string", "description": "Целевая аудитория / кому продают"},
                "business_stage_key": {"type": "string", "enum": list(_STAGES)},
                "business_stage_label": {"type": "string", "description": "Короткая фраза о стадии для владельца"},
                "business_stage_reason": {"type": "string", "description": "Почему именно эта стадия, одним предложением"},
                "business_stage_confidence": {"type": "string", "enum": list(_CONFIDENCE)},
            },
            "required": ["summary", "niche", "goal", "business_stage_key",
                         "business_stage_label", "business_stage_reason", "business_stage_confidence"],
        },
    },
}


def _load() -> dict:
    return ctx.read_json(_FILE, {"history": []})


def _save(state: dict) -> None:
    ctx.write_json(_FILE, state)


def active() -> bool:
    """Идёт ли уже расследование (был хотя бы один обмен репликами)."""
    return bool(_load().get("history"))


def reset() -> None:
    ctx.delete_file(_FILE)


def _build_brief_data(args: dict) -> dict:
    stage_key = args.get("business_stage_key")
    stage_confidence = args.get("business_stage_confidence")
    stage = {
        "key": stage_key if stage_key in _STAGES else "idea",
        "label": (args.get("business_stage_label") or "").strip()[:120],
        "reason": (args.get("business_stage_reason") or "").strip()[:300],
        "confidence": stage_confidence if stage_confidence in _CONFIDENCE else "unconfirmed",
    }
    return {
        "summary": (args.get("summary") or "").strip()[:600],
        "niche": (args.get("niche") or "").strip()[:200],
        "goal": (args.get("goal") or "").strip()[:300],
        "audience": (args.get("audience") or "").strip()[:300],
        "business_stage": stage,
    }


async def run_turn(text: str, publish=None) -> tuple[str, bool]:
    """Один ход диалога расследования. Возвращает (reply_text, finished) —
    finished=True означает, что brief.set_brief() уже вызван внутри этого хода
    и офис может стартовать BOOTSTRAP (тот же переход, что раньше делал
    server.py._intake_from_chat после сбора ответов)."""
    from src.core import llm as llm_module
    from src.office import brief as brief_module, memory

    state = _load()
    history = state.get("history", [])

    finished_holder: dict = {"done": False, "brief": None}

    async def _finish_handler(args: dict) -> str:
        brief_data = _build_brief_data(args)
        brief_module.set_brief(brief_data)
        memory.remember("Бриф клиента (приоритет)", brief_data.get("summary", ""))
        finished_holder["done"] = True
        finished_holder["brief"] = brief_data
        return "Бриф сохранён, офис приступает к работе."

    reply = await llm_module.run_agent(
        system=SYSTEM_PROMPT,
        user=text,
        history=history,
        use_search=True,
        max_searches=3,
        extra_tools=[FINISH_TOOL],
        tool_handlers={"finish_investigation": _finish_handler},
        agent_id="orchestrator_1",
        max_iterations=6,
        publish=publish,
    )

    if finished_holder["done"]:
        reset()  # расследование закрыто — состояние больше не нужно
        if not reply:
            reply = (f"Принял ✅ Вот как я понял задачу:\n\n{finished_holder['brief'].get('summary', '')}\n\n"
                     "Команда приступает: исследование рынка, стратегия, план. Пишите сюда в любой "
                     "момент, чтобы направлять или уточнять.")
    else:
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": reply})
        _save({"history": history[-_MAX_HISTORY:]})
        if not reply:
            reply = "Понял, уточню ещё пару деталей."

    return reply, finished_holder["done"]
