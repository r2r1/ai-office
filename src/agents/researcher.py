"""
Researcher Agent — первый сотрудник AI-офиса.

Исследует рынок, соцсети и новости, чтобы дать обоснованную рекомендацию
о наиболее эффективном способе заработка 1 млн рублей с помощью AI-агентов.
"""

import json
import os
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

DEFAULT_QUESTION = (
    "Проанализируй актуальные тренды 2026 года и ответь на вопрос: "
    "какой способ заработать 1 миллион рублей с помощью AI-агентов является "
    "наиболее реалистичным и эффективным прямо сейчас? "
    "Изучи реальные кейсы, ниши, монетизацию, конкуренцию и сроки. "
    "Дай конкретный пошаговый план действий."
)

SYSTEM_PROMPT = """Ты — ведущий исследователь AI-офиса. Твоя задача — принимать решения
строго на основе данных из интернета, а не на основе предположений.

Процесс исследования:
1. Сделай серию целенаправленных поисковых запросов (минимум 8–12 запросов).
2. Охвати темы: AI-фриланс, AI SaaS, автоматизация бизнеса, продажа AI-инструментов,
   создание AI-контента, AI-агентства, актуальные кейсы и цифры дохода.
3. Проверь данные по российскому и международному рынкам.
4. Синтезируй находки в структурированный отчёт.

Формат итогового отчёта (обязательно):
- Executive Summary (2–3 предложения)
- Топ-3 бизнес-модели с оценкой потенциала
- Для каждой модели: описание, сроки выхода на 1М руб., стартовые вложения, риски
- Рекомендованная стратегия с пошаговым планом на 90 дней
- Источники и ключевые данные

Пиши по-русски. Будь конкретным — цифры, сроки, реальные примеры."""


def run(question: str = DEFAULT_QUESTION, reports_dir: str = "reports") -> str:
    """Запускает агента-ресёрчера и возвращает итоговый отчёт."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    tools = [{"type": "web_search_20260209", "name": "web_search"}]

    messages = [{"role": "user", "content": question}]

    print("🔍 Агент-ресёрчер начинает исследование...\n")

    iteration = 0
    while True:
        iteration += 1
        print(f"  Итерация {iteration}...", end=" ", flush=True)

        response = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        text_blocks = [b for b in response.content if b.type == "text"]

        if tool_uses:
            print(f"выполняет {len(tool_uses)} поисковых запросов...")
        else:
            print("готово.")

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            break

        tool_results = []
        for tu in tool_uses:
            result_blocks = [
                b for b in response.content
                if hasattr(b, "tool_use_id") and b.tool_use_id == tu.id
            ]
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": [b.model_dump() for b in result_blocks] if result_blocks else [],
            })

        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    final_text = "\n\n".join(b.text for b in text_blocks if b.text)

    _save_report(final_text, reports_dir)

    return final_text


def _save_report(content: str, reports_dir: str) -> Path:
    Path(reports_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = Path(reports_dir) / f"research_{timestamp}.md"
    path.write_text(content, encoding="utf-8")
    print(f"\n📄 Отчёт сохранён: {path}")
    return path
