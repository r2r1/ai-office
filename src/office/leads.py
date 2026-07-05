"""
Мини-CRM: лиды, собранные формами лендингов/ботов — по тенанту, с состоянием.

Специализация обобщённого движка `process_instances.py` (BOS §5): продажи —
Process, который никогда не завершается сам по себе, лид — Instance с текущей
стадией (`status`) и историей переходов. Внешний контракт этого модуля
(add/get/set_status/...) и файл (`leads.json`) НЕ меняются — существующие
потребители (server.py, ResultsView.tsx, metrics.py, gap.py, world.py, objectives.py)
читают count()/for_site()/count_last_days(), их поведение не меняется.
"""

from src.office import process_instances as pi

PROCESS = "sales"
STATUSES = ("new", "contacted", "qualified", "won", "lost")
STATUS_LABELS = {
    "new": "Новый", "contacted": "Связались", "qualified": "В работе",
    "won": "Сделка", "lost": "Отказ",
}
# Через сколько часов "новый" лид без движения считается недожатым — раскрывается
# в Event Layer (check_stale_events), не здесь: этот модуль только хранит данные.
STALE_AFTER_HOURS = 72

pi.register(PROCESS, file="leads.json", stages=STATUSES, labels=STATUS_LABELS, stage_field="status")


def add(slug: str, name: str, contact: str, message: str = "") -> dict:
    return pi.add(PROCESS, {
        "slug": slug, "name": (name or "").strip()[:120],
        "contact": (contact or "").strip()[:160], "message": (message or "").strip()[:1000],
    })


def all_leads() -> list[dict]:
    return pi.all_instances(PROCESS)


def for_site(slug: str) -> list[dict]:
    return [l for l in all_leads() if l.get("slug") == slug]


def get(lead_id: str) -> dict | None:
    return pi.get(PROCESS, lead_id)


def set_status(lead_id: str, status: str, note: str = "") -> dict | None:
    """Меняет статус лида, пишет запись в историю. None — если лид/статус не найден."""
    if status not in STATUSES:
        return None
    return pi.set_stage(PROCESS, lead_id, status, note=note)


def add_note(lead_id: str, text: str, by: str = "") -> dict | None:
    return pi.add_note(PROCESS, lead_id, text, by)


def stale_new(hours: float = STALE_AFTER_HOURS) -> list[dict]:
    """Лиды, всё ещё "new" дольше `hours` — кандидаты на follow-up/дожим."""
    return pi.stale_in_first_stage(PROCESS, hours)


def check_stale_events(hours: float = STALE_AFTER_HOURS) -> int:
    return pi.check_stale_events(
        PROCESS, hours, name_fields=("name", "contact"),
        message="{count} лид(ов) без ответа {hours}+ часов: {names}",
        detail="Открой «Лиды» → отметь статус или напиши клиенту напрямую.",
        event_kind="opportunity", from_role="crm")


def count() -> int:
    return pi.count(PROCESS)


def count_since(ts: float) -> int:
    """Число лидов, пришедших после метки времени ts (факт для Measurement)."""
    return pi.count_since(PROCESS, ts)


def count_last_days(days: int = 7) -> int:
    """Число лидов за последние `days` суток — фактическая метрика «заявки/неделю»."""
    return pi.count_last_days(PROCESS, days)


def load() -> None:
    pass


def reset() -> None:
    pi.reset(PROCESS)
