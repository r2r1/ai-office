"""
Единый LLM-клиент для всех агентов (OpenAI-совместимый формат).

Работает с apinet.cloud и любым OpenAI-совместимым провайдером.
Веб-поиск реализован через DuckDuckGo (бесплатно), а не через
встроенные серверные инструменты — поэтому работает с любой моделью.

Настройки через .env:
    LLM_BASE_URL=https://apinet.cloud/v1
    LLM_API_KEY=sk-...
    LLM_MODEL=qwen3-vl-plus
"""

import json
import os
from typing import Optional, Callable, Awaitable, Any

from dotenv import load_dotenv
from openai import AsyncOpenAI

from src.core.search import web_search

load_dotenv()

BASE_URL = os.getenv("LLM_BASE_URL", "https://apinet.cloud/v1")
API_KEY = os.getenv("LLM_API_KEY") or os.getenv("ANTHROPIC_API_KEY", "")
DEFAULT_MODEL = os.getenv("LLM_MODEL", "glm-4.5-flash")


def _resolve_creds() -> tuple[str, str]:
    """Креды LLM текущего тенанта (свой ключ клиента) или общий из .env."""
    try:
        from src.office import llm_settings
        return llm_settings.credentials()
    except Exception:
        return BASE_URL, API_KEY

# Инструмент веб-поиска в формате OpenAI function calling
WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Ищет актуальную информацию в интернете. Используй для трендов, цен, новостей, кейсов.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Поисковый запрос"},
            },
            "required": ["query"],
        },
    },
}


def _client() -> AsyncOpenAI:
    base_url, api_key = _resolve_creds()
    return AsyncOpenAI(base_url=base_url, api_key=api_key)


async def run_agent(
    system: str,
    user: str,
    model: Optional[str] = None,
    max_tokens: int = 2000,
    use_search: bool = True,
    publish: Optional[Callable[[dict], Awaitable[None]]] = None,
    agent_id: str = "agent",
    extra_tools: Optional[list] = None,
    tool_handlers: Optional[dict[str, Callable[[dict], Awaitable[str]]]] = None,
    max_iterations: int = 8,
    history: Optional[list[dict[str, str]]] = None,
    max_searches: int = 5,
) -> str:
    """
    Запускает агентный цикл: LLM думает, вызывает инструменты, отвечает.

    extra_tools     — дополнительные инструменты (формат OpenAI function).
    tool_handlers   — {имя_инструмента: async-функция(args)->str} для extra_tools.
    history         — предыдущие реплики диалога [{role, content}] для памяти.
    max_searches    — жёсткий лимит web_search за один запуск (экономия токенов/времени).
    """
    client = _client()
    model = model or DEFAULT_MODEL

    tools = []
    if use_search:
        tools.append(WEB_SEARCH_TOOL)
    if extra_tools:
        tools.extend(extra_tools)

    # Глобальная директива: дешёвые модели иначе срываются на китайский/воду.
    system = system + "\n\nПиши только на русском языке. Будь краток и по делу, без воды."

    searches_done = 0
    in_tokens = 0
    out_tokens = 0
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user})

    final_text = ""

    for _ in range(max_iterations):
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools or None,
            max_tokens=max_tokens,
        )
        usage = getattr(resp, "usage", None)
        if usage:
            in_tokens += getattr(usage, "prompt_tokens", 0) or 0
            out_tokens += getattr(usage, "completion_tokens", 0) or 0
        msg = resp.choices[0].message

        if msg.content and msg.content.strip():
            final_text = msg.content
            if publish:
                snippet = msg.content[:150].replace("\n", " ").strip()
                if snippet:  # не публикуем пустые «мысли» (дешёвые модели их плодят)
                    await publish({"type": "speech", "agent_id": agent_id, "text": snippet})

        # Добавляем ответ ассистента в историю
        assistant_msg: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant_msg)

        if not msg.tool_calls:
            break

        # Выполняем инструменты
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            if name == "web_search":
                if searches_done >= max_searches:
                    result = ("Достигнут лимит веб-поисков. Хватит искать — "
                              "сделай вывод на основе уже собранных данных.")
                else:
                    searches_done += 1
                    query = args.get("query", "")
                    if publish:
                        await publish({"type": "speech", "agent_id": agent_id,
                                       "text": f"🔍 Ищу: {query[:60]}"})
                    result = await _search_async(query)
            elif tool_handlers and name in tool_handlers:
                result = await tool_handlers[name](args)
            else:
                result = f"Неизвестный инструмент: {name}"

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result[:4000],
            })

    # Учёт расхода токенов/стоимости (ленивый импорт — core не зависит от office)
    if in_tokens or out_tokens:
        try:
            from src.office import costs
            costs.record(agent_id, model, in_tokens, out_tokens)
        except Exception:
            pass

    return final_text


async def _search_async(query: str) -> str:
    """DuckDuckGo синхронный — запускаем в потоке, чтобы не блокировать event loop."""
    import asyncio
    return await asyncio.to_thread(web_search, query)
