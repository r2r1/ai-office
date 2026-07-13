"""
Billing-provider abstraction (issue #5, docs/architecture-improvements.md).

Раньше распознавание "нет баланса"/"модель недоступна" жило как строковые
паттерны прямо в `core/llm.py` (`is_quota_error`/`is_model_unavailable_error`),
завязанные на конкретный формат ошибок apinet (в т.ч. китайский текст шлюза —
"额度不足"/"余额不足"). Смена или добавление второго LLM-провайдера означало
править эти функции внутри `core/llm.py`. Теперь это регистрация нового
`BillingProvider` здесь — `core/llm.py` не меняется.

`core/llm.py.is_quota_error/is_model_unavailable_error` остаются как есть по
сигнатуре (ничего не сломано у execution.py и прочих вызывающих) — внутри
делегируют активному провайдеру из этого модуля.
"""

from dataclasses import dataclass
from typing import Callable


@dataclass
class BillingProvider:
    id: str
    label: str
    is_quota_error: Callable[[str], bool]
    is_model_unavailable_error: Callable[[str], bool]


_REGISTRY: dict[str, BillingProvider] = {}
_active_id = "apinet"


def register(provider: BillingProvider) -> None:
    _REGISTRY[provider.id] = provider


def active() -> BillingProvider:
    return _REGISTRY[_active_id]


def set_active(provider_id: str) -> None:
    if provider_id not in _REGISTRY:
        raise ValueError(f"Неизвестный billing-provider: {provider_id} "
                          f"(зарегистрированы: {', '.join(_REGISTRY) or '—'})")
    global _active_id
    _active_id = provider_id


def _apinet_is_quota_error(err: str) -> bool:
    err = err or ""
    low = err.lower()
    return (
        "insufficient" in low or "额度不足" in err or "余额不足" in err
        or ("403" in err and ("quota" in low or "balance" in low or "额度" in err or "余额" in err))
        or "预扣费" in err
    )


def _apinet_is_model_unavailable_error(err: str) -> bool:
    low = (err or "").lower()
    return "model_not_found" in low or "no available channel" in low


register(BillingProvider(
    id="apinet", label="apinet.cloud",
    is_quota_error=_apinet_is_quota_error,
    is_model_unavailable_error=_apinet_is_model_unavailable_error,
))
