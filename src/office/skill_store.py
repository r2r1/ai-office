"""
Хранилище устанавливаемых скиллов — скиллы КАК ФАЙЛЫ (как SKILL.md у Claude Code).

Встроенные скиллы — тоже файлы (src/office/builtin_skills/*.md, тот же формат,
парсер переиспользует skills._load_builtin_dir). Здесь — механизм для
УСТАНАВЛИВАЕМЫХ скиллов: офис «ставит любой скилл из любого источника» БЕЗ правки
кода — скилл кладётся файлом в папку, а офис подхватывает его на лету.

Формат файла (совместим с реальным SKILL.md экосистемы):
    ---
    title: Название            # или name: (алиас Claude Code)
    description: Что делает
    keywords: слово1, слово2    # опц.; нет → берём слова из title
    roles: developer, designer  # опц.; пусто → доступен всем ролям
    kind: builtin               # опц.; по умолчанию builtin
    ---
    <тело-плейбук в markdown>

Хранение:
    data/tenants/<tid>/skills/*.md   — установленные клиентом (per-tenant, изоляция)
    data/skills/*.md                 — опц. глобальные (оператор, для всех тенантов)

БЕЗОПАСНОСТЬ: установленный скилл — это ИНСТРУКЦИЯ, которой следует агент. Ставит
его только пользователь/оператор явным действием (UI/API), НЕ агент. Сам скилл —
лишь текст-плейбук; агент действует существующими песочница-инструментами.
"""

import hashlib
import re
from pathlib import Path

from src.saas import context as ctx

# Кеш распарсенных установленных скиллов по тенанту — _load зовётся часто
# (all_skills → prompt_block на каждую задачу). Инвалидируется при install/remove.
_cache: dict[str, list[dict]] = {}

GLOBAL_DIR = Path("data") / "skills"


def _tenant_dir() -> Path:
    return ctx.tenant_dir() / "skills"


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    # Нелатинский заголовок (кириллица) даёт пустой ascii-slug — тогда стабильный
    # хеш от исходного текста, чтобы id был уникальным (иначе все «→ skill» слипнутся).
    if len(s) < 3:
        return "skill_" + hashlib.md5((text or "").encode("utf-8")).hexdigest()[:8]
    return s[:48]


def parse_skill_md(text: str) -> dict | None:
    """
    Разбирает markdown-скилл в dict полей. Возвращает None, если нет валидного
    frontmatter или тела. Лениво: недостающие поля получают разумные дефолты, чтобы
    реальный SKILL.md из экосистемы (у него только name/description) заработал сразу.
    """
    text = (text or "").strip()
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if not m:
        return None
    front_raw, body = m.group(1), m.group(2).strip()
    if not body:
        return None
    front: dict[str, str] = {}
    for line in front_raw.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            front[k.strip().lower()] = v.strip()
    title = front.get("title") or front.get("name") or ""
    if not title:
        return None
    desc = front.get("description", "")
    kw_raw = front.get("keywords", "")
    keywords = [w.strip().lower() for w in re.split(r"[,;]", kw_raw) if w.strip()]
    if not keywords:  # нет ключевых → берём значимые слова из title
        keywords = [w.lower() for w in re.split(r"\s+", title) if len(w) > 3]
    roles = [r.strip() for r in re.split(r"[,;]", front.get("roles", "")) if r.strip()]
    sid = front.get("id") or slugify(title)
    kind = front.get("kind", "builtin")
    return {
        "id": sid, "title": title, "description": desc,
        "keywords": keywords, "roles": roles, "kind": kind, "playbook": body,
    }


def _read_dir(d: Path) -> list[dict]:
    out: list[dict] = []
    if not d.exists():
        return out
    for f in sorted(d.glob("*.md")):
        try:
            parsed = parse_skill_md(f.read_text(encoding="utf-8"))
        except OSError:
            parsed = None
        if parsed:
            out.append(parsed)
    return out


def load_installed() -> list[dict]:
    """Установленные скиллы текущего тенанта + глобальные. Кешируется по тенанту."""
    tid = ctx.get_tenant()
    if tid in _cache:
        return _cache[tid]
    items = _read_dir(GLOBAL_DIR) + _read_dir(_tenant_dir())
    _cache[tid] = items
    return items


def _invalidate() -> None:
    _cache.pop(ctx.get_tenant(), None)


def install_markdown(text: str) -> dict:
    """Сохраняет вставленный скилл-markdown как файл тенанта. {ok,id} или {ok:False}."""
    parsed = parse_skill_md(text)
    if not parsed:
        return {"ok": False, "message": "Нужен frontmatter (--- title/description ---) и тело плейбука."}
    d = _tenant_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{parsed['id']}.md").write_text(text.strip() + "\n", encoding="utf-8")
    _invalidate()
    return {"ok": True, "id": parsed["id"], "title": parsed["title"]}


def install_url(url: str) -> dict:
    """Тянет сырой markdown по URL и устанавливает. Только по явному адресу от пользователя."""
    import urllib.request
    url = (url or "").strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        return {"ok": False, "message": "Укажи http(s)-ссылку на сырой markdown скилла."}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ai-office-skill-installer"})
        with urllib.request.urlopen(req, timeout=20) as r:
            text = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        return {"ok": False, "message": f"Не удалось скачать: {str(e)[:120]}"}
    return install_markdown(text)


def install_github(ref: str) -> dict:
    """
    'owner/repo@skill' — best-effort резолв SKILL.md через GitHub API (публичные
    репо, без токена). Не нашли — просим прямую raw-ссылку.
    """
    import json
    import urllib.request
    ref = (ref or "").strip()
    m = re.match(r"^([^/]+)/([^@]+)@(.+)$", ref)
    if not m:
        return {"ok": False, "message": "Формат: owner/repo@skill (или дай прямую raw-ссылку)."}
    owner, repo, skill = m.group(1), m.group(2), m.group(3)
    # Ищем SKILL.md по типовым путям экосистемы.
    candidates = [
        f"skills/{skill}/SKILL.md", f"{skill}/SKILL.md",
        f"skills/{skill}.md", f"{skill}.md",
    ]
    for path in candidates:
        api = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        try:
            req = urllib.request.Request(api, headers={
                "User-Agent": "ai-office-skill-installer",
                "Accept": "application/vnd.github.raw",
            })
            with urllib.request.urlopen(req, timeout=20) as r:
                text = r.read().decode("utf-8", errors="replace")
        except Exception:
            continue
        res = install_markdown(text)
        if res.get("ok"):
            return res
    return {"ok": False, "message": f"SKILL.md для «{skill}» не найден в {owner}/{repo}. "
                                    f"Дай прямую raw-ссылку на файл."}


def remove(skill_id: str) -> bool:
    """Удаляет установленный файл тенанта (встроенные скиллы не трогает)."""
    f = _tenant_dir() / f"{skill_id}.md"
    if f.exists():
        f.unlink()
        _invalidate()
        return True
    return False
