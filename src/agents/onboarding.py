"""
Onboarding Agent — CEO встречает клиента.

Два режима работы:
1. Свободный (legacy): любой ввод → 3-5 уточняющих вопросов → бриф (через LLM).
2. Структурированное интервью: 3 сценария входа × 5 фиксированных измерений
   (продукт → клиент → оборот → цель → ограничения). Бриф собирается
   ДЕТЕРМИНИРОВАННО из ответов — работает даже при нулевом балансе LLM.
"""

import json
from typing import Optional, Callable, Awaitable

from src.core import llm

# ─────────────────────── Структурированное интервью ───────────────────────
# Три сценария входа (item 4 плана). Для каждого — 5 вопросов по одним и тем же
# измерениям, но с разной формулировкой под ситуацию клиента.
MODES = {
    "business": {
        "title": "У меня есть бизнес",
        "icon": "🏢",
        "intro": "Отлично. Расскажите о вашем деле — и офис возьмётся за рост.",
    },
    "launch": {
        "title": "Хочу открыть компанию",
        "icon": "🚀",
        "intro": "Поможем запуститься. Проведу вас по ключевым вопросам старта.",
    },
    "idea": {
        "title": "У меня есть идея",
        "icon": "💡",
        "intro": "Проверим жизнеспособность за один цикл: рынок, экономика, спрос — и вердикт.",
    },
}

# Измерения интервью (порядок = алгоритм). dimension → поле брифа.
_DIMENSIONS = ["product", "client", "revenue", "goal", "constraints"]

# Вопросы по сценарию и измерению.
_INTERVIEW = {
    "business": {
        "product":     "Что вы продаёте? Опишите продукт или услугу.",
        "client":      "Кто ваши клиенты? Опишите целевую аудиторию.",
        "revenue":     "Какой сейчас примерный оборот и средний чек?",
        "goal":        "Какой результат вы хотите от офиса? Что для вас = успех?",
        "constraints": "Есть ограничения или пожелания? (бюджет, что нельзя использовать, "
                       "уже используете CRM/таблицы/рассылки/аналитику — если да, какие)",
    },
    "launch": {
        "product":     "Какой бизнес хотите открыть? Идея продукта или услуги.",
        "client":      "Для кого это? Кто будет покупать?",
        "revenue":     "Какой стартовый бюджет и на какой доход рассчитываете?",
        "goal":        "Какая цель на первые 3 месяца запуска?",
        "constraints": "Что уже есть и какие ограничения? (опыт, команда, деньги)",
    },
    "idea": {
        "product":     "Опишите вашу идею. Что это за продукт или сервис?",
        "client":      "Кто будет этим пользоваться и какую проблему это решает?",
        "revenue":     "Как планируете зарабатывать? Готова ли аудитория платить?",
        "goal":        "Что хотите выяснить — стоит ли вообще это запускать?",
        "constraints": "Сколько готовы вложить времени и денег в проверку идеи?",
    },
}


def interview_questions(mode: str) -> list[dict]:
    """5 вопросов выбранного сценария с метками измерений (для прогресс-бара)."""
    mode = mode if mode in _INTERVIEW else "business"
    qs = _INTERVIEW[mode]
    return [{"dimension": d, "question": qs[d]} for d in _DIMENSIONS]


def _parse_economics(text: str) -> tuple[float | None, float | None]:
    """Best-effort извлечение (бюджет, средний чек) из свободного ответа про оборот/чек
    (Phase 3a: типизированный Brief — вход для прокси-экономики Measurement).
    Возвращает числа как есть (валюта — как ввёл клиент; прокси лиды×чек валюто-
    независим). None, если число не распозналось. Разбор: сначала по ключевым словам
    рядом с числом («чек/средний» → чек, «бюджет/оборот/…» → бюджет), затем остаток
    по убыванию (крупнейшее — бюджет)."""
    import re
    t = (text or "").lower().replace(" ", " ")
    nums: list[tuple[int, float]] = []
    for m in re.finditer(r"\d[\d\s]*\d|\d", t):
        raw = m.group(0).replace(" ", "")
        try:
            nums.append((m.start(), float(raw)))
        except ValueError:
            continue
    if not nums:
        return None, None
    budget = avg = None
    for pos, val in nums:
        window = t[max(0, pos - 25):pos + 6]
        if avg is None and any(k in window for k in ("чек", "средн")):
            avg = val
        elif budget is None and any(k in window for k in
                                    ("бюджет", "оборот", "старт", "влож", "доход", "выручк")):
            budget = val
    remaining = sorted((v for _, v in nums if v not in (budget, avg)), reverse=True)
    if budget is None and remaining:
        budget = remaining.pop(0)
    if avg is None and remaining:
        avg = remaining.pop(0)
    return budget, avg


def build_brief_structured(mode: str, answers: list[dict]) -> dict:
    """
    Детерминированно собирает бриф из ответов интервью — БЕЗ вызова LLM.
    answers: [{"dimension": "...", "answer": "..."}, ...]
    Это делает онбординг устойчивым к нехватке баланса.
    """
    mode = mode if mode in MODES else "business"
    by_dim = {a.get("dimension", ""): (a.get("answer") or "").strip() for a in answers}
    product = by_dim.get("product", "")
    client = by_dim.get("client", "")
    revenue = by_dim.get("revenue", "")
    goal = by_dim.get("goal", "")
    constraints = by_dim.get("constraints", "")

    if mode == "idea":
        # Цель «идеи» — всегда вердикт о жизнеспособности (Research + Finance + Marketing).
        if goal:
            goal = f"Проверить жизнеспособность и дать вердикт: {goal}"
        else:
            goal = f"Проверить жизнеспособность идеи и дать вердикт: {product[:120]}"

    niche = product[:120] or MODES[mode]["title"]
    summary_parts = []
    if product:     summary_parts.append(f"Продукт: {product}")
    if client:      summary_parts.append(f"Клиенты: {client}")
    if revenue:     summary_parts.append(f"Экономика: {revenue}")
    if goal:        summary_parts.append(f"Цель: {goal}")
    if constraints: summary_parts.append(f"Ограничения: {constraints}")
    summary = " ".join(summary_parts) or product or MODES[mode]["title"]

    research_question = (
        f"Актуальные тренды и тактики 2026 в нише: {niche}. Цель: {goal}. "
        f"Что сейчас работает, кейсы, каналы привлечения."
    )

    budget_usd, avg_check_usd = _parse_economics(revenue)

    return {
        "mode": mode,
        "niche": niche,
        "goal": goal,
        "audience": client,
        "assets": revenue,          # сырой ответ (совместимость + человекочитаемо)
        # Типизированная экономика (Phase 3a): числа для прокси-выручки Measurement.
        # None, если клиент не назвал число — тогда прокси-экономики нет до уточнения.
        "budget_usd": budget_usd,
        "avg_check_usd": avg_check_usd,
        "constraints": constraints,
        "research_question": research_question,
        "summary": summary,
    }

# Тексты онбординга — policies/onboarding_{questions,brief}.md. Слот Brief НЕ
# подмешивается (with_brief=False): бриф здесь ещё только формируется.


async def make_questions(
    client_input: str,
    publish: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> list[str]:
    """Возвращает список уточняющих вопросов к клиенту."""
    if publish:
        await publish({"type": "thinking", "agent_id": "onboarding_1",
                       "text": "Изучаю ваш запрос, готовлю вопросы..."})

    from src.office import models as models_module
    from src.office import prompt_builder
    user = f"Ввод клиента:\n{client_input[:3000]}"
    system, _pid = prompt_builder.company_system(
        "onboarding_questions", "onboarding_1", "onboarding", user, with_brief=False)
    raw = await llm.run_agent(
        system=system,
        user=user,
        model=models_module.get_default(),
        max_tokens=500,
        use_search=False,
        agent_id="onboarding_1",
    )
    data = _parse_json(raw)
    questions = data.get("questions", [])
    if not questions:
        questions = [
            "Какая у вас главная цель (какой результат = успех)?",
            "Какая ниша/продукт и кто целевая аудитория?",
            "Что уже есть (соцсети, продукт, бюджет)?",
        ]
    return questions[:5]


async def build_brief(
    client_input: str,
    qa_pairs: list[dict],
    publish: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> dict:
    """Формирует бриф из ввода клиента и его ответов."""
    qa_text = "\n".join(f"В: {p.get('q','')}\nО: {p.get('a','')}" for p in qa_pairs)
    user = f"Ввод клиента:\n{client_input[:2000]}\n\nОтветы на вопросы:\n{qa_text[:2000]}"

    if publish:
        await publish({"type": "thinking", "agent_id": "onboarding_1",
                       "text": "Формирую бриф для офиса..."})

    from src.office import models as models_module
    from src.office import prompt_builder
    system, _pid = prompt_builder.company_system(
        "onboarding_brief", "onboarding_1", "onboarding", user, with_brief=False)
    raw = await llm.run_agent(
        system=system,
        user=user,
        model=models_module.get_default(),
        max_tokens=800,
        use_search=False,
        agent_id="onboarding_1",
    )
    brief = _parse_json(raw)

    # Подстраховка — минимальный бриф
    if not brief.get("summary"):
        brief["summary"] = client_input[:500]
    if not brief.get("research_question"):
        brief["research_question"] = (
            f"Актуальные тренды и тактики 2026 в нише: {brief.get('niche', client_input[:100])}"
        )

    if publish:
        await publish({"type": "speech", "agent_id": "onboarding_1",
                       "text": f"Бриф готов! Запускаю офис под задачу: {brief.get('goal', '')[:80]}"})

    return brief


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw[3:]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start:end + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}
