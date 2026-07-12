"""
Каталог готовых open-source MCP-коннекторов — по одному .md-файлу на сервис
(тот же приём, что office/builtin_skills/*.md для скиллов: карточка на файл,
а не растущий Python-словарь). Решает конкретную проблему, найденную живым
разговором о Postiz: register_mcp_server даёт агенту голый command/args/env —
модель каждый раз сама вспоминает (или ВЫДУМЫВАЕТ) правильный npm-пакет, URL
эндпоинта, нужен ли stdio↔SSE мост типа mcp-remote и т.п. Один раз ошиблись
на Postiz (предложили несуществующий npx-пакет вместо реального mcp-remote-
моста на удалённый /mcp/<key> эндпоинт) — и это будет повторяться на каждом
новом open-source MCP-сервисе, если рецепт не записан один раз в файл.

Формат файла (frontmatter + тело-заметка для агента):
    ---
    id: postiz
    title: Postiz (кроспостинг в соцсети)
    keywords: постинг, кроспостинг, соцсети, публикация, карусель
    command: npx
    args: -y, mcp-remote, {POSTIZ_URL}/mcp/{POSTIZ_API_KEY}
    needs: POSTIZ_URL=адрес self-hosted Postiz; POSTIZ_API_KEY=ключ из Settings→Developers→Public API
    allow_network: true
    ---
    Свободный текст — что это, откуда взять значения needs, на что обратить внимание.

`args`/`needs` — шаблон с плейсхолдерами {VAR}; connect_mcp_connector() подставляет
значения, полученные агентом от пользователя (через ask_user), и передаёт готовый
command/args/env в mcp_tenant_servers.add — агенту не нужно ничего изобретать,
только собрать значения needs и вызвать коннектор по id.

Хранение: office/builtin_mcp_connectors/*.md — общие для всех тенантов, никакого
тенант-специфичного слоя пока не нужно (в отличие от skill_store — коннектор не
"учит" модель ничему тенант-специфичному, только описывает КАК подключиться).
"""

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Connector:
    id: str
    title: str
    description: str
    keywords: list[str] = field(default_factory=list)
    command: str = ""
    args_template: list[str] = field(default_factory=list)
    needs: list[dict] = field(default_factory=list)  # [{"key": "POSTIZ_URL", "hint": "..."}]
    allow_network: bool = False

    def to_public(self) -> dict:
        return {
            "id": self.id, "title": self.title, "description": self.description,
            "keywords": self.keywords, "command": self.command, "args_template": self.args_template,
            "needs": self.needs, "allow_network": self.allow_network,
        }

    def score(self, need: str) -> int:
        from src.office import needs as needs_module
        return needs_module.score_keywords(need, self.keywords)

    def resolve(self, values: dict[str, str]) -> tuple[list[str], list[str]]:
        """Подставляет {VAR} в args_template значениями values. Возвращает
        (готовые_args, недостающие_ключи) — недостающие не подставляются
        (плейсхолдер остаётся как есть), чтобы вызывающий увидел, чего не хватает."""
        missing = [n["key"] for n in self.needs if n["key"] not in values or not values[n["key"]]]
        args = [_substitute(a, values) for a in self.args_template]
        return args, missing


def _substitute(template: str, values: dict[str, str]) -> str:
    def repl(m: re.Match) -> str:
        key = m.group(1)
        return values.get(key, m.group(0))
    return re.sub(r"\{([A-Z0-9_]+)\}", repl, template)


_REGISTRY: dict[str, Connector] = {}


def _parse_md(text: str) -> dict | None:
    text = (text or "").strip()
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if not m:
        return None
    front_raw, body = m.group(1), m.group(2).strip()
    front: dict[str, str] = {}
    for line in front_raw.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            front[k.strip().lower()] = v.strip()
    sid = front.get("id", "").strip()
    title = front.get("title", "").strip()
    if not sid or not title:
        return None
    keywords = [w.strip().lower() for w in re.split(r"[,;]", front.get("keywords", "")) if w.strip()]
    args_template = [a.strip() for a in front.get("args", "").split(",") if a.strip()]
    needs: list[dict] = []
    for chunk in re.split(r"[;\n]", front.get("needs", "")):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        key, hint = chunk.split("=", 1)
        needs.append({"key": key.strip(), "hint": hint.strip()})
    allow_network = front.get("allow_network", "").strip().lower() in ("true", "1", "yes")
    return {
        "id": sid, "title": title, "description": body, "keywords": keywords,
        "command": front.get("command", "").strip(), "args_template": args_template,
        "needs": needs, "allow_network": allow_network,
    }


def register(c: Connector) -> None:
    _REGISTRY[c.id] = c


def get(connector_id: str) -> Connector | None:
    return _REGISTRY.get((connector_id or "").strip())


def all_connectors() -> list[Connector]:
    return list(_REGISTRY.values())


def match(need: str, top: int = 3) -> list[Connector]:
    scored = [(c.score(need), c) for c in _REGISTRY.values()]
    scored = [(s, c) for s, c in scored if s > 0]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top]]


def _load_builtin_dir() -> None:
    d = Path(__file__).parent / "builtin_mcp_connectors"
    if not d.exists():
        return
    for f in sorted(d.glob("*.md")):
        try:
            parsed = _parse_md(f.read_text(encoding="utf-8"))
        except OSError:
            parsed = None
        if parsed:
            register(Connector(
                id=parsed["id"], title=parsed["title"], description=parsed["description"],
                keywords=parsed["keywords"], command=parsed["command"], args_template=parsed["args_template"],
                needs=parsed["needs"], allow_network=parsed["allow_network"],
            ))


_load_builtin_dir()
