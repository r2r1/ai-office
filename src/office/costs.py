"""
Учёт расхода токенов и стоимости работы офиса — по тенанту.
Стоимость считается по прайсу apinet (PRICES).
"""

from src.saas import context as ctx

_FILE = "costs.json"

# Цены в $ за 1M токенов (вход, выход). Сверены с прайсом apinet
# (GET /api/pricing → model_ratio×$2/1M вход, ×completion_ratio выход).
# ⚠️ gpt-5.4 раньше стояла (0.12, 0.72) — это была ОШИБКА ~21x: реальная цена
# $2.5/$15 за 1M. Из-за этого индикатор расхода показывал в ~21 раз меньше реальной
# суммы, списанной с баланса apinet. При смене дефолтной модели сверяйся с /api/pricing.
PRICES: dict[str, tuple[float, float]] = {
    "glm-4.5-flash": (0.01, 0.01), "glm-4-flash": (0.01, 0.01),
    "gpt-5-nano": (0.05, 0.40), "gpt-5-codex": (1.25, 10.0),
    "gpt-5.3-codex": (0.08, 0.64),
    "gpt-4.1-nano": (0.10, 0.40), "gpt-4o-mini": (0.15, 0.60),
    "qwen3-vl-flash": (0.15, 1.50), "gemini-2.5-flash": (0.30, 2.50),
    "kimi-k2": (0.60, 1.50), "qwen3-vl-plus": (1.0, 10.0),
    "gemini-2.5-pro": (1.25, 10.0), "gpt-4.1": (2.0, 8.0),
    "gpt-4o": (2.5, 10.0), "gpt-5.4": (2.5, 15.0),
    "claude-sonnet-4-6": (3.0, 15.0), "claude-opus-4-8": (5.0, 25.0),
}
# Опечатка/новая модель без прайса раньше молча возвращала (0.0, 0.0) — реальный
# расход у apinet идёт, а индикатор показывал $0 (то же семейство бага, что уже
# было с 21x-занижением цены gpt-5.4 выше). Лучше переоценить, чем спрятать
# реальные траты: неизвестная модель получает консервативную оценку (медиану
# известных цен), а не ноль. Медиана считается ДО добавления эмбеддингов ниже —
# они на порядок дешевле чат-моделей и увели бы этот фолбэк вниз для ВСЕХ
# неизвестных чат-моделей, если бы попали в выборку.
DEFAULT_PRICE = (
    sorted(p[0] for p in PRICES.values())[len(PRICES) // 2],
    sorted(p[1] for p in PRICES.values())[len(PRICES) // 2],
)

# Эмбеддинги (src/core/embeddings.py) — billятся только по входным токенам,
# цена OpenAI text-embedding-3-small ($0.02/1M) на порядок ниже чат-моделей.
# Добавлена ПОСЛЕ вычисления DEFAULT_PRICE (см. комментарий выше).
PRICES["text-embedding-3-small"] = (0.02, 0.0)
_warned_models: set[str] = set()


def price_for(model: str) -> tuple[float, float]:
    m = (model or "").strip()
    price = PRICES.get(m)
    if price is None and m and m not in _warned_models:
        _warned_models.add(m)
        print(f"⚠️ costs.py: нет цены для модели «{m}» в PRICES — использую "
              f"консервативную оценку {DEFAULT_PRICE} вместо $0. Добавь реальную "
              f"цену из GET /api/pricing apinet.")
    return price or DEFAULT_PRICE


def _all() -> dict:
    return ctx.read_json(_FILE, {})


def _today() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _agents_only(data: dict) -> dict:
    """Записи агентов без служебных ключей (напр. '_daily')."""
    return {k: v for k, v in data.items() if not k.startswith("_")}


def record(agent_id: str, model: str, in_tokens: int, out_tokens: int) -> None:
    agent_id = agent_id or "unknown"
    pin, pout = price_for(model)
    cost = in_tokens / 1_000_000 * pin + out_tokens / 1_000_000 * pout
    data = _all()
    a = data.setdefault(agent_id, {"model": model, "in_tokens": 0, "out_tokens": 0, "cost": 0.0, "calls": 0})
    a["model"] = model or a["model"]
    a["in_tokens"] += int(in_tokens or 0)
    a["out_tokens"] += int(out_tokens or 0)
    a["cost"] += cost
    a["calls"] += 1
    # Посуточный расход для дневного лимита. Служебный ключ '_daily' исключён из
    # totals()/by_agent(), чтобы не считался «агентом».
    daily = data.setdefault("_daily", {})
    daily[_today()] = round(daily.get(_today(), 0.0) + cost, 6)
    # Держим только последние ~7 дат, иначе словарь растёт бесконечно.
    if len(daily) > 7:
        for k in sorted(daily)[:-7]:
            daily.pop(k, None)
    ctx.write_json(_FILE, data)


def spent_today() -> float:
    return float(_all().get("_daily", {}).get(_today(), 0.0))


def for_agent(agent_id: str) -> dict:
    return _all().get(agent_id, {"in_tokens": 0, "out_tokens": 0, "cost": 0.0, "calls": 0})


def totals() -> dict:
    t = {"in_tokens": 0, "out_tokens": 0, "cost": 0.0, "calls": 0}
    for a in _agents_only(_all()).values():
        t["in_tokens"] += a["in_tokens"]
        t["out_tokens"] += a["out_tokens"]
        t["cost"] += a["cost"]
        t["calls"] += a["calls"]
    return t


def by_agent() -> list[dict]:
    out = [dict(v, agent_id=k) for k, v in _agents_only(_all()).items()]
    out.sort(key=lambda x: x["cost"], reverse=True)
    return out


def payload() -> dict:
    return {"total": totals(), "agents": by_agent()}


# ── Бюджетные лимиты (Конституция → авто-пауза при превышении) ───────────────
_LIMITS_FILE = "limits.json"


def limits() -> dict:
    """Лимиты расхода: {total_usd, daily_usd}; 0 = без лимита."""
    return ctx.read_json(_LIMITS_FILE, {"total_usd": 0.0, "daily_usd": 0.0})


def set_limits(total_usd: float = 0.0, daily_usd: float = 0.0) -> None:
    ctx.write_json(_LIMITS_FILE, {
        "total_usd": max(0.0, float(total_usd or 0)),
        "daily_usd": max(0.0, float(daily_usd or 0)),
    })


def _effective_total_cap() -> float:
    """Единый общий лимит: минимальный ненулевой из «Лимиты» и порога Конституции."""
    total_cap = limits().get("total_usd", 0.0)
    try:
        from src.office import constitution
        c_cap = constitution.budget_auto_limit()
        if c_cap > 0:
            total_cap = c_cap if total_cap <= 0 else min(total_cap, c_cap)
    except Exception:
        pass
    return total_cap


def over_limit() -> bool:
    """Превышен ли ОБЩИЙ или ДНЕВНОЙ лимит расхода (для авто-паузы)."""
    total_cap = _effective_total_cap()
    daily_cap = limits().get("daily_usd", 0.0)
    if total_cap > 0 and totals()["cost"] >= total_cap:
        return True
    if daily_cap > 0 and spent_today() >= daily_cap:
        return True
    return False


def would_exceed(estimated_usd: float) -> bool:
    """Выйдет ли ПРЕДСТОЯЩИЙ платный шаг за лимиты (BOS §6: estimated_cost сверяется
    с бюджетом ДО исполнения, а не после). 0/отрицательная оценка → не блокируем."""
    if estimated_usd <= 0:
        return False
    total_cap = _effective_total_cap()
    daily_cap = limits().get("daily_usd", 0.0)
    if total_cap > 0 and totals()["cost"] + estimated_usd > total_cap:
        return True
    if daily_cap > 0 and spent_today() + estimated_usd > daily_cap:
        return True
    return False


def limit_payload() -> dict:
    lim = limits()
    return {
        "total_usd": lim.get("total_usd", 0.0),
        "daily_usd": lim.get("daily_usd", 0.0),
        "spent": totals()["cost"],
        "spent_today": spent_today(),
        "over_limit": over_limit(),
    }


def load() -> None:
    pass


def reset() -> None:
    ctx.delete_file(_FILE)
