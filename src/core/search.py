"""
Веб-поиск через DuckDuckGo — бесплатно, без API-ключа.
Заменяет встроенный web_search Anthropic для работы с любым LLM-провайдером.
"""

from typing import Optional


def web_search(query: str, max_results: int = 5, timeout: int = 20) -> str:
    """Ищет в DuckDuckGo и возвращает отформатированный текст результатов.

    `timeout` — потолок HTTP-запросов внутри DDGS. Без него зависший поисковик
    (DDG в РФ нередко блокируется/стоит) держал тред вечно; треды копились в общем
    пуле asyncio.to_thread и в итоге замораживали ВСЕ поиски всех агентов.
    """
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # старое имя пакета
        except ImportError:
            return "Ошибка: установите пакет 'ddgs' (pip install ddgs)"

    try:
        results = []
        try:
            client = DDGS(timeout=timeout)
        except TypeError:  # версия библиотеки без параметра timeout
            client = DDGS()
        with client as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append(r)
    except Exception as e:
        return f"Ошибка поиска: {e}"

    if not results:
        return "Ничего не найдено."

    lines = [f"Результаты поиска по запросу «{query}»:\n"]
    for i, r in enumerate(results, 1):
        title = r.get("title", "")
        body = r.get("body", "")
        href = r.get("href", "")
        lines.append(f"{i}. {title}\n   {body}\n   {href}\n")

    return "\n".join(lines)
