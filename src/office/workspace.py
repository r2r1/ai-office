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


def _guess_filename(content: str) -> str:
    """Определяет имя файла по содержимому, если путь не задан."""
    c = (content or "").lstrip()
    if c.startswith("<!") or "<html" in c[:200].lower() or "<body" in c[:500].lower():
        return "index.html"
    if c.startswith("#!/usr/bin/env python") or "import " in c[:300] or "def " in c[:300]:
        return "main.py"
    if c.startswith("#!/usr/bin/env node") or "const " in c[:200] or "function " in c[:200] or "require(" in c[:300]:
        return "app.js"
    if c.startswith("#!/bin/bash") or c.startswith("#!/bin/sh"):
        return "run.sh"
    if "version:" in c[:100] or "services:" in c[:200]:
        return "docker-compose.yml"
    return "output.txt"


def write_file(path: str, content: str) -> str:
    content = content or ""
    if not (path or "").strip():
        path = _guess_filename(content)
    full = _safe(path)
    if full is None:
        path = _guess_filename(content)
        full = _safe(path)
    if full is None:
        return "Ошибка: не удалось определить путь файла. Укажи имя явно: index.html, main.py, app.js"
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


def base_dir() -> Path:
    """Корень рабочей папки тенанта (для хостинга опубликованных сайтов)."""
    return _base()


def resolve(path: str) -> Path | None:
    """Безопасно резолвит относительный путь внутри рабочей папки (или None)."""
    return _safe(path)


def read_bytes(path: str) -> bytes | None:
    """Сырые байты файла (для отдачи картинок/медиа). None — если нет/недопустим."""
    full = _safe(path)
    if full is None or not full.is_file():
        return None
    return full.read_bytes()


def list_dir(rel: str = "") -> list[dict]:
    """Файлы внутри подпапки рабочей папки (рекурсивно), пути относительно неё."""
    root = _safe(rel) if rel else _base().resolve()
    if root is None or not root.is_dir():
        return []
    out = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out.append({"path": p.relative_to(root).as_posix(), "size": p.stat().st_size})
    return out


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


def delete_file(path: str) -> str:
    full = _safe(path)
    if full is None:
        return f"Недопустимый путь: {path}"
    if not full.exists():
        return f"Файл не найден: {path}"
    full.unlink()
    return f"Файл удалён: {path}"


def execute_code(path: str, stdin_input: str = "") -> str:
    """Запускает файл из рабочей папки, возвращает stdout+stderr (макс. 30 сек)."""
    import subprocess
    import sys

    full = _safe(path)
    if full is None or not full.is_file():
        return f"Файл не найден: {path}"

    ext = full.suffix.lower()
    if ext == ".py":
        cmd = [sys.executable, str(full)]
    elif ext in (".js", ".mjs", ".ts"):
        cmd = ["node", str(full)]
    elif ext == ".sh":
        cmd = ["bash", str(full)]
    else:
        return f"Неизвестный тип файла: {ext}. Поддерживаются: .py .js .sh"

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(_base()),
            input=stdin_input or None,
        )
        out = result.stdout[-3000:] if result.stdout else ""
        err = result.stderr[-1500:] if result.stderr else ""
        code = result.returncode
        parts = []
        if out:
            parts.append(f"STDOUT:\n{out}")
        if err:
            parts.append(f"STDERR:\n{err}")
        if not parts:
            parts.append("(нет вывода)")
        status = "✅ завершён" if code == 0 else f"❌ код выхода {code}"
        return f"{status}\n" + "\n".join(parts)
    except subprocess.TimeoutExpired:
        return "❌ Таймаут: скрипт работал более 30 секунд и был остановлен."
    except FileNotFoundError as e:
        return f"❌ Интерпретатор не найден: {e}"
    except Exception as e:
        return f"❌ Ошибка запуска: {e}"


def reset() -> None:
    import shutil
    base = _base()
    if base.exists():
        shutil.rmtree(base, ignore_errors=True)
