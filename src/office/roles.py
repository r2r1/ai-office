"""
Role Definitions — роли как ДАННЫЕ, а не зашитые в код промпты (см. docs/arhitecture.md).

Идея: у агента нет собственного постоянного промпта. Есть описание роли
(миссия, зона ответственности, инструменты, полномочия, ограничения, метрики)
и операционный «playbook». Итоговый системный промпт собирает prompt_builder
динамически под конкретную задачу.

Базовые тексты ролей берутся из встроенного каталога (seed). Клиент может
переопределить любую роль — оверрайды хранятся per-tenant в roles.json и имеют
приоритет над seed. Так роль становится редактируемыми данными, а не кодом.
"""

from pathlib import Path

from src.saas import context as ctx

_FILE = "roles.json"

# Структурированные описания ролей (для UI и будущего редактора).
# Операционный текст («как именно работать») — файлы builtin_roles/<role>.md
# (см. _load_seed_files ниже), по одному на роль, как builtin_skills.
ROLE_META: dict[str, dict] = {
    "cto": {
        "department": "tech", "title": "CTO", "capability": "reasoning",
        "mission": "Вести технический отдел к продукту, который решает задачу клиента.",
        "responsibilities": ["продукт", "код", "боты", "сайты", "технические интеграции"],
        "tools": ["delegate_task", "hire", "ask_colleague"],
        "constraints": ["не делать работу руками — управлять подчинёнными"],
        "success_metrics": ["работающий продукт", "закрытые задачи отдела"],
    },
    "cmo": {
        "department": "marketing", "title": "CMO", "capability": "reasoning",
        "mission": "Растить узнаваемость и привлечение аудитории.",
        "responsibilities": ["контент", "соцсети", "реклама", "бренд"],
        "tools": ["delegate_task", "hire", "ask_colleague"],
        "constraints": ["не делать работу руками — управлять подчинёнными"],
        "success_metrics": ["охват", "лиды"],
    },
    "sales_lead": {
        "department": "sales", "title": "Head of Sales", "capability": "reasoning",
        "mission": "Превращать интерес в платящих клиентов.",
        "responsibilities": ["поиск клиентов", "переговоры", "конверсия лидов", "CRM"],
        "tools": ["delegate_task", "hire", "ask_colleague"],
        "constraints": ["не делать работу руками — управлять подчинёнными"],
        "success_metrics": ["сделки", "конверсия"],
    },
    "designer": {
        # Возвращена как отдельная роль (2026-07-14) — НЕ повтор старой ошибки.
        # Раньше designer/developer были двумя ролями на ОДИН артефакт (site/) —
        # второй переписывал то, что собрал первый. Теперь designer владеет ДРУГИМ
        # артефактом (docs/brand_book.md, plan._derive_artifacts → "doc") и
        # передаёт направление ДАЛЬШЕ — в site/ пишет только developer. Ключевой
        # инвариант: designer никогда не вызывает write_file по пути site/*.
        "department": "tech", "title": "Дизайнер", "capability": "reasoning",
        "mission": "Готовить визуальное направление ДО кода: референсы, тон, палитра,"
                    " бренд-бук — и получать явное «да» владельца, прежде чем разработчик"
                    " начнёт строить.",
        "responsibilities": ["референсы и конкурентный визуальный анализ", "бренд-бук",
                              "выбор палитры/типографики/приёма из каталога направлений",
                              "карта сайта для многостраничных проектов (не для лендинга)",
                              "утверждение направления/карты с владельцем"],
        "tools": ["web_search", "write_file", "ask_user", "read_file", "list_files"],
        "constraints": ["никогда не пишет в site/ — только docs/brand_book.md, docs/site_content.md, docs/sitemap.md",
                         "не публикует и не финализирует сайт — это делает developer после явного «да» владельца"],
        "success_metrics": ["бренд-бук одобрен владельцем с первого раза",
                             "developer не переспрашивает про стиль"],
    },
    "developer": {
        # Раньше "designer" и "developer" были двумя отдельными ролями на ОДИН
        # артефакт site/ (одинаковая декларация артефакта в plan._derive_artifacts,
        # почти дословно совпадающие границы в builtin_roles/*.md) — на практике
        # второй систематически переписывал то, что уже собрал первый (прод-кейс:
        # два полных прохода framer_motion_3d_site на один и тот же лендинг за один
        # прогон). Слиты в одну роль: developer владеет сайтом end-to-end (структура,
        # премиальный визуал, логика) — один production-шаг, не два.
        #
        # 2026-07-14: designer вернулась, но НЕ повторяет старую ошибку — она
        # владеет ДРУГИМ артефактом (docs/brand_book.md), не site/. developer
        # по-прежнему единственный, кто пишет в site/ — граница артефактов, а
        # не дублирование одного и того же.
        "department": "tech", "title": "Разработчик", "capability": "coding",
        "mission": "Писать и запускать реальный рабочий код: от премиального визуала сайта до логики и ботов.",
        "responsibilities": ["UI/UX и вёрстка сайтов", "боты", "скрипты/API", "анимации"],
        # web_search — для референсов приёмов (см. builtin_skills/three_js_3d_site.md),
        # не для замены готовым сайтом целиком: искать ПРИЁМ, не копировать чужой сайт.
        "tools": ["write_file", "verify_code", "execute_code", "list_files", "read_file", "web_search"],
        "constraints": ["не использовать платные конструкторы (Tilda/Webflow)", "артефакты только через write_file"],
        "success_metrics": ["код компилируется и работает", "красивый рабочий сайт"],
    },
    "integrator": {
        "department": "tech", "title": "Интегратор", "capability": "coding",
        "mission": "Подключать офис к внешним сервисам и запускать ботов.",
        "responsibilities": ["интеграции", "запуск ботов", "проверка подключений"],
        "tools": ["list_integrations", "use_integration", "configure_bot", "ask_user"],
        "constraints": ["не публиковать сайты", "не делать ручную работу в сервисе"],
        "success_metrics": ["работающие подключения и боты"],
    },
    "marketer": {
        "department": "marketing", "title": "Маркетолог", "capability": "text",
        "mission": "Создавать оффер, контент и тексты для сайта и бота.",
        "responsibilities": ["оффер/УТП", "контент сайта", "тексты бота"],
        "tools": ["write_file", "request_research"],
        "constraints": ["сохранять результаты в workspace через write_file"],
        "success_metrics": ["готовые тексты, которыми пользуются коллеги"],
    },
    "analyst": {
        "department": "marketing", "title": "Аналитик", "capability": "search",
        "mission": "Собирать данные и давать выводы с цифрами.",
        "responsibilities": ["анализ рынка/конкурентов/клиентов"],
        "tools": ["web_search", "write_file"],
        "constraints": ["сохранять анализ в workspace через write_file"],
        "success_metrics": ["выводы с цифрами и рекомендациями"],
    },
    "salesman": {
        "department": "sales", "title": "Продажник", "capability": "text",
        "mission": "Находить клиентов и писать цепляющие холодные сообщения.",
        "responsibilities": ["поиск лидов", "оффер", "холодные сообщения"],
        "tools": ["web_search"],
        "constraints": [],
        "success_metrics": ["ответы и встречи"],
    },
    "cfo": {
        "department": "finance", "title": "CFO", "capability": "reasoning",
        "mission": "Вести финансовый учёт офиса и юнит-экономику бизнеса клиента.",
        "responsibilities": ["учёт", "ERP/1С", "юнит-экономика", "финансовая отчётность"],
        "tools": ["delegate_task", "hire", "ask_colleague"],
        "constraints": ["не делать работу руками — управлять подчинёнными"],
        "success_metrics": ["точный учёт", "закрытые задачи отдела"],
    },
    "accountant": {
        "department": "finance", "title": "Бухгалтер", "capability": "text",
        "mission": "Вести учёт в ERP/1С и готовить финансовые документы.",
        "responsibilities": ["контрагенты и документы в учётной системе", "сверка данных", "отчёты"],
        "tools": ["use_capability", "use_integration", "write_file"],
        "constraints": ["не менять финансовые данные без явного запроса владельца"],
        "success_metrics": ["корректно созданные документы/контрагенты в учётной системе"],
    },
}


# Штаб-роли CEO — не отдел, но реальные, часто адресуемые роли (см. CLAUDE.md §3.2).
SERVICE_ROLES = ["researcher", "strategist", "architect", "hr"]

# capability для штаб-ролей — не входят в ROLE_META (нет отдела), но должны
# роутиться на подходящую модель через quality_modes.role_capability.
_SERVICE_CAPABILITY: dict[str, str] = {
    "researcher": "search", "strategist": "reasoning",
    "architect": "reasoning", "hr": "text",
    "orchestrator": "reasoning",
}


def known_roles() -> set[str]:
    """Все существующие в офисе роли: отдельческие (ROLE_META) + штаб CEO.
    Источник правды для валидации delegate_task/send_message — чтобы агент не
    мог поставить задачу или написать сообщение несуществующей роли/коллеге."""
    return set(ROLE_META.keys()) | set(SERVICE_ROLES)


def department_of(role: str) -> str:
    """К какому отделу относится роль ('' для штаба CEO/неизвестной роли).
    Единственный источник правды роль→отдел (было продублировано в org.py и
    plan.py — теперь оба читают отсюда)."""
    return ROLE_META.get(role, {}).get("department", "")


def roles_in_department(dept_id: str) -> list[str]:
    """Роли, относящиеся к отделу — вычисляется из ROLE_META, а не хранится
    отдельным ручным списком (было org.DEPARTMENTS[dept]['members'])."""
    return [r for r, m in ROLE_META.items() if m.get("department") == dept_id]


def capability_of(role: str) -> str:
    """Тип задачи роли для capability-роутинга моделей (было отдельным
    hardcoded-словарём в quality_modes.py — теперь одно поле здесь)."""
    if role in ROLE_META:
        return ROLE_META[role].get("capability", "reasoning")
    return _SERVICE_CAPABILITY.get(role, "reasoning")


def _overrides() -> dict:
    return ctx.read_json(_FILE, None) or {}


# Встроенные тексты ролей — файлы builtin_roles/<role>.md (по образцу builtin_skills):
# frontmatter (id, leader) + markdown-тело-плейбук. Редактируешь роль — открываешь
# один текстовый файл, а не Python-литерал. Лидерам (leader: true) загрузчик
# дописывает общую политику руководителя (policies/leader.md) — без дублирования.
_ROLES_DIR = Path(__file__).parent / "builtin_roles"
_seed_cache: dict[str, dict] = {}


def _load_seed_files() -> dict[str, dict]:
    import re
    if _seed_cache:
        return _seed_cache
    for f in sorted(_ROLES_DIR.glob("*.md")) if _ROLES_DIR.exists() else []:
        try:
            text = f.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
        if not m:
            continue
        front = {}
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                front[k.strip().lower()] = v.strip()
        rid = front.get("id") or f.stem
        _seed_cache[rid] = {"body": m.group(2).strip(),
                            "leader": front.get("leader", "").lower() == "true"}
    return _seed_cache


def _seed_text(role: str) -> str:
    """Базовый операционный текст роли из builtin_roles/<role>.md."""
    seed = _load_seed_files().get(role)
    if not seed:
        return ""
    body = seed["body"]
    if seed["leader"]:
        from src.office import prompt_builder
        lead = prompt_builder.policy("leader")
        if lead:
            body = body + "\n" + lead
    return body


def base_text(role: str) -> str:
    """Текст-основа роли: оверрайд клиента или seed. '' если роль неизвестна."""
    ov = _overrides().get(role) or {}
    if ov.get("playbook"):
        return ov["playbook"]
    seed = _seed_text(role)
    if seed:
        return seed
    return f"Ты — {role} агент AI-агентства. Выполни задачу профессионально."


def render(role: str) -> str:
    """Системная основа промпта роли (= base_text: оверрайд клиента или seed из
    builtin_roles/*.md); структурированная мета используется в UI и доступна для
    будущей динамической сборки заголовка роли."""
    return base_text(role)


def get(role: str) -> dict:
    meta = dict(ROLE_META.get(role, {}))
    ov = _overrides().get(role) or {}
    meta.update({k: v for k, v in ov.items() if k != "playbook"})
    meta["role"] = role
    meta["playbook"] = base_text(role)
    return meta


def all_roles() -> list[dict]:
    return [get(r) for r in ROLE_META]


def set_role(role: str, patch: dict) -> None:
    """Переопределить поля роли (включая playbook) — данные клиента."""
    ov = _overrides()
    cur = ov.get(role) or {}
    cur.update(patch or {})
    ov[role] = cur
    ctx.write_json(_FILE, ov)


def payload() -> dict:
    return {"roles": [
        {k: v for k, v in get(r).items() if k != "playbook"} | {"has_playbook": bool(base_text(r))}
        for r in ROLE_META
    ]}
