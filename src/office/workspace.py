"""
Рабочая папка проекта — агенты пишут реальный код. По тенанту:
data/tenants/<tid>/workspace/. Защита от выхода за пределы каталога.

Параллельные Work (Фаза 3, project_limits): у каждого активного проекта —
СВОЯ подпапка внутри workspace/ (projects.workspace_dir, читаемое имя вроде
"landing_1"), а не общий плоский корень на весь тенант. Иначе два одновременно
активных проекта, пишущих в одинаково называющиеся файлы (app.js, index.html),
физически затирали бы друг друга — тот же класс бага, что уже был ВНУТРИ
одного проекта и решался мьютексом артефакта (plan.site_task_in_progress).

Область видимости — ContextVar `_project_dir`, тот же приём, что `saas/context.
_tenant` для тенанта: устанавливается ОДИН раз в начале исполнения задачи
(execution.run_task — по project_id этой задачи) и автоматически изолирована
между параллельными asyncio-тасками (contextvars копируются на
asyncio.create_task, не расшариваются) — двум задачам разных проектов,
исполняющимся в один момент, не нужен явный лок или сброс после каждой.
Пусто ("") — легаси/общий доступ к КОРНЮ workspace (как было раньше,
для тенантов с одним проектом и для company-wide файлов вроде docs/strategy.md,
которые пишутся ДО того, как какой-либо проект существует).

execute_code/run_command исполняют процесс (интерпретатор/shell) через
src/office/exec_sandbox.py. По умолчанию (SANDBOX_MODE=direct) — БЕЗ изоляции
от файловой системы хоста, как и раньше: `_safe()` защищает только путь
ФАЙЛА, который запускается, а не то, что делает запущенный код/команда —
Python-скрипт или shell-команда внутри workspace могут прочитать
`../../<чужой-tenant>/connections.json`, `.env` и т.д. с правами процесса
сервера (реальная находка DD-аудита, docs/audit-dd-2026-07.md §17). Реальная
изоляция — SANDBOX_MODE=docker (контейнер без сети, read-only ФС, лимиты
ресурсов, см. exec_sandbox.py и docker/sandbox.Dockerfile) — требует
установленного Docker и собранного образа, не включена по умолчанию, чтобы
не ломать деплои без Docker. Обе функции по-прежнему по умолчанию ВЫКЛЮЧЕНЫ
целиком (opt-in через ALLOW_CODE_EXECUTION=1) независимо от SANDBOX_MODE.
"""

import contextlib
import contextvars
import os
import re
from pathlib import Path

from src.saas import context as ctx

MAX_FILE_BYTES = 200_000

# См. докстринг модуля — область видимости workspace на текущий проект.
_project_dir: contextvars.ContextVar[str] = contextvars.ContextVar("workspace_project_dir", default="")


def set_project_dir(d: str) -> None:
    """Переключает workspace на подпапку конкретного проекта (или "" — корень/
    легаси). Вызывать в НАЧАЛЕ исполнения задачи (см. execution.run_task) —
    контекст изолирован per-asyncio-Task, дальнейший явный сброс не обязателен."""
    _project_dir.set((d or "").strip())


def get_project_dir() -> str:
    return _project_dir.get()


@contextlib.contextmanager
def project_scope(project_dir: str):
    """Временно переключает workspace на project_dir, ГАРАНТИРОВАННО возвращая
    прежнее значение по выходу (даже при исключении/continue) — в отличие от
    голого set_project_dir(), который остаётся в силе до следующего явного
    вызова. Нужен там, где сама область — не одноразовый asyncio.Task (как в
    execution.run_task), а долгоживущая корутина цикла тенанта (office/loop.py):
    без сброса finalize-блок одной итерации "просачивался" бы в scope
    следующей итерации того же цикла."""
    token = _project_dir.set((project_dir or "").strip())
    try:
        yield
    finally:
        _project_dir.reset(token)


# Единая точка правды: разрешено ли исполнение кода/shell-команд из workspace.
# Читаем ЛЕНИВО (не на импорт модуля) — тесты и .env могут выставлять переменную
# после старта процесса; редко вызываемая функция, не критично к производительности.
def code_execution_allowed() -> bool:
    return os.getenv("ALLOW_CODE_EXECUTION", "0") == "1"


_DISABLED_MSG = (
    "❌ Исполнение кода отключено оператором платформы (ALLOW_CODE_EXECUTION=0) — "
    "критический security-риск без песочницы (см. docs/audit-dd-2026-07.md §17): "
    "запущенный процесс не изолирован от файловой системы хоста и может прочитать "
    "данные других клиентов. Проверяй код через verify_code (компиляция) или "
    "перечитай файл глазами; включить исполнение может только оператор."
)


def _base() -> Path:
    p = ctx.tenant_dir() / "workspace"
    pd = get_project_dir()
    if pd:
        p = p / pd
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
    # Регресс контента: агент перезаписывает существующий текстовый файл заметно более
    # коротким без причины (реальный кейс: docs/offer.md 2808 → 1089 символов — агент не
    # читал прошлую версию и потерял часть офферов). Не блокируем запись — предупреждаем,
    # чтобы агент сам решил, специально это или потеря контента.
    shrink_warning = ""
    if full.suffix.lower() in (".md", ".txt") and full.is_file():
        old_len = len(full.read_text(encoding="utf-8", errors="replace"))
        if old_len > 500 and len(content) < old_len * 0.6:
            shrink_warning = (f" ⚠ Было {old_len} символов, стало {len(content)} — если это не "
                              "осознанное сокращение, перечитай прошлую версию и объедини.")
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return (f"Файл сохранён: {full.relative_to(_base().resolve()).as_posix()} "
            f"({len(content)} символов).{shrink_warning}")


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


MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB — щедро для фото/аудио, не безгранично


def write_bytes(path: str, data: bytes) -> Path | None:
    """Сохраняет сырые байты (загрузка пользователя — фото/аудио/pdf, round2
    audit, раунд1 #2). В отличие от write_file (только текст, инструмент
    агента) — путь ВСЕГДА валиден и предсказуем (генерируется на бэкенде, не
    приходит от LLM), поэтому проверка `_safe()` тут скорее защита от опечатки
    в собственном коде, чем от инъекции пути. None — путь недопустим/файл
    больше лимита."""
    if len(data) > MAX_UPLOAD_BYTES:
        return None
    full = _safe(path)
    if full is None:
        return None
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(data)
    return full


def list_dir(rel: str = "") -> list[dict]:
    """Файлы внутри подпапки рабочей папки (рекурсивно), пути относительно неё."""
    root = _safe(rel) if rel else _base().resolve()
    if root is None or not root.is_dir():
        return []
    out = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            rel_posix = p.relative_to(root).as_posix()
            if _ignored(rel_posix):
                continue
            out.append({"path": rel_posix, "size": p.stat().st_size})
    return out


# Служебные папки, которые НЕ являются исходниками проекта: зависимости и кеши
# сборки. Обязаны быть исключены из листинга — иначе появление npm-проекта
# (node_modules = тысячи файлов) кладёт критика/verify/дерево файлов агента.
_IGNORED_DIRS = {"node_modules", ".git", "__pycache__", ".vite", ".cache", ".npm"}


def _ignored(rel_posix: str) -> bool:
    return any(seg in _IGNORED_DIRS for seg in rel_posix.split("/")[:-1])


def list_files() -> list[dict]:
    base = _base().resolve()
    out = []
    for p in sorted(base.rglob("*")):
        if p.is_file():
            rel = p.relative_to(base).as_posix()
            if _ignored(rel):
                continue
            st = p.stat()
            out.append({"path": rel, "size": st.st_size, "mtime": st.st_mtime})
    return out


def tree_text() -> str:
    files = list_files()
    if not files:
        return "Рабочая папка пуста."
    return "\n".join(f"  {f['path']} ({f['size']} б)" for f in files)


# ── Кросс-проектное ЧТЕНИЕ (иерархия доступа лидеров) ─────────────────────────
# Лидеры/CEO видят бизнес насквозь — читают файлы ЛЮБОГО проекта тенанта, не
# только своего. Реализовано поверх project_scope() (не сменой мутируемого
# _project_dir): область гарантированно возвращается по выходу, и здесь есть
# ТОЛЬКО чтение — записи в чужой проект по построению нет (инвариант единой
# ответственности за артефакт). project_dir обязан приходить уже
# провалидированным через projects.valid_workspace_dir (имя из реестра, не
# сырая строка от модели) — иначе см. риск path-инъекции в PRD иерархии доступа.

def read_file_in(project_dir: str, path: str) -> str:
    """Читает файл конкретного проекта тенанта (read-only, для лидеров)."""
    with project_scope(project_dir):
        return read_file(path)


def tree_text_in(project_dir: str) -> str:
    """Дерево файлов конкретного проекта тенанта (read-only, для лидеров)."""
    with project_scope(project_dir):
        return tree_text()


def _js_syntax_error(code: str, as_module: bool = True) -> str:
    """
    Проверяет JS через `node --check` (реальный парсер). '' если ок или node недоступен.
    as_module=True пишет во временный .mjs — иначе `node --check` падает на ЛЮБОМ
    import/export (наш 3D-скилл — React/framer-motion строго через ESM-import), выдавая
    ложную ошибку на валидном коде.
    """
    if not code.strip():
        return ""
    import shutil
    if not shutil.which("node"):
        return ""  # node нет на сервере — тихо пропускаем (не ложная тревога)
    import subprocess, tempfile, os
    tmp = None
    try:
        suffix = ".mjs" if as_module else ".js"
        with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8") as f:
            f.write(code)
            tmp = f.name
        r = subprocess.run(["node", "--check", tmp], capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            out = (r.stderr or r.stdout or "").strip().splitlines()
            err_line = next((ln for ln in out if "error" in ln.lower() and "node.js" not in ln.lower()), "")
            return (err_line or "синтаксическая ошибка").strip()
        return ""
    except Exception:
        return ""
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except Exception:
                pass


def verify(changed_since: float = 0.0) -> dict:
    """
    Статическая проверка работоспособности: компиляция .py + синтаксис .js/.mjs
    (отдельных файлов И инлайновых <script type="module"> в .html).

    Раньше проверялся ТОЛЬКО .py — для 3D-лендинга (весь код на React/framer-motion
    в JS, ни одного .py файла) verify_code всегда отвечал «✅ 0 .py файлов
    компилируются без ошибок» — ложное «всё ок» без единой реальной проверки того,
    что агент только что написал (реальный кейс: designer/developer получали этот
    зелёный чек на JS с синтаксическими ошибками и сдавали задачу как готовую).

    `changed_since` > 0 — проверять только файлы, изменённые после этой метки
    (mtime). Нужен приёмке ЗАДАЧИ: битый файл, оставленный ЧУЖОЙ задачей, не должен
    валить приёмку текущей (кросс-контаминация: 3 таких провала блокировали
    невиновную задачу). 0 — прежнее поведение, весь workspace.
    """
    import py_compile
    files = list_files()
    if changed_since > 0:
        files = [f for f in files if f.get("mtime", 0) >= changed_since]
    # Выход сборки (dist/…) валидирует сама сборка — гонять node --check по
    # минифицированным бандлам бессмысленно и медленно (ленивый импорт от цикла).
    from src.office import site_builder
    files = [f for f in files if not site_builder.is_built_output(f["path"])]
    py_files = [f for f in files if f["path"].endswith(".py")]
    js_files = [f for f in files if f["path"].endswith((".js", ".mjs"))]
    html_files = [f for f in files if f["path"].endswith(".html")]
    errors = []
    for f in py_files:
        full = _safe(f["path"])
        if full is None:
            continue
        try:
            py_compile.compile(str(full), doraise=True)
        except py_compile.PyCompileError as e:
            errors.append(f"{f['path']}: {getattr(e, 'msg', str(e))}")
    checked_js = 0
    for f in js_files:
        code = read_file(f["path"])
        is_module = f["path"].endswith(".mjs") or bool(re.search(r"^\s*(import|export)\s", code, re.M))
        err = _js_syntax_error(code, as_module=is_module)
        checked_js += 1
        if err:
            errors.append(f"{f['path']}: {err}")
    for f in html_files:
        code = read_file(f["path"])
        for m in re.finditer(r'<script[^>]*type=["\']module["\'][^>]*>(.*?)</script>',
                              code, re.IGNORECASE | re.DOTALL):
            inline = m.group(1)
            err = _js_syntax_error(inline, as_module=True)
            checked_js += 1
            if err:
                errors.append(f"{f['path']}: инлайн <script type=module> — {err}")
    has_reqs = any(f["path"].endswith("requirements.txt") for f in files)
    return {"ok": not errors, "checked_py": len(py_files), "checked_js": checked_js,
            "total_files": len(files), "errors": errors, "has_requirements": has_reqs}


def verify_text() -> str:
    if not list_files():
        return "Проект пуст — сначала напиши код через write_file."
    r = verify()
    if r["ok"]:
        warn = "" if r["has_requirements"] else " ⚠ нет requirements.txt — добавь зависимости."
        return (f"✅ Проверка пройдена: {r['checked_py']} .py и {r['checked_js']} .js/.mjs/inline "
                f"файлов компилируются без ошибок (всего файлов: {r['total_files']}).{warn}")
    return "❌ Ошибки компиляции:\n" + "\n".join(r["errors"][:15])


def delete_file(path: str) -> str:
    full = _safe(path)
    if full is None:
        return f"Недопустимый путь: {path}"
    if not full.exists():
        return f"Файл не найден: {path}"
    full.unlink()
    return f"Файл удалён: {path}"


def _utf8_env() -> dict:
    """Окружение для дочерних процессов execute_code/run_command — БЕЗ полного
    наследования os.environ. Раньше env=dict(os.environ) прокидывал в subprocess
    ВСЁ окружение сервера целиком: APP_SECRET, LLM_API_KEY, APINET_ACCESS_TOKEN,
    GITHUB_CLIENT_SECRET и т.д. — агенту не нужен даже path traversal (см. docs/
    audit-dd-2026-07.md §17), чтобы украсть креды: `import os; print(os.environ)`
    в собственном же коде отдавал их напрямую (найдено при аудите 2026-07-06,
    docs/audit-dd-2026-07-06.md §11). Allowlist — только то, что реально нужно
    интерпретатору/шеллу для запуска (PATH и системные переменные ОС), плюс
    UTF-8-энкодинг (см. ниже, для русского/эмодзи-вывода на Windows)."""
    import os
    _ALLOWLIST = {
        "PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP",
        "HOMEDRIVE", "HOMEPATH", "USERPROFILE", "HOME", "LANG", "LC_ALL",
        "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
    }
    env = {k: v for k, v in os.environ.items() if k.upper() in _ALLOWLIST}
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def execute_code(path: str, stdin_input: str = "") -> str:
    """Запускает файл из рабочей папки, возвращает stdout+stderr (макс. 30 сек)."""
    import subprocess
    from src.office import exec_sandbox

    if not code_execution_allowed():
        return _DISABLED_MSG

    full = _safe(path)
    if full is None or not full.is_file():
        return f"Файл не найден: {path}"

    ext = full.suffix.lower()
    rel = full.relative_to(_base().resolve()).as_posix()
    # Долгоживущий Telegram-бот (long polling) НЕЛЬЗЯ запускать здесь: процесс висит
    # до таймаута, а под uvicorn --reload запись bot.py и так перезагружает сервер.
    # Боты запускаются штатно через integrations.telegram.launch_bot, не через execute_code.
    if ext == ".py":
        try:
            code = full.read_text(encoding="utf-8", errors="replace").lower()
        except Exception:
            code = ""
        if any(s in code for s in ("start_polling", "run_polling", "infinity_polling",
                                   "executor.start_polling", "dp.run_polling")):
            return ("⏭ Пропущен запуск: это бот с long-polling — он работает бесконечно и "
                    "здесь только повис бы. Синтаксис проверь через verify_code, а сам бот "
                    "запусти штатно через интеграцию Telegram (launch_bot), не execute_code.")
    if ext == ".py":
        lang = "python"
    elif ext in (".js", ".mjs", ".ts"):
        # Клиентский JS сайта (site/*.js) выполняется в браузере, а не в Node — там нет
        # document/window/navigator. Реальный кейс: developer гонял site/script.js через
        # execute_code, ловил "document is not defined", решал что скрипт сломан и дважды
        # переписывал его всё короче (3081 → 1550 → 637 символов), теряя функциональность
        # в погоне за несуществующей ошибкой. Раньше запрещали только .html/.css — теперь
        # явно предупреждаем и здесь, до запуска Node.
        try:
            js_code = full.read_text(encoding="utf-8", errors="replace")
        except Exception:
            js_code = ""
        is_site_js = rel.startswith("site/") or "/site/" in rel
        uses_browser_globals = bool(re.search(r"\b(document|window|navigator|localStorage)\b", js_code))
        if is_site_js and uses_browser_globals:
            return ("⏭ Пропущен запуск: это браузерный скрипт (использует document/window), "
                    "а execute_code запускает через Node, где их нет — «document is not defined» "
                    "здесь НЕ означает, что код сломан. Проверяй такой JS через verify_code "
                    "(синтаксис) или глазами при открытии сайта, не через execute_code.")
        lang = "node"
    elif ext == ".sh":
        lang = "bash"
    else:
        return f"Неизвестный тип файла: {ext}. Поддерживаются: .py .js .sh"

    try:
        result = exec_sandbox.run_script(lang, rel, workdir=_base(), timeout=30,
                                         stdin_input=stdin_input)
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
    except exec_sandbox.SandboxUnavailable as e:
        return f"❌ {e}"
    except FileNotFoundError as e:
        return f"❌ Интерпретатор не найден: {e}"
    except Exception as e:
        return f"❌ Ошибка запуска: {e}"


def run_command(cmd: str, cwd_rel: str = "") -> str:
    """
    Выполняет произвольную команду в рабочей папке тенанта (терминал).
    cwd_rel — подпапка внутри workspace, откуда запускать (для вложенности).
    Ограничения: таймаут 30 сек, рабочая директория — внутри workspace.
    """
    import subprocess
    from src.office import exec_sandbox

    if not code_execution_allowed():
        return _DISABLED_MSG

    cmd = (cmd or "").strip()
    if not cmd:
        return "(пустая команда)"

    # Рабочая директория: подпапка внутри workspace (или корень) — в
    # docker-режиме монтируется как /workspace целиком, так что команда
    # физически не видит ничего за пределами ЭТОЙ директории.
    workdir = _base().resolve()
    if cwd_rel:
        sub = _safe(cwd_rel)
        if sub is not None and sub.is_dir():
            workdir = sub

    try:
        result = exec_sandbox.run_shell(cmd, workdir=workdir, timeout=30)
        out = (result.stdout or "")[-4000:]
        err = (result.stderr or "")[-2000:]
        parts = []
        if out:
            parts.append(out.rstrip())
        if err:
            parts.append(err.rstrip())
        body = "\n".join(parts) if parts else "(нет вывода)"
        if result.returncode != 0:
            body += f"\n[код выхода {result.returncode}]"
        return body
    except subprocess.TimeoutExpired:
        return "❌ Таймаут: команда работала более 30 секунд и была остановлена."
    except exec_sandbox.SandboxUnavailable as e:
        return f"❌ {e}"
    except Exception as e:
        return f"❌ Ошибка: {e}"


def reset() -> None:
    """Стирает ВЕСЬ workspace тенанта (все проекты), независимо от того, какой
    project_dir сейчас установлен в контексте вызывающего — "сброс" означает
    весь тенант, не только текущий проект."""
    import shutil
    base = ctx.tenant_dir() / "workspace"
    if base.exists():
        shutil.rmtree(base, ignore_errors=True)
