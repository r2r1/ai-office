"""
Researcher Agent — универсальный исследователь AI-офиса.

Два режима:
  quick — haiku, 2-3 поиска, ~500 токенов, для текущих задач агентов
  deep  — opus,  8-12 поисков, полный отчёт, только для стратегических решений

Другие агенты вызывают: researcher.run(question, depth="quick")
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Awaitable

import anthropic
from dotenv import load_dotenv

load_dotenv()

DEFAULT_QUESTION = (
    "Проанализируй актуальные тренды 2026 года: какой способ заработать "
    "1 миллион рублей с помощью AI-агентов наиболее реалистичен прямо сейчас? "
    "Изучи кейсы, ниши, монетизацию, конкуренцию."
)

# Quick — краткий ответ, дешёвый
_SYSTEM_QUICK = """Ты — исследователь AI-офиса. Отвечай строго на основе данных из поиска.
Сделай 2-3 целенаправленных запроса и дай краткий, конкретный ответ.
Максимум 300 слов. Только факты и цифры — без воды."""

# Deep — полное исследование
_SYSTEM_DEEP = """Ты — ведущий исследователь AI-офиса. Принимай решения строго на основе данных.

Процесс:
1. Сделай 8-12 целенаправленных поисковых запросов.
2. Охвати: тренды, кейсы, цифры, российский и мировой рынки.
3. Синтезируй в структурированный отчёт.

Формат отчёта:
- Executive Summary (2-3 предложения)
- Топ-3 варианта с оценкой потенциала
- Рекомендованная стратегия и план на 90 дней
- Источники

Пиши по-русски. Конкретные цифры, сроки, примеры."""

_MODELS = {
    "quick": "claude-haiku-4-5-20251001",
    "deep":  "claude-opus-4-8",
}
_MAX_TOKENS = {
    "quick": 1500,
    "deep":  12000,
}


async def run_async(
    question: str = DEFAULT_QUESTION,
    depth: str = "quick",
    publish: Optional[Callable[[dict], Awaitable[None]]] = None,
    agent_id: str = "researcher_1",
    save_report: bool = False,
) -> str:
    """Асинхронный запуск ресёрчера. depth='quick'|'deep'."""
    client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    tools = [{"type": "web_search_20260209", "name": "web_search"}]
    system = _SYSTEM_QUICK if depth == "quick" else _SYSTEM_DEEP
    model = _MODELS[depth]
    max_tokens = _MAX_TOKENS[depth]

    if publish:
        await publish({"type": "thinking", "agent_id": agent_id,
                       "text": f"[{depth}] Исследую: {question[:80]}..."})

    messages = [{"role": "user", "content": question}]
    text_blocks = []

    while True:
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            messages=messages,
        )

        text_blocks = [b for b in response.content if b.type == "text"]
        tool_uses  = [b for b in response.content if b.type == "tool_use"]

        if text_blocks and publish:
            snippet = text_blocks[0].text[:150].replace("\n", " ")
            await publish({"type": "speech", "agent_id": agent_id, "text": snippet})

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            break

        tool_results = []
        for tu in tool_uses:
            result_blocks = [b for b in response.content
                             if hasattr(b, "tool_use_id") and b.tool_use_id == tu.id]
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": [b.model_dump() for b in result_blocks] if result_blocks else [],
            })
        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    final_text = "\n\n".join(b.text for b in text_blocks if b.text)

    if save_report:
        _save_report(final_text, depth)

    if publish:
        await publish({"type": "task_done", "agent_id": agent_id,
                       "summary": final_text[:300]})

    return final_text


def run(
    question: str = DEFAULT_QUESTION,
    depth: str = "deep",
    reports_dir: str = "reports",
) -> str:
    """Синхронный запуск (для CLI / main.py)."""
    import asyncio
    result = asyncio.run(run_async(question, depth=depth, save_report=True))
    return result


# Удобные хелперы, которые другие агенты вызывают напрямую
async def quick(question: str, publish=None, agent_id="researcher_1") -> str:
    """2-3 поиска, haiku, ~500 токенов."""
    return await run_async(question, depth="quick", publish=publish, agent_id=agent_id)


async def deep(question: str, publish=None, agent_id="researcher_1") -> str:
    """8-12 поисков, opus, полный отчёт."""
    return await run_async(question, depth="deep", publish=publish, agent_id=agent_id,
                           save_report=True)


def _save_report(content: str, depth: str) -> Path:
    path = Path("reports")
    path.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    p = path / f"research_{depth}_{ts}.md"
    p.write_text(content, encoding="utf-8")
    return p
