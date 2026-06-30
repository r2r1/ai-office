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
    "gpt-5-nano": (0.05, 0.40), "gpt-5.3-codex": (0.08, 0.64),
    "gpt-4.1-nano": (0.10, 0.40), "gpt-4o-mini": (0.15, 0.60),
    "qwen3-vl-flash": (0.15, 1.50), "gemini-2.5-flash": (0.30, 2.50),
    "kimi-k2": (0.60, 1.50), "qwen3-vl-plus": (1.0, 10.0),
    "gemini-2.5-pro": (1.25, 10.0), "gpt-4.1": (2.0, 8.0),
    "gpt-4o": (2.5, 10.0), "gpt-5.4": (2.5, 15.0),
    "claude-sonnet-4-6": (3.0, 15.0), "claude-opus-4-8": (5.0, 25.0),
}
DEFAULT_PRICE = (0.0, 0.0)


def price_for(model: str) -> tuple[float, float]:
    return PRICES.get((model or "").strip(), DEFAULT_PRICE)


def _all() -> dict:
    return ctx.read_json(_FILE, {})


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
    ctx.write_json(_FILE, data)


def for_agent(agent_id: str) -> dict:
    return _all().get(agent_id, {"in_tokens": 0, "out_tokens": 0, "cost": 0.0, "calls": 0})


def totals() -> dict:
    t = {"in_tokens": 0, "out_tokens": 0, "cost": 0.0, "calls": 0}
    for a in _all().values():
        t["in_tokens"] += a["in_tokens"]
        t["out_tokens"] += a["out_tokens"]
        t["cost"] += a["cost"]
        t["calls"] += a["calls"]
    return t


def by_agent() -> list[dict]:
    out = [dict(v, agent_id=k) for k, v in _all().items()]
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


def over_limit() -> bool:
    """Превышен ли общий лимит расхода (для авто-паузы)."""
    lim = limits()
    cap = lim.get("total_usd", 0.0)
    return cap > 0 and totals()["cost"] >= cap


def limit_payload() -> dict:
    lim = limits()
    spent = totals()["cost"]
    return {
        "total_usd": lim.get("total_usd", 0.0),
        "daily_usd": lim.get("daily_usd", 0.0),
        "spent": spent,
        "over_limit": over_limit(),
    }


def load() -> None:
    pass


def reset() -> None:
    ctx.delete_file(_FILE)
