"""
Capability — реестр «что компания умеет производить» (BOS §1/§5).

НЕ путать с quality_modes (режимы качества выбора модели). Capability отвечает на
вопрос «умеем ли мы произвести артефакт такого типа / закрыть такую потребность»:
пересечение того, что офис РЕАЛЬНО умеет (встроенные навыки + подключённые
интеграции), с тем, что ТРЕБУЕТ план (task.required_capabilities — декларация, как
task.artifacts). Нехватка способности — не строка в ленте, а решение «приобрести»
с вариантами (подключить провайдера / установить скилл / спросить у владельца).

Статусы способности:
  have      — умеем сейчас (платформенная / скилл / подключённая интеграция)
  missing   — требуется планом, но не подключена (нужно приобрести)
  available — можем подключить, планом пока не требуется

Хранилища собственного нет: реестр вычисляется поверх plan + integrations.registry.
"""

from src.office import needs

# Каталог способностей: id → чем закрывается.
#   backed_by: "platform" (встроено, всегда есть) | имя интеграции (нужно подключение)
_CATALOG: dict[str, dict] = {
    "landing_site": {"label": "Публикация лендинга", "backed_by": "platform",
                     "hint": "встроенная интеграция website — доступна всегда"},
    "telegram_bot": {"label": "Telegram-бот", "backed_by": "telegram",
                     "hint": "токен Telegram-бота (@BotFather)"},
    "email":        {"label": "Email-рассылка", "backed_by": "gmail",
                     "hint": "подключение Gmail (OAuth в «Доступы»)"},
    "spreadsheet":  {"label": "Google Sheets", "backed_by": "google_sheets",
                     "hint": "подключение Google Sheets (OAuth в «Доступы»)"},
    "repo":         {"label": "GitHub-репозиторий", "backed_by": "github",
                     "hint": "GitHub (OAuth или PAT в «Доступы»)"},
    "calendar":     {"label": "Google Calendar", "backed_by": "google_calendar",
                     "hint": "подключение Google Calendar (OAuth)"},
}

# Слова задачи → capability_id. ЕДИНАЯ точка вывода required_capabilities (как
# _derive_artifacts в plan.py): вывод делается ОДИН раз при генерации плана и
# хранится в задаче; потребители читают декларацию, а не парсят заголовок заново.
# «бот»/«bot» НЕ входят сюда голой подстрокой — needs.is_bot_reference (ниже)
# матчит их отдельно с защитой от «работать/доработать» (см. needs.py).
_NEED_WORDS: dict[str, tuple[str, ...]] = {
    "email":        ("письм", "email", "рассылк", "gmail"),
    "spreadsheet":  ("таблиц", "sheets"),
    "repo":         ("репозитор", "github", "git push"),
    "calendar":     ("календар", "calendar"),
}


def derive_required(task: dict) -> list[str]:
    """capability_id, требуемые задачей (по заголовку). landing_site НЕ выводим из
    слов «сайт» — он платформенный (всегда have) и не создаёт capability-gap;
    важны внешние доступы, которых может не быть."""
    title = (task.get("title") or "").lower()
    out = []
    if needs.is_bot_reference(title):
        out.append("telegram_bot")
    for cap, words in _NEED_WORDS.items():
        if any(w in title for w in words):
            out.append(cap)
    return out


def required_of(task: dict) -> list[str]:
    """Требуемые способности задачи: явная декларация или вывод (совместимость)."""
    req = task.get("required_capabilities")
    if req:
        return list(req)
    return derive_required(task)


def _backing_status(cap_id: str) -> str:
    """have | available для способности вне зависимости от плана (умеем ли в
    принципе прямо сейчас)."""
    spec = _CATALOG.get(cap_id)
    if not spec:
        return "available"
    backed = spec["backed_by"]
    if backed == "platform":
        return "have"
    from src.integrations import registry as ir
    integ = ir.get(backed)
    return "have" if (integ and ir.is_connected(integ)) else "available"


def _acquire(cap_id: str) -> dict:
    """Как приобрести недостающую способность (варианты §5)."""
    spec = _CATALOG.get(cap_id, {})
    backed = spec.get("backed_by", "")
    if backed and backed != "platform":
        return {"method": "connect_integration", "integration": backed,
                "hint": spec.get("hint", "")}
    return {"method": "ask_user", "hint": spec.get("hint", "")}


def registry() -> dict:
    """Реестр способностей компании: что умеем / чего не хватает под план / что
    можем подключить. Источник — план (декларации) ∩ каталог интеграций."""
    from src.office import plan
    required: dict[str, list[str]] = {}
    for t in plan.all_tasks():
        if t.get("status") in ("done", "skipped"):
            continue
        for cap in required_of(t):
            required.setdefault(cap, []).append(t["id"])

    items = []
    for cap_id, spec in _CATALOG.items():
        base = _backing_status(cap_id)
        req_by = required.get(cap_id, [])
        if base == "have":
            status = "have"
        elif req_by:
            status = "missing"      # требуется планом, но не подключена
        else:
            status = "available"    # можем подключить, планом пока не требуется
        item = {"id": cap_id, "label": spec["label"], "status": status,
                "backed_by": spec["backed_by"], "required_by": req_by}
        if status == "missing":
            item["acquire"] = _acquire(cap_id)
        items.append(item)
    return {"capabilities": items,
            "have": [i["id"] for i in items if i["status"] == "have"],
            "missing": [i["id"] for i in items if i["status"] == "missing"]}


def missing() -> list[dict]:
    """Способности, которые план требует, но офис не умеет — как РЕШЕНИЕ приобрести
    (§5), а не уведомление. [{capability, label, required_by:[task_ids], acquire}].
    Читается execution_policy.missing_for_plan и capability-гейтом bootstrap."""
    return [
        {"capability": i["id"], "label": i["label"],
         "required_by": i["required_by"], "acquire": i["acquire"]}
        for i in registry()["capabilities"] if i["status"] == "missing"
    ]
