"""
Разбивка использования диска тенантом — «Хранилище» как в iPhone/Windows: не
просто список файлов, а честный ответ на «что и сколько места занимает»,
включая Docker-ресурсы (постоянные приложения, MCP-серверы), которые физически
лежат ВНЕ data/tenants/<tid>/ и раньше были невидимы совсем (живой дизайн-аудит:
«хранилище» показывало только сырое дерево файлов, без итоговой картины).

Категории:
  workspace   — файлы проектов (workspace/<project>/, по папке на проект)
  system_data — состояние тенанта в корне data/tenants/<tid>/ (trace.jsonl,
                prompts.jsonl, world_snapshots.jsonl, intents.json и т.п.)
  docker      — постоянные приложения (tenant_apps) + активные MCP-серверы
                этого тенанта; недоступен Docker — возвращает 0 с пометкой,
                не падает (тот же принцип, что exec_sandbox.SandboxUnavailable,
                но здесь диагностика, а не блокирующая операция).
"""

import subprocess
from pathlib import Path

from src.office import exec_sandbox
from src.saas import context as ctx

_DOCKER_SIZE_TIMEOUT = 15


def _dir_size(p: Path) -> int:
    if not p.exists():
        return 0
    total = 0
    for f in p.rglob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
            except OSError:
                pass
    return total


def workspace_projects() -> list[dict]:
    """Файлы проекта по папкам workspace/<project>/ — сколько весит каждый.
    workspace_dir совпадает с projects.py::workspace_dir_of — фронтенд может
    напрямую связать проект с его строкой здесь (переход «Проект → Хранилище»).
    Папки, которых нет в реестре проектов (docs/ — общие документы компании,
    пишутся ДО создания первого проекта, см. workspace.py) помечаются
    is_project=False, чтобы UI не называл их "проектом"."""
    from src.office import projects as projects_module
    known = {p["workspace_dir"] for p in projects_module.all_projects() if p.get("workspace_dir")}
    root = ctx.tenant_dir() / "workspace"
    out: list[dict] = []
    if root.exists():
        for child in sorted(root.iterdir()):
            if child.is_dir():
                out.append({"name": child.name, "bytes": _dir_size(child), "is_project": child.name in known})
        loose = sum(f.stat().st_size for f in root.glob("*") if f.is_file())
        if loose:
            out.append({"name": "", "bytes": loose, "is_project": False})
    return out


def system_data_bytes() -> int:
    """json/jsonl состояние тенанта в корне data/tenants/<tid>/ (НЕ внутри
    workspace/) — логи, память, снимки мира, журналы решений/намерений."""
    root = ctx.tenant_dir()
    total = 0
    for f in root.glob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
            except OSError:
                pass
    return total


def _parse_docker_size(raw: str) -> int:
    """`docker ps --size` отдаёt строки вида "0B (virtual 396MB)" — берём
    virtual-размер (реальный вес образа+слоёв), если есть, иначе основной."""
    raw = (raw or "").strip()
    m = raw
    if "(virtual" in raw:
        m = raw.split("(virtual", 1)[1].rstrip(")").strip()
    return _parse_size_token(m)


def _parse_size_token(tok: str) -> int:
    tok = tok.strip().upper()
    units = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    for u, mult in sorted(units.items(), key=lambda kv: -len(kv[0])):
        if tok.endswith(u):
            num = tok[: -len(u)].strip()
            try:
                return int(float(num) * mult)
            except ValueError:
                return 0
    return 0


def docker_usage() -> dict:
    """Диск, занятый Docker-контейнерами ЭТОГО тенанта (постоянные приложения
    + любые сейчас поднятые MCP-серверы) — по имени compose-проекта
    aio_<tenant>_*, тот же префикс, что tenant_apps._compose_project."""
    if exec_sandbox.mode() != "docker" or not exec_sandbox.docker_available():
        return {"available": False, "total_bytes": 0, "containers": []}

    tid = ctx.get_tenant()
    try:
        r = subprocess.run(
            [*exec_sandbox.DOCKER_CMD, "ps", "-a", "--filter", f"name=aio_{tid}_",
             "--format", "{{.Names}}\t{{.Size}}"],
            capture_output=True, text=True, timeout=_DOCKER_SIZE_TIMEOUT,
        )
    except Exception:
        return {"available": True, "total_bytes": 0, "containers": [], "error": True}

    containers = []
    total = 0
    for line in (r.stdout or "").splitlines():
        if not line.strip() or "\t" not in line:
            continue
        name, size_raw = line.split("\t", 1)
        b = _parse_docker_size(size_raw)
        containers.append({"name": name, "bytes": b})
        total += b
    return {"available": True, "total_bytes": total, "containers": containers}


def sandbox_image_bytes() -> int:
    """Образ песочницы (docker/sandbox.Dockerfile) — ОБЩИЙ для всех тенантов,
    не удаляется вместе с тенантом; показывается отдельной строкой с пометкой
    "общее", не суммируется в личный расход тенанта."""
    if exec_sandbox.mode() != "docker" or not exec_sandbox.docker_available():
        return 0
    try:
        r = subprocess.run(
            [*exec_sandbox.DOCKER_CMD, "image", "inspect", exec_sandbox.IMAGE_NAME,
             "--format", "{{.Size}}"],
            capture_output=True, text=True, timeout=_DOCKER_SIZE_TIMEOUT,
        )
        return int((r.stdout or "0").strip() or 0)
    except Exception:
        return 0


def summary() -> dict:
    """Полная разбивка для UI — категории с байтами + метаданные."""
    projects = workspace_projects()
    sys_bytes = system_data_bytes()
    docker = docker_usage()
    workspace_total = sum(p["bytes"] for p in projects)
    return {
        "workspace": {"bytes": workspace_total, "projects": projects},
        "system_data": {"bytes": sys_bytes},
        "docker": docker,
        "shared_sandbox_image_bytes": sandbox_image_bytes(),
        "total_bytes": workspace_total + sys_bytes + docker.get("total_bytes", 0),
    }
