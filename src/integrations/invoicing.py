"""
Интеграция «Счета» — TEST-режим без реального провайдера инвойсинга.

Реального сервиса выставления счетов сегодня нет (docs/product-capability-gaps.md
п.7) — как и в payments.py/deploy.py, здесь живая песочница: создаёт настоящую
запись счёта (invoices.json) с номером, позициями и суммой, в форме, которую
вернёт реальный провайдер. Когда он появится — меняется только тело
`_create_invoice` (реальный HTTP-вызов вместо генерации записи), контракт
действия для агента остаётся прежним.
"""

import time
import uuid

from src.integrations.base import Action, Integration
from src.saas import context as ctx

_FILE = "invoices.json"


def _all() -> list[dict]:
    return ctx.read_json(_FILE, [])


def _save(items: list[dict]) -> None:
    ctx.write_json(_FILE, items)


def get(invoice_id: str) -> dict | None:
    for i in _all():
        if i["id"] == invoice_id:
            return i
    return None


def list_invoices() -> list[dict]:
    return sorted(_all(), key=lambda i: i.get("created_ts", 0), reverse=True)


def mark_paid(invoice_id: str) -> dict | None:
    items = _all()
    for i in items:
        if i["id"] == invoice_id and i["status"] == "issued":
            i["status"] = "paid"
            i["paid_ts"] = time.time()
            _save(items)
            return i
    return None


async def _create_invoice(creds: dict, params: dict) -> str:
    client_name = (params.get("client_name") or "").strip()
    if not client_name:
        return "Нужно имя клиента (client_name)."
    items_raw = params.get("items") or []
    if isinstance(items_raw, str):
        # Агент иногда присылает позиции строкой "Услуга — 5000" по одной на строку.
        items_raw = [x.strip() for x in items_raw.split("\n") if x.strip()]
    line_items = []
    total = 0.0
    for it in items_raw:
        if isinstance(it, dict):
            name = (it.get("name") or "Позиция").strip()
            amount = float(it.get("amount") or 0)
        else:
            parts = str(it).rsplit("-", 1)
            name = parts[0].strip() if parts else str(it)
            try:
                amount = float(parts[1].strip()) if len(parts) > 1 else 0.0
            except ValueError:
                amount = 0.0
        line_items.append({"name": name, "amount": round(amount, 2)})
        total += amount
    if not line_items:
        return "Нужна хотя бы одна позиция в items."

    tid = ctx.get_tenant()
    inv_id = f"test_inv_{uuid.uuid4().hex[:8]}"
    number = f"INV-{int(time.time()) % 1000000}"
    pdf_url = f"/invoice/{tid}/{inv_id}.pdf"  # заглушка — реальный PDF не генерируется
    entry = {
        "id": inv_id, "number": number, "client_name": client_name,
        "items": line_items, "total": round(total, 2),
        "currency": (params.get("currency") or "RUB").strip().upper()[:3],
        "status": "issued", "created_ts": time.time(), "paid_ts": None, "pdf_url": pdf_url,
    }
    items = _all()
    items.append(entry)
    _save(items)
    return (f"Тестовый счёт {number} создан для «{client_name}»: {entry['total']} {entry['currency']} "
            f"({len(line_items)} позици(й)), id: {inv_id}. "
            f"⚠️ Реальный провайдер инвойсинга не подключён — PDF не генерируется, это заготовка "
            f"формы данных на будущее.")


async def _get_invoice_status(creds: dict, params: dict) -> str:
    inv_id = (params.get("invoice_id") or "").strip()
    inv = get(inv_id)
    if inv is None:
        return f"Счёт {inv_id} не найден."
    status_ru = {"issued": "выставлен, не оплачен", "paid": "оплачен"}.get(inv["status"], inv["status"])
    return f"Счёт {inv['number']}: {status_ru}, {inv['total']} {inv['currency']}."


INTEGRATION = Integration(
    name="invoicing",
    title="Счета",
    category="publishing",
    icon="🧾",
    description="TEST-режим выставления счетов: создаёт запись с номером и позициями, "
                "пока не подключён реальный провайдер инвойсинга.",
    how_to="Сейчас работает в тестовом режиме без ключей — PDF не генерируется. "
           "Реальный провайдер подключится сюда, когда появится.",
    cred_fields=[],
    actions={
        "create_invoice": Action(
            name="create_invoice",
            description="Создать счёт клиенту (тестовый режим, пока нет реального провайдера).",
            handler=_create_invoice,
            params={
                "client_name": {"type": "string", "description": "Имя/название клиента"},
                "items": {"type": "array", "description": "Позиции счёта: [{name, amount}]"},
                "currency": {"type": "string", "description": "Валюта, например RUB"},
            },
            required=["client_name", "items"],
            synonyms=["счёт", "счет", "инвойс", "invoice", "выставить счёт"],
        ),
        "get_invoice_status": Action(
            name="get_invoice_status",
            description="Проверить статус счёта по id.",
            handler=_get_invoice_status,
            params={"invoice_id": {"type": "string", "description": "id счёта"}},
            required=["invoice_id"],
        ),
    },
)
