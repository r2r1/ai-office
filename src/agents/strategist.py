"""
Strategist Agent — второй сотрудник AI-офиса.

Берёт отчёт агента-ресёрчера и превращает выбранную бизнес-модель
в конкретный, исполнимый план действий: задачи, метрики, ресурсы,
90-дневная дорожная карта с разбивкой по неделям.
"""

import os
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

SYSTEM_PROMPT = """Ты — главный стратег AI-офиса. На вход ты получаешь исследовательский
отчёт от агента-ресёрчера с рекомендованной бизнес-моделью для заработка 1 млн рублей.

Твоя задача — превратить рекомендацию в конкретный исполнимый план, по которому
другие агенты офиса (продажник, разработчик, контент-менеджер) смогут работать.

Используй веб-поиск, чтобы уточнить детали: реальные цены на рынке, инструменты,
площадки для поиска клиентов, примеры офферов конкурентов.

Формат итогового плана (обязательно):
1. Выбранная модель и цель — что именно делаем и какая финансовая цель (1М руб.)
2. Юнит-экономика — сколько нужно клиентов/продаж × средний чек = 1М руб.
3. Декомпозиция на задачи — список конкретных задач с назначением агенту-исполнителю
   (формат: [АГЕНТ] задача → ожидаемый результат)
4. Дорожная карта 90 дней — по неделям, с измеримыми целями (KPI на каждую неделю)
5. Необходимые ресурсы — инструменты, бюджет, аккаунты, доступы
6. Метрики успеха и точки контроля — когда и что проверять, критерии разворота (pivot)
7. Риски и план Б

Пиши по-русски. Будь предельно конкретным: цифры, сроки, чек-листы, а не общие слова.
План должен быть таким, чтобы по нему можно было начать работать завтра."""


def run(research_report: str, reports_dir: str = "reports") -> str:
    """Запускает агента-стратега на основе отчёта ресёрчера."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    tools = [{"type": "web_search_20260209", "name": "web_search"}]

    user_message = (
        "Вот исследовательский отчёт от агента-ресёрчера. "
        "Выбери из него наиболее перспективную бизнес-модель и составь "
        "по ней детальный исполнимый план действий.\n\n"
        f"=== ОТЧЁТ РЕСЁРЧЕРА ===\n{research_report}"
    )

    messages = [{"role": "user", "content": user_message}]

    print("🧭 Агент-стратег составляет план...\n")

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
            print(f"уточняет детали ({len(tool_uses)} запросов)...")
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

    _save_plan(final_text, reports_dir)

    return final_text


def _save_plan(content: str, reports_dir: str) -> Path:
    Path(reports_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = Path(reports_dir) / f"plan_{timestamp}.md"
    path.write_text(content, encoding="utf-8")
    print(f"\n📋 План сохранён: {path}")
    return path
