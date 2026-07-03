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
import re
import time
from typing import Optional, Callable, Awaitable, Any

from dotenv import load_dotenv
from openai import AsyncOpenAI

from src.core.search import web_search

load_dotenv()


def _mask_old_observations(messages: list, keep_last: int = 3) -> None:
    """
    Observation masking: содержимое СТАРЫХ tool-результатов заменяем компактной ссылкой,
    оставляя полными только последние `keep_last`. tool_call_id сохраняем (нужен API).
    Экономит 60-80% токенов истории при <2% потери качества (длинные web_search/файлы
    уже учтены моделью, повторно их слать целиком не нужно).
    """
    tool_idxs = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    for i in tool_idxs[:-keep_last] if keep_last else tool_idxs:
        c = messages[i].get("content", "")
        if c and not c.startswith("[свёрнуто"):
            messages[i] = {**messages[i],
                           "content": f"[свёрнуто: результат инструмента учтён выше, {len(c)} симв.]"}


def _parse_tool_args(raw: str) -> dict:
    """
    Надёжный парсинг аргументов tool-call.

    Дешёвые модели (glm-4.5-flash и т.п.) часто кладут в строковое поле
    (например HTML в `content`) ЖИВЫЕ переносы строк и табы — это невалидный
    строгий JSON, и обычный json.loads падает, теряя весь вызов. Здесь:
      1. json.loads(strict=False) — разрешает control-символы внутри строк;
      2. если и это упало — regex-сальваж: вытаскиваем строковые значения
         известных ключей (path/content/query/...), беря «жадно» всё до
         закрывающей кавычки перед следующим ключом или концом объекта.
    """
    raw = (raw or "").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw, strict=False)
    except (json.JSONDecodeError, ValueError):
        pass
    # Сальваж: ключ → значение-строка (учитываем экранированные кавычки)
    out: dict = {}
    for m in re.finditer(r'"(\w+)"\s*:\s*"((?:[^"\\]|\\.)*)"', raw, re.DOTALL):
        key, val = m.group(1), m.group(2)
        # Разэкранируем основные последовательности
        val = (val.replace('\\n', '\n').replace('\\t', '\t')
                  .replace('\\"', '"').replace('\\\\', '\\').replace("\\/", "/"))
        out[key] = val
    return out


BASE_URL = os.getenv("LLM_BASE_URL", "https://apinet.cloud/v1")
API_KEY = os.getenv("LLM_API_KEY") or os.getenv("ANTHROPIC_API_KEY", "")
DEFAULT_MODEL = os.getenv("LLM_MODEL", "glm-4.5-flash")
# Жёсткий потолок на ОДИН вызов API: без него зависший запрос к провайдеру висит
# бесконечно (watchdog офиса лишь метит агента idle, но саму корутину не убивает),
# продолжая держать соединение. wait_for гарантирует, что вызов завершится.
CALL_TIMEOUT = float(os.getenv("LLM_CALL_TIMEOUT", "180"))
# Потолок на ОДИН веб-поиск. Реальный вис прода: DDG недоступен/медленен →
# asyncio.to_thread(web_search) ждал тред ВЕЧНО, корутина агента зависала, а
# bootstrap (ресёрчер — первый, кто ищет после онбординга) вообще не под watchdog.
# Плюс зависшие треды исчерпывали общий thread-pool — замирали поиски ВСЕХ агентов.
SEARCH_TIMEOUT = float(os.getenv("SEARCH_TIMEOUT", "45"))


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


def _is_model_unavailable(err: Exception) -> bool:
    """503/недоступная модель у провайдера (нет канала, модель не найдена)."""
    s = str(err).lower()
    return ("model_not_found" in s or "no available channel" in s
            or "does not exist" in s or "no such model" in s)


def _fallback_model(failed: str) -> str:
    """
    Безопасная замена недоступной модели: базовая модель офиса, иначе модель из .env,
    иначе почти бесплатная glm. Никогда не возвращаем ту же модель, что упала.
    """
    try:
        from src.office import models as _models
        d = _models.get_default()
        if d and d != failed:
            return d
    except Exception:
        pass
    if DEFAULT_MODEL and DEFAULT_MODEL != failed:
        return DEFAULT_MODEL
    return "glm-4.5-flash" if failed != "glm-4.5-flash" else ""


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
    fellback = False  # фолбэк на доступную модель делаем максимум один раз за запуск
    seen_queries: set[str] = set()  # анти-цикл: не искать одно и то же дважды
    in_tokens = 0
    out_tokens = 0
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user})

    final_text = ""

    for _it in range(max_iterations):
        # Observation masking (context-engineering): результаты инструментов с прошлых
        # итераций сворачиваем в короткую ссылку — модель уже на них отреагировала, но
        # они продолжали пересылаться целиком на каждом вызове (квадратичный раздув,
        # в логах — 197k входных токенов на агента). Последние KEEP держим полными.
        if _it > 0:
            _mask_old_observations(messages, keep_last=3)
        _api_t0 = time.time()
        try:
            import asyncio as _asyncio
            resp = await _asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=tools or None,
                    max_tokens=max_tokens,
                ),
                timeout=CALL_TIMEOUT,
            )
        except Exception as e:
            # Недоступная модель (503/нет канала) НЕ должна зацикливать офис: один раз
            # переключаемся на базовую доступную модель и повторяем этот же шаг.
            fb = _fallback_model(model) if (not fellback and _is_model_unavailable(e)) else ""
            if not fb:
                raise
            fellback = True
            if publish:
                await publish({"type": "system",
                               "text": f"⚠️ Модель «{model}» недоступна — переключаюсь на «{fb}»"})
            model = fb
            continue  # повтор той же итерации с рабочей моделью
        usage = getattr(resp, "usage", None)
        if usage:
            pin = getattr(usage, "prompt_tokens", 0) or 0
            pout = getattr(usage, "completion_tokens", 0) or 0
            in_tokens += pin
            out_tokens += pout
            try:
                from src.office import trace
                trace.log("llm", agent=agent_id, model=model, it=_it,
                          ms=int((time.time() - _api_t0) * 1000), tok_in=pin, tok_out=pout)
            except Exception:
                pass
            # ИНКРЕМЕНТАЛЬНЫЙ учёт: пишем расход СРАЗУ после каждого ответа API,
            # а не в конце run_agent. Иначе длинные/зависшие прогоны (deep research,
            # агент, сброшенный watchdog) тратят реальные деньги, но в индикаторе $0.
            if pin or pout:
                try:
                    from src.office import costs
                    costs.record(agent_id, model, pin, pout)
                except Exception:
                    pass
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

        # Ответ обрезан по длине — аргументы tool-call могли не дописаться (пустой content).
        truncated = getattr(resp.choices[0], "finish_reason", "") == "length"

        # Выполняем инструменты
        for tc in msg.tool_calls:
            name = tc.function.name
            args = _parse_tool_args(tc.function.arguments or "")
            # write_file с пустым/обрезанным content при обрыве по длине — подсказываем модели
            if truncated and name == "write_file" and not (args.get("content") or "").strip():
                messages.append({
                    "role": "tool", "tool_call_id": tc.id,
                    "content": ("Файл НЕ сохранён: ответ оборвался по лимиту длины, content пустой. "
                                "Напиши файл КОРОЧЕ или раздели на несколько файлов (CSS/JS отдельно)."),
                })
                continue

            _tool_t0 = time.time()
            if name == "web_search":
                query = args.get("query", "")
                qnorm = " ".join(query.lower().split())
                if qnorm in seen_queries:
                    # Анти-цикл: тот же запрос уже выполнялся — не жжём поиск/токены.
                    result = ("Этот запрос уже выполнялся в этой задаче. Не повторяй поиск — "
                              "используй то, что уже нашёл, и сделай вывод/результат.")
                elif searches_done >= max_searches:
                    result = ("Достигнут лимит веб-поисков. Хватит искать — "
                              "сделай вывод на основе уже собранных данных.")
                else:
                    searches_done += 1
                    seen_queries.add(qnorm)
                    if publish:
                        await publish({"type": "speech", "agent_id": agent_id,
                                       "text": f"🔍 Ищу: {query[:60]}"})
                    result = await _search_async(query)
            elif tool_handlers and name in tool_handlers:
                result = await tool_handlers[name](args)
            else:
                result = f"Неизвестный инструмент: {name}"

            # Детальный трейс инструмента: что вызвал, ключевой аргумент, сколько занял,
            # размер результата — «куда что ушло» видно в системном логе.
            try:
                from src.office import trace
                arg_hint = args.get("path") or args.get("query") or args.get("need") or \
                    args.get("name") or args.get("question") or ""
                trace.log("tool", agent=agent_id, tool=name, arg=str(arg_hint)[:120],
                          ms=int((time.time() - _tool_t0) * 1000), out_len=len(result or ""))
            except Exception:
                pass

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result[:2500],
            })

    # Модель уложилась в max_iterations, ни разу не написав текст — только tool-calls
    # (реальный кейс: marketer/developer/integrator на нескольких прогонах сдавали
    # out_len=0 после реальных write_file, задачу считали пустой и перезапускали с нуля,
    # теряя уже сделанную работу и раздувая расход). Просим ОДНИМ доп. вызовом без
    # инструментов подвести итог — история с результатами tool-calls уже в messages.
    if not final_text.strip():
        messages.append({"role": "user", "content":
                          "Ты не написал итоговый текст, только вызывал инструменты. "
                          "Подведи итог 1-2 предложениями: что именно сделал (какие файлы "
                          "записал, что решил). Без вызова инструментов."})
        try:
            import asyncio as _asyncio
            resp = await _asyncio.wait_for(
                client.chat.completions.create(model=model, messages=messages, max_tokens=300),
                timeout=CALL_TIMEOUT,
            )
            usage = getattr(resp, "usage", None)
            if usage:
                pin = getattr(usage, "prompt_tokens", 0) or 0
                pout = getattr(usage, "completion_tokens", 0) or 0
                if pin or pout:
                    try:
                        from src.office import costs
                        costs.record(agent_id, model, pin, pout)
                    except Exception:
                        pass
            msg = resp.choices[0].message
            if msg.content and msg.content.strip():
                final_text = msg.content
                if publish:
                    snippet = msg.content[:150].replace("\n", " ").strip()
                    await publish({"type": "speech", "agent_id": agent_id, "text": snippet})
        except Exception:
            pass  # не удалось — вернём как есть, вызывающий код обработает пустой результат

    # Учёт расхода теперь инкрементальный — пишется внутри цикла после каждого
    # ответа API (см. выше), чтобы расход был виден в реальном времени и не терялся
    # при зависании/сбросе агента. Здесь больше ничего записывать не нужно.
    return final_text


async def _search_async(query: str) -> str:
    """DuckDuckGo синхронный — запускаем в потоке, чтобы не блокировать event loop.
    wait_for обязателен: поиск без ответа не должен вешать агента (см. SEARCH_TIMEOUT)."""
    import asyncio
    try:
        return await asyncio.wait_for(asyncio.to_thread(web_search, query),
                                      timeout=SEARCH_TIMEOUT)
    except (asyncio.TimeoutError, TimeoutError):
        return ("Поиск не ответил (сеть или поисковый сервис недоступны). "
                "НЕ повторяй этот запрос — продолжай задачу на основе того, "
                "что уже знаешь, и честно отметь, каких данных не хватило.")
