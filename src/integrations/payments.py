"""
Интеграция «Приём платежей» — TEST-режим без реального провайдера.

Реального Stripe/ЮKassa/CloudPayments ключа сегодня нет (см. docs/product-capability-gaps.md
п.1) — вместо того чтобы оставить способность отсутствующей целиком, здесь живой
песочный движок: создаёт настоящие записи о платеже (payments.json), с
детерминированной ссылкой и статусом pending → paid, которые агент и
пользователь видят и могут проверить прямо сейчас. Когда появится реальный ключ
провайдера — добавь `CredField` в `cred_fields` и в `_create_payment_link`
разветвление «есть секретный ключ → реальный вызов API, иначе — эта песочница»;
внешний контракт действий (name/params/что возвращает агенту) менять не нужно —
агент и промпты уже умеют работать с этой формой данных.

Данные — TEST-режим, не воображаемые: `create_payment_link` создаёт реальную
запись в `payments.json` тенанта, `mark_paid` (вызывается с тестового
эндпоинта `/api/payments/{tenant}/{payment_id}/mark-paid`, имитирующего вебхук
провайдера) реально меняет её статус — офис учится РАБОТАТЬ с формой данных
платежа (id, статус, сумма, ссылка) до того, как эта форма станет настоящей.
"""

import time
import uuid

from src.integrations.base import Action, Integration
from src.saas import context as ctx

_FILE = "payments.json"
_STATUSES = ("pending", "paid", "failed", "canceled")


def _all() -> list[dict]:
    return ctx.read_json(_FILE, [])


def _save(items: list[dict]) -> None:
    ctx.write_json(_FILE, items)


def get(payment_id: str) -> dict | None:
    for p in _all():
        if p["id"] == payment_id:
            return p
    return None


def list_payments() -> list[dict]:
    return sorted(_all(), key=lambda p: p.get("created_ts", 0), reverse=True)


def mark_paid(payment_id: str) -> dict | None:
    """Имитация вебхука провайдера ("оплата прошла") — для теста без реального ключа."""
    items = _all()
    for p in items:
        if p["id"] == payment_id and p["status"] == "pending":
            p["status"] = "paid"
            p["paid_ts"] = time.time()
            _save(items)
            return p
    return None


async def _create_payment_link(creds: dict, params: dict) -> str:
    amount = params.get("amount")
    try:
        amount = round(float(amount), 2)
    except (TypeError, ValueError):
        return "Нужна сумма (amount) — число больше нуля."
    if amount <= 0:
        return "Сумма должна быть больше нуля."
    currency = (params.get("currency") or "RUB").strip().upper()[:3]
    description = (params.get("description") or "Оплата услуги").strip()[:200]

    tid = ctx.get_tenant()
    pid = f"test_pay_{uuid.uuid4().hex[:10]}"
    checkout_url = f"/pay/{tid}/{pid}"
    items = _all()
    items.append({
        "id": pid, "amount": amount, "currency": currency, "description": description,
        "status": "pending", "created_ts": time.time(), "paid_ts": None,
        "checkout_url": checkout_url, "provider": "test",
    })
    _save(items)
    return (f"Тестовая ссылка на оплату создана: {checkout_url} "
            f"(id: {pid}, {amount} {currency}, «{description}»). "
            f"⚠️ Реальный платёжный провайдер не подключён — это песочница: "
            f"ссылка не принимает настоящие деньги, статус можно проверить через "
            f"get_payment_status. Отправь ссылку клиенту как заглушку, пока владелец "
            f"не подключит настоящий Stripe/ЮKassa в «Доступы».")


async def _get_payment_status(creds: dict, params: dict) -> str:
    pid = (params.get("payment_id") or "").strip()
    p = get(pid)
    if p is None:
        return f"Платёж {pid} не найден."
    status_ru = {"pending": "ожидает оплаты", "paid": "оплачен",
                 "failed": "не прошёл", "canceled": "отменён"}.get(p["status"], p["status"])
    return f"Платёж {pid}: {status_ru}, {p['amount']} {p['currency']} («{p['description']}»)."


INTEGRATION = Integration(
    name="payments",
    title="Приём платежей",
    category="publishing",
    icon="💳",
    description="TEST-режим приёма оплаты: создаёт ссылку и учитывает статус, "
                "пока не подключён реальный провайдер (Stripe/ЮKassa/CloudPayments).",
    how_to="Сейчас работает в тестовом режиме без ключей — ссылки не принимают "
           "настоящие деньги. Чтобы принимать реальные платежи, добавь ключ провайдера "
           "здесь, когда он появится (раздел будет обновлён под конкретного провайдера).",
    cred_fields=[],  # test-режим доступен всегда; реальный провайдер добавится сюда позже
    actions={
        "create_payment_link": Action(
            name="create_payment_link",
            description="Создать ссылку на оплату (тестовый режим, пока нет реального провайдера).",
            handler=_create_payment_link,
            params={
                "amount": {"type": "number", "description": "Сумма к оплате"},
                "currency": {"type": "string", "description": "Валюта, например RUB/USD"},
                "description": {"type": "string", "description": "За что платёж"},
            },
            required=["amount"],
            synonyms=["оплата", "платёж", "платеж", "счёт", "счет", "payment", "оплатить", "чек"],
        ),
        "get_payment_status": Action(
            name="get_payment_status",
            description="Проверить статус созданного платежа по id.",
            handler=_get_payment_status,
            params={"payment_id": {"type": "string", "description": "id платежа"}},
            required=["payment_id"],
            synonyms=["статус оплаты", "проверить платёж"],
        ),
    },
)
