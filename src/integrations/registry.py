"""
Каталог доступных интеграций + связка с хранилищем учётных данных.

Чтобы добавить сервис — импортируй его INTEGRATION и добавь в _ALL.
OAuth-интеграции (oauth_url != "") считаются подключёнными, если существует
соответствующее подключение в connections (name == integration.name или "google").
"""

from src.integrations.base import Integration
from src.integrations.telegram          import INTEGRATION as _telegram
from src.integrations.telegram_personal import INTEGRATION as _telegram_personal
from src.integrations.website           import INTEGRATION as _website
from src.integrations.github            import INTEGRATION as _github
from src.integrations.google_sheets     import INTEGRATION as _gsheets
from src.integrations.gmail             import INTEGRATION as _gmail
from src.integrations.google_calendar   import INTEGRATION as _gcal
from src.integrations.payments          import INTEGRATION as _payments
from src.integrations.deploy            import INTEGRATION as _deploy
from src.integrations.invoicing         import INTEGRATION as _invoicing
from src.integrations.ads               import INTEGRATION as _ads
from src.integrations.crm               import INTEGRATION as _crm
from src.integrations.crm_bitrix24      import INTEGRATION as _crm_bitrix24
from src.integrations.erp_1c            import INTEGRATION as _erp_1c
from src.integrations.figma             import INTEGRATION as _figma
from src.integrations.bitrix24          import INTEGRATION as _bitrix24
from src.office import connections

_ALL: dict[str, Integration] = {
    _website.name:          _website,
    _telegram.name:         _telegram,
    _telegram_personal.name: _telegram_personal,
    _github.name:           _github,
    _gsheets.name:          _gsheets,
    _gmail.name:            _gmail,
    _gcal.name:             _gcal,
    _payments.name:         _payments,
    _deploy.name:           _deploy,
    _invoicing.name:        _invoicing,
    _ads.name:              _ads,
    _crm.name:              _crm,
    _crm_bitrix24.name:     _crm_bitrix24,
    _erp_1c.name:           _erp_1c,
    _figma.name:            _figma,
    _bitrix24.name:         _bitrix24,
}

# Все Google-интеграции держат токен под одним именем "google"
_GOOGLE_SERVICES = {"google_sheets", "gmail", "google_calendar"}


def all_integrations() -> list[Integration]:
    return list(_ALL.values())


def get(name: str) -> Integration | None:
    if not name:
        return None
    key = name.lower().strip()
    if key in _ALL:
        return _ALL[key]
    for integ in _ALL.values():
        if integ.title.lower() == key or key in integ.name:
            return integ
    return None


def credentials_for(integ: Integration, profile_id: str = "") -> dict:
    """Возвращает поля учётных данных из сохранённого подключения (или {}).
    `profile_id` — конкретный профиль, когда у провайдера их несколько
    (см. profiles_for); без него — первый профиль (обратная совместимость с
    однопрофильными тенантами). Точный матч по имени (get_exact_by_name), НЕ
    нечёткий — иначе "crm" рискует зацепить связку "crm_bitrix24"."""
    if profile_id:
        conn = connections.get_profile(profile_id)
        return conn.get("fields", {}) if conn else {}
    # Google-интеграции используют общее подключение "google"
    if integ.name in _GOOGLE_SERVICES:
        conn = connections.get_exact_by_name("google")
        return conn.get("fields", {}) if conn else {}
    conn = connections.get_exact_by_name(integ.name)
    return conn.get("fields", {}) if conn else {}


def profiles_for(integ: Integration) -> list[dict]:
    """Все профили подключения провайдера (замаскированные, для UI) — когда
    тенант держит несколько одновременных подключений одной способности."""
    return connections.list_profiles(integ.name)


def is_connected(integ: Integration) -> bool:
    """
    Подключено ли? Логика:
    - Интеграции без cred_fields и без oauth_url: всегда True (сайт и т.п.)
    - OAuth-интеграции: True если существует нужное подключение в connections
    - Остальные: True если есть сохранённая учётка с непустым секретом
    """
    # OAuth-интеграции
    if integ.oauth_url:
        if integ.name in _GOOGLE_SERVICES:
            return connections.get_exact_by_name("google") is not None
        return connections.get_exact_by_name(integ.name) is not None

    # Интеграции без кредов (website и т.п.)
    if not integ.cred_fields:
        return True

    # Обычные ключ/токен
    creds = credentials_for(integ)
    if not creds:
        return False
    primary    = integ.cred_fields[0].key if integ.cred_fields else None
    candidates = [primary, "token", "key", "value"]
    return any((creds.get(k) or "").strip() for k in candidates if k)


def catalog_payload() -> list[dict]:
    """Каталог для фронта: описание + статус подключения."""
    out = []
    for integ in _ALL.values():
        item = integ.to_public()
        item["connected"] = is_connected(integ)
        out.append(item)
    return out


# Ключевые слова → интеграция. Отдельный словарь от tool_router._INTENT_HINTS
# (тот — для подбора СПОСОБНОСТИ внутри задачи агента; этот — для подсказки
# владельцу "подключите X" в момент пиковой мотивации сразу после онбординга,
# см. server.py /api/onboarding/suggested-integrations). website не предлагаем —
# он всегда "подключён" (см. is_connected), предлагать нечего.
_SUGGEST_KEYWORDS: dict[str, tuple[str, ...]] = {
    "telegram":        ("бот", "telegram", "телеграм", "заявк", "запис"),
    "google_sheets":   ("таблиц", "excel", "гугл документ", "sheets", "учёт", "crm"),
    "google_calendar": ("календар", "запись на приём", "встреч", "расписан", "бронир"),
    "gmail":           ("почт", "email", "e-mail", "рассылк", "gmail"),
    "github":          ("код", "github", "репозитор", "разработ"),
    "payments":        ("оплат", "платеж", "платёж", "счёт", "счет", "payment"),
    "deploy":          ("деплой", "хостинг", "vercel", "netlify", "поднять сайт"),
    "invoicing":       ("счёт", "счет", "инвойс", "invoice"),
    "ads":             ("реклама", "таргет", "google ads", "meta ads", "продвижение"),
    "crm":             ("crm", "pipedrive", "hubspot", "amocrm", "внешняя crm"),
    "crm_bitrix24":    ("bitrix", "битрикс", "bitrix24"),
    "erp_1c":          ("1с", "1c", "erp", "эрп", "контрагент"),
    "figma":           ("figma", "фигма", "макет", "дизайн-файл"),
    # "bitrix24" (OAuth-вариант) намеренно НЕ в этом словаре — иначе бриф про
    # Bitrix24 показывал бы владельцу два конкурирующих провайдера одной
    # потребности сразу (вебхук crm_bitrix24 уже покрывает подсказку);
    # OAuth-вариант всё равно виден в полном каталоге «Ресурсы → Доступы».
}


def suggested_for(text: str) -> list[dict]:
    """Интеграции, релевантные тексту брифа (BOS §5: предложить подключение в
    момент пиковой мотивации — сразу после того, как клиент увидел анализ и
    инициативы, а не спрятанным в «Компания → Доступы», где его никто не
    находит). Уже подключённые тоже попадают в список (foreground: "готово"),
    просто без CTA — иначе после первой же подключённой интеграции список
    менялся бы под ногами непредсказуемо."""
    low = (text or "").lower()
    scored: list[tuple[int, Integration]] = []
    for integ in _ALL.values():
        kws = _SUGGEST_KEYWORDS.get(integ.name)
        if not kws:
            continue
        hits = sum(1 for kw in kws if kw in low)
        if hits:
            scored.append((hits, integ))
    scored.sort(key=lambda x: -x[0])
    out = []
    for _, integ in scored[:3]:
        item = integ.to_public()
        item["connected"] = is_connected(integ)
        out.append(item)
    return out
