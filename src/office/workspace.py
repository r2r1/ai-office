"""
Рабочая папка проекта — агенты пишут реальный код. По тенанту:
data/tenants/<tid>/workspace/. Защита от выхода за пределы каталога.
"""

from pathlib import Path

from src.saas import context as ctx

MAX_FILE_BYTES = 200_000


def _base() -> Path:
    p = ctx.tenant_dir() / "workspace"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _safe(path: str) -> Path | None:
    p = (path or "").strip().replace("\\", "/").lstrip("/")
    if not p or ".." in Path(p).parts:
        return None
    base = _base().resolve()
    full = (base / p).resolve()
    if base != full and base not in full.parents:
        return None
    return full


def write_file(path: str, content: str) -> str:
    full = _safe(path)
    if full is None:
        return f"Недопустимый путь: {path}"
    content = content or ""
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        return f"Файл слишком большой (> {MAX_FILE_BYTES} байт). Разбей на модули."
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return f"Файл сохранён: {full.relative_to(_base().resolve()).as_posix()} ({len(content)} символов)."


def read_file(path: str) -> str:
    full = _safe(path)
    if full is None or not full.is_file():
        return f"Файл не найден: {path}"
    return full.read_text(encoding="utf-8", errors="replace")[:MAX_FILE_BYTES]


def list_files() -> list[dict]:
    base = _base().resolve()
    out = []
    for p in sorted(base.rglob("*")):
        if p.is_file():
            out.append({"path": p.relative_to(base).as_posix(), "size": p.stat().st_size})
    return out


def tree_text() -> str:
    files = list_files()
    if not files:
        return "Рабочая папка пуста."
    return "\n".join(f"  {f['path']} ({f['size']} б)" for f in files)


def verify() -> dict:
    """Статическая проверка работоспособности: компиляция всех .py файлов проекта."""
    import py_compile
    files = list_files()
    py_files = [f for f in files if f["path"].endswith(".py")]
    errors = []
    for f in py_files:
        full = _safe(f["path"])
        if full is None:
            continue
        try:
            py_compile.compile(str(full), doraise=True)
        except py_compile.PyCompileError as e:
            errors.append(f"{f['path']}: {getattr(e, 'msg', str(e))}")
    has_reqs = any(f["path"].endswith("requirements.txt") for f in files)
    return {"ok": not errors, "checked_py": len(py_files), "total_files": len(files),
            "errors": errors, "has_requirements": has_reqs}


def verify_text() -> str:
    if not list_files():
        return "Проект пуст — сначала напиши код через write_file."
    r = verify()
    if r["ok"]:
        warn = "" if r["has_requirements"] else " ⚠ нет requirements.txt — добавь зависимости."
        return (f"✅ Проверка пройдена: {r['checked_py']} .py файлов компилируются без ошибок "
                f"(всего файлов: {r['total_files']}).{warn}")
    return "❌ Ошибки компиляции:\n" + "\n".join(r["errors"][:15])


def reset() -> None:
    import shutil
    base = _base()
    if base.exists():
        shutil.rmtree(base, ignore_errors=True)
