"""
Эмбеддинги для поиска по памяти (docs/audit-dd-2026-07-06.md §8/§19 п.11 —
`knowledge.py` искал релевантные факты только по пересечению ключевых слов,
без учёта смысла: факт «клиент недоволен ценой» не находился по запросу
«жалоба на дороговизну», хотя семантически совпадает).

Синхронный клиент (не AsyncOpenAI, как в core/llm.py) — `knowledge.retrieve()`/
`remember()` синхронны и вызываются из десятков мест без await; перевод их в
async потребовал бы каскадных правок по всей цепочке вызовов ради одной
фичи. Эмбеддинги — вторичный, необязательный сигнал: любая ошибка (сеть,
нехватка баланса на счету apinet, провайдер не поддерживает модель) должна
molча деградировать к прежнему поведению (чистый TF-скор), а не ронять
retrieve().

Проверено вживую (2026-07-06): apinet ПОДДЕРЖИВАЕТ /v1/embeddings — реальный
вызов был корректно принят и смаршрутизирован, отклонён только по причине
insufficient_user_quota (баланс аккаунта ~$0). Сама интеграция не проверена
на РЕАЛЬНО полученном векторе — это следует сделать после пополнения баланса,
прежде чем полагаться на семантический скор в проде.
"""

import os

from src.office import trace

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
_MAX_CHARS = 4000  # грубый лимит на вход — эмбеддинг факта/задачи не требует полного текста

# Кеш ПО ТЕНАНТУ, не один глобальный клиент на процесс: у тенантов бывают разные
# свои ключи/base_url (llm_settings.py) и теперь разные прокси (admin-панель,
# per-tenant proxy_url) — единый глобальный `_client` кешировал бы настройки
# ПЕРВОГО тенанта, обратившегося в этом процессе, и молча раздавал их всем
# остальным тенантам того же процесса.
_clients: dict[str, object] = {}
_unavailable_warned = False


def _get_client():
    from src.saas import context as ctx
    tid = ctx.get_tenant() or "_default"
    if tid in _clients:
        return _clients[tid]
    try:
        import httpx
        from openai import OpenAI
        from src.core.llm import _resolve_creds, _resolve_proxy
        base_url, api_key = _resolve_creds()
        proxy = _resolve_proxy()
        if proxy:
            client = OpenAI(base_url=base_url, api_key=api_key,
                             http_client=httpx.Client(proxy=proxy))
        else:
            client = OpenAI(base_url=base_url, api_key=api_key)
    except Exception:
        client = False  # помечаем «недоступно», чтобы не пересоздавать клиент каждый вызов
    _clients[tid] = client
    return client


def embed(text: str, agent_id: str = "knowledge_embeddings") -> list[float] | None:
    """Возвращает вектор эмбеддинга или None при ЛЮБОЙ ошибке (сеть, баланс,
    провайдер не поддерживает модель) — вызывающий код обязан деградировать
    к прежнему поведению, а не падать."""
    global _unavailable_warned
    text = (text or "").strip()
    if not text:
        return None
    client = _get_client()
    if not client:
        return None
    try:
        resp = client.embeddings.create(model=EMBEDDING_MODEL, input=text[:_MAX_CHARS])
        usage = getattr(resp, "usage", None)
        if usage:
            try:
                from src.office import costs
                # Эмбеддинги billятся только по входным токенам (нет output).
                costs.record(agent_id, EMBEDDING_MODEL,
                            getattr(usage, "prompt_tokens", 0) or getattr(usage, "total_tokens", 0) or 0, 0)
            except Exception:
                pass
        return list(resp.data[0].embedding)
    except Exception as e:
        if not _unavailable_warned:
            _unavailable_warned = True
            trace.log("embeddings_unavailable", model=EMBEDDING_MODEL,
                      error=f"{type(e).__name__}: {str(e)[:200]}")
        return None


def cosine(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
