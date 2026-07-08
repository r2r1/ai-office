"""
Автоматический дожим лида — детерминированная серия сообщений вместо ручного
поиска протухших заявок раз в цикл (docs/product-capability-gaps.md п.4).

Раньше `leads.check_stale_events()` только поднимал ОДНО событие для продажника —
дальше всё зависело от того, вспомнит ли LLM-агент написать конкретному лиду в
конкретный день. Здесь — расписание из 3 шагов (72ч / 120ч / 192ч без ответа),
которое СРАБАТЫВАЕТ САМО каждый цикл офиса (детерминированный код первичнее LLM,
BOS §7 engineering-principles): рендерит шаблон, пробует реально отправить через
gmail (если контакт похож на email и Google подключён) или telegram_personal
(иначе), а если ни одна интеграция не подключена — пишет TEST-заметку в историю
лида, чтобы поведение было видно и проверяемо уже сейчас, без единого ключа.

Состояние дожима — не в самом лиде (чтобы не трогать формат `leads.json`,
BOS §11 «один сериализатор на сущность»), а в отдельном `lead_nurture.json`:
{lead_id: последний_отправленный_шаг}.
"""

import re
import time

from src.saas import context as ctx
from src.office import leads

_FILE = "lead_nurture.json"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# (часы_без_ответа, текст) — шаг N срабатывает, когда лид ждёт дольше threshold
# и предыдущие шаги (0..N-1) уже отправлены. Последний шаг — не спам "ещё
# напоминание", а мягкое закрытие ("если неактуально — просто не отвечайте").
STEPS: list[tuple[float, str]] = [
    (72, "Здравствуйте, {name}! Вы оставляли заявку{service_part} — уточняю, "
         "остаётся ли запрос в силе? Готовы ответить на вопросы."),
    (120, "{name}, добрый день! Ещё раз про вашу заявку{service_part} — если удобнее, "
          "можем созвониться в любое время, только напишите."),
    (192, "{name}, если запрос уже неактуален — просто игнорируйте это сообщение, "
          "мы больше не будем писать. Если актуален — напишите одно слово, продолжим."),
]


def _state() -> dict:
    return ctx.read_json(_FILE, {})


def _save(d: dict) -> None:
    ctx.write_json(_FILE, d)


def _service_part(message: str) -> str:
    if not message:
        return ""
    first = message.split(";")[0].strip()
    if first.lower().startswith("услуга:"):
        return f" ({first.split(':', 1)[1].strip()})"
    return ""


def _render(step_idx: int, lead: dict) -> str:
    name = (lead.get("name") or "").strip() or "здравствуйте"
    template = STEPS[step_idx][1]
    return template.format(name=name, service_part=_service_part(lead.get("message", "")))


async def _try_deliver(contact: str, text: str) -> tuple[bool, str]:
    """Пытается реально отправить через подключённую интеграцию. Возвращает
    (доставлено?, человекочитаемый результат для истории лида)."""
    from src.integrations import registry as integrations_registry

    contact = (contact or "").strip()
    if _EMAIL_RE.match(contact):
        gmail = integrations_registry.get("gmail")
        if gmail and integrations_registry.is_connected(gmail):
            creds = integrations_registry.credentials_for(gmail)
            result = await gmail.actions["send_email"].handler(
                creds, {"to": contact, "subject": "Ваша заявка", "body": text})
            ok = "ошиб" not in result.lower() and "не удал" not in result.lower()
            return ok, f"Email: {result[:150]}"

    tg = integrations_registry.get("telegram_personal")
    if tg and integrations_registry.is_connected(tg) and contact:
        creds = integrations_registry.credentials_for(tg)
        result = await tg.actions["send_dm"].handler(creds, {"target": contact, "text": text})
        ok = "отправлено" in result.lower()
        return ok, f"Telegram: {result[:150]}"

    return False, f"[TEST, интеграция не подключена] Отправили бы: «{text}»"


async def run_due_followups(max_per_cycle: int = 10) -> int:
    """Отправляет по одному следующему шагу дожима каждому подходящему лиду за
    вызов (не спамит все шаги разом). Возвращает число отправленных сообщений."""
    state = _state()
    sent_count = 0
    now = time.time()
    for lead in leads.all_leads():
        if sent_count >= max_per_cycle:
            break
        if lead.get("status") != "new":
            continue  # уже в работе/закрыт — автодожим не вмешивается
        hours_waiting = (now - lead.get("ts", now)) / 3600
        last_step = state.get(lead["id"], -1)
        next_step = last_step + 1
        if next_step >= len(STEPS):
            continue  # серия исчерпана
        threshold, _ = STEPS[next_step]
        if hours_waiting < threshold:
            continue
        text = _render(next_step, lead)
        delivered, result = await _try_deliver(lead.get("contact", ""), text)
        leads.add_note(lead["id"],
                       f"Автодожим шаг {next_step + 1}/{len(STEPS)}: {result}", by="auto_nurture")
        state[lead["id"]] = next_step
        sent_count += 1
    if sent_count:
        _save(state)
    return sent_count


def reset() -> None:
    ctx.delete_file(_FILE)
