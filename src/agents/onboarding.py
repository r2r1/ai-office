"""
Onboarding Agent — встречает клиента.

Читает любой ввод клиента (идея / соцсети / инструкции) и:
1. Задаёт 3-5 уточняющих вопросов, чтобы понять задачу.
2. По ответам формирует структурированный бриф для всего офиса.
"""

import json
from typing import Optional, Callable, Awaitable

from src.core import llm

_QUESTIONS_SYSTEM = """Ты — менеджер по работе с клиентами AI-офиса. Клиент прислал тебе
свою идею / ссылки на соцсети / инструкции. Твоя задача — задать 3-5 КОРОТКИХ уточняющих
вопросов, чтобы офис понял что делать.

Спрашивай о главном: цель и сроки, ниша/продукт, целевая аудитория, бюджет, что уже есть,
какой результат считается успехом.

Ответь ТОЛЬКО валидным JSON без markdown:
{"questions": ["Вопрос 1?", "Вопрос 2?", "Вопрос 3?"]}"""

_BRIEF_SYSTEM = """Ты — менеджер AI-офиса. На основе ввода клиента и его ответов на вопросы
сформируй структурированный бриф, по которому будет работать весь офис.

Ответь ТОЛЬКО валидным JSON без markdown:
{
  "niche": "ниша/сфера клиента",
  "goal": "конкретная цель клиента",
  "audience": "целевая аудитория",
  "assets": "что уже есть у клиента (соцсети, продукт, бюджет)",
  "research_question": "конкретный вопрос для агента-ресёрчера про тренды и тактику в этой нише",
  "summary": "краткое резюме брифа в 3-4 предложениях для всех агентов офиса"
}"""


async def make_questions(
    client_input: str,
    publish: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> list[str]:
    """Возвращает список уточняющих вопросов к клиенту."""
    if publish:
        await publish({"type": "thinking", "agent_id": "onboarding_1",
                       "text": "Изучаю ваш запрос, готовлю вопросы..."})

    raw = await llm.run_agent(
        system=_QUESTIONS_SYSTEM,
        user=f"Ввод клиента:\n{client_input[:3000]}",
        max_tokens=500,
        use_search=False,
        agent_id="onboarding_1",
    )
    data = _parse_json(raw)
    questions = data.get("questions", [])
    if not questions:
        questions = [
            "Какая у вас главная цель и за какой срок?",
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

    raw = await llm.run_agent(
        system=_BRIEF_SYSTEM,
        user=user,
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
