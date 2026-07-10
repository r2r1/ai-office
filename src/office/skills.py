"""
Skills — встроенная бизнес-логика (второй способ Execution Engine из docs/3.md).

Задача может быть выполнена тремя способами:
  1. Встроенный AI (LLM) — основной путь (см. core/llm.py).
  2. Skill — готовая бизнес-логика: знает КАК сделать (структура, приёмы, проверки).
     Роль больше НЕ держит «как» у себя в промпте — «как» живёт здесь, в скилле.
  3. External Worker — внешний сервис (Cursor/Lovable/n8n) — точка расширения.

Как воркер выбирает скилл (тот же приём, что в tool_router для интеграций):
  воркер описывает ПОТРЕБНОСТЬ словами  →  use_skill("сделать 3D-лендинг с анимациями")
    →  skills.match() ранжирует скиллы по словам потребности
    →  возвращается ПЛЕЙБУК скилла (экспертные инструкции + план файлов + чеклист)
    →  воркер выполняет его СВОИМИ инструментами (write_file/verify_code/…).

Так роль перестаёт быть зашитой инструкцией: захотели менять способ делать
3D-сайты — правим скилл, а не каждую роль; новый способ — новый скилл, роли не трогаем.
"""

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional


@dataclass
class Skill:
    """Декларативное описание навыка (по образцу integrations/base.Integration)."""
    id: str
    title: str
    description: str
    # Слова-триггеры в тексте потребности (грубый матч намерения).
    keywords: list[str] = field(default_factory=list)
    # Экспертный плейбук «как делать»: структура файлов, приёмы, проверки.
    # Именно его получает воркер при use_skill и выполняет своими инструментами.
    playbook: str = ""
    # Каким ролям осмысленно (пусто = всем). Фильтрует выдачу под конкретного воркера.
    roles: list[str] = field(default_factory=list)
    # builtin — делается встроенной моделью по плейбуку; external — делегируется наружу.
    kind: str = "builtin"
    # Опциональный детерминированный исполнитель (если скилл сам что-то делает).
    handler: Optional[Callable[[dict], Awaitable[str]]] = None
    # Откуда скилл: "builtin" (в коде) или "installed" (файл, поставлен клиентом).
    source: str = "builtin"

    def score(self, task: str) -> int:
        """Насколько Skill подходит задаче — единый скорер потребностей (needs.py,
        BOS §5): совпадения ключевых слов с обработкой отрицания («без 3D»)."""
        from src.office import needs
        return needs.score_keywords(task, self.keywords)

    def to_public(self) -> dict:
        return {"id": self.id, "title": self.title, "description": self.description,
                "keywords": self.keywords, "roles": self.roles, "kind": self.kind,
                "source": self.source}


# ── Реестр ───────────────────────────────────────────────────────────────────
# _BUILTIN — скиллы из кода (общие для всех тенантов, регистрируются при импорте).
# Установленные клиентом скиллы (файлы) вливаются в выдачу через _all_registered()
# и потому автоматически видны use_skill/find_skills без правок agent_factory.
_BUILTIN: dict[str, Skill] = {}


def register(skill: Skill) -> None:
    _BUILTIN[skill.id] = skill


def _all_registered() -> dict[str, Skill]:
    """Встроенные + установленные текущим тенантом (installed переопределяет по id)."""
    from src.office import skill_store
    merged: dict[str, Skill] = dict(_BUILTIN)
    for d in skill_store.load_installed():
        merged[d["id"]] = Skill(
            id=d["id"], title=d["title"], description=d["description"],
            keywords=d.get("keywords") or [], playbook=d.get("playbook", ""),
            roles=d.get("roles") or [], kind=d.get("kind", "builtin"),
            source="installed",
        )
    return merged


def get(skill_id: str) -> Optional[Skill]:
    return _all_registered().get(skill_id)


def all_skills(role: str = "") -> list[Skill]:
    """Скиллы, доступные роли (или все). Скилл без привязки доступен любой роли."""
    items = list(_all_registered().values())
    if not role:
        return items
    return [s for s in items if not s.roles or role in s.roles]


def match(task: str, role: str = "") -> Optional[Skill]:
    """Лучший Skill под потребность или None (тогда задачу делает LLM напрямую)."""
    pool = all_skills(role)
    ranked = sorted(pool, key=lambda s: s.score(task), reverse=True)
    if ranked and ranked[0].score(task) > 0:
        return ranked[0]
    return None


def suggestions(task: str, role: str = "", top: int = 3) -> list[Skill]:
    """Топ-N подходящих скиллов (для развилки, когда лидера нет)."""
    pool = [(s, s.score(task)) for s in all_skills(role)]
    pool = [p for p in pool if p[1] > 0]
    pool.sort(key=lambda kv: kv[1], reverse=True)
    return [s for s, _ in pool[:top]]


def catalog_for(role: str) -> str:
    """Короткий список доступных роли скиллов — для подсказки в промпте."""
    items = all_skills(role)
    return "; ".join(f"«{s.title}»" for s in items) if items else ""


def search(query: str, role: str = "", top: int = 6) -> list[Skill]:
    """
    Поиск по каталогу скиллов (внутренний аналог find-skills) — для ДИСКАВЕРИ,
    когда воркер/лидер хочет ПОСМОТРЕТЬ, какие способы вообще есть под запрос,
    а не сразу взять один плейбук (это делает match/use_skill).

    Пустой запрос → весь каталог роли (просто «покажи что умеешь»). Иначе —
    ранжирование по совпадению ключевых слов; если совпадений нет, возвращаем
    топ каталога роли (лучше показать что есть, чем пусто).
    """
    pool = all_skills(role)
    q = (query or "").strip().lower()
    if not q:
        return pool[:top]
    scored = sorted(pool, key=lambda s: s.score(q), reverse=True)
    if scored and scored[0].score(q) > 0:
        return [s for s in scored if s.score(q) > 0][:top]
    return pool[:top]


_PROMPT_BLOCK_LIMIT = 6


def prompt_block(role: str, task: str = "", limit: int = _PROMPT_BLOCK_LIMIT) -> str:
    """
    Динамический блок скиллов для системного промпта роли (собирается Prompt Builder'ом).

    Роль НЕ называет скиллы в своём тексте — их подмешивает этот блок из реестра,
    отфильтрованный под роль. Фильтр по роли одной задачи не решает: он режет
    каталог по ГОРИЗОНТАЛИ (какие скиллы вообще относятся к профессии), но не по
    ВЕРТИКАЛИ (какие из НИХ относятся к ЭТОЙ конкретной задаче) — раньше блок
    безусловно перечислял title+description ВСЕХ скиллов роли на КАЖДУЮ её задачу,
    независимо от того, какая из них реально нужна. У developer'а их уже 10, а
    устанавливаемые клиентом скиллы (skill_store.py) растут без верхней границы —
    тот же паттерн, что ленивая загрузка каталога инструментов (ToolSearch): не
    предзагружать всё, что теоретически может понадобиться, а показать то, что
    релевантно СЕЙЧАС, и дать способ дотянуться до остального (find_skills).

    `task` — текст задачи, по которому ранжируем (Skill.score, тот же скорер, что
    match/suggestions). Каталог роли ≤ limit — ведём себя как раньше, показываем
    всё (усечение не нужно). Пустой task при большом каталоге — берём первые
    `limit` в порядке реестра (детерминированно, без ложной точности сортировки
    по нулевому score).
    """
    items = all_skills(role)
    if not items:
        return ""
    total = len(items)
    if total > limit:
        if task:
            ranked = sorted(items, key=lambda s: s.score(task), reverse=True)
        else:
            ranked = items
        shown, hidden = ranked[:limit], total - limit
    else:
        shown, hidden = items, 0
    lines = "\n".join(f"• {s.title} — {s.description}" for s in shown)
    tail = (f"\n(ещё {hidden} — не показаны, не подошли под эту задачу по ключевым "
            f"словам; если ни один из перечисленных не годится, вызови find_skills "
            f"с потребностью словами — поищет по ВСЕМУ каталогу.)" if hidden else "")
    return ("\n\nДОСТУПНЫЕ СКИЛЛЫ (готовые способы «как делать»). Когда сомневаешься, "
            "как именно выполнить — НЕ выдумывай: вызови use_skill с потребностью словами, "
            "получи экспертный плейбук и выполни его своими инструментами. Не уверен, "
            "что есть под задачу — сначала find_skills (поиск по каталогу).\n" + lines + tail)


def catalog_payload() -> list[dict]:
    return [s.to_public() for s in _all_registered().values()]


# ── Установка/удаление скиллов-файлов (аналог npx skills add/remove) ─────────
# Тонкие обёртки над skill_store — единая точка входа для API. Установка — только
# явное действие пользователя (см. server.py), НЕ инструмент агента.
def install(source: str, content: str = "", url: str = "", ref: str = "") -> dict:
    from src.office import skill_store
    if source == "markdown":
        return skill_store.install_markdown(content)
    if source == "url":
        return skill_store.install_url(url)
    if source == "github":
        return skill_store.install_github(ref)
    return {"ok": False, "message": "source должен быть markdown | url | github"}


def remove(skill_id: str) -> dict:
    from src.office import skill_store
    if skill_id in _BUILTIN:
        return {"ok": False, "message": "Встроенный скилл нельзя удалить — можно переопределить, установив свой с тем же id."}
    ok = skill_store.remove(skill_id)
    return {"ok": ok, "message": "" if ok else "Скилл не найден среди установленных."}


# ── Загрузка встроенных скиллов из файлов ─────────────────────────────────────
# Раньше каждый скилл был Python-литералом Skill(...) прямо в этом файле (и в
# skill_library.py) — редактировать один скилл значило открывать файл на сотни
# строк с десятком чужих playbook'ов вперемешку. Ни один встроенный скилл не
# использовал Python-логику в handler (framer_motion_3d_site просто возвращал
# свой текст) — значит формат УСТАНОВЛЕННЫХ скиллов (skill_store.parse_skill_md,
# тот же ---frontmatter--- + markdown-тело, что у реального SKILL.md экосистемы)
# подходит и для встроенных. Один скилл = один файл в builtin_skills/*.md —
# редактируется отдельно, виден в git как обычный текст, без риска задеть чужой
# playbook в том же .py.
def _load_builtin_dir() -> None:
    from pathlib import Path
    from src.office import skill_store

    d = Path(__file__).parent / "builtin_skills"
    for parsed in skill_store._read_dir(d):
        register(Skill(
            id=parsed["id"], title=parsed["title"], description=parsed["description"],
            keywords=parsed.get("keywords") or [], playbook=parsed.get("playbook", ""),
            roles=parsed.get("roles") or [], kind=parsed.get("kind", "builtin"),
            source="builtin",
        ))


_load_builtin_dir()
