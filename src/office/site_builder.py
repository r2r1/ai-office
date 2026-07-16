"""
Site Builder — этап сборки в производственном пайплайне артефакта «site» (BOS §12).

Раньше публикация просто хостила папку site/ как статику — рендерились только
сайты без шага сборки (HTML/CSS/JS или React через esm.sh-importmap). Теперь
офис умеет и полноценные фреймворки со сборкой (Vite/React/Vue/…): агент кладёт
проект с package.json в site/, а платформа детерминированно собирает его и
публикует РЕЗУЛЬТАТ сборки (dist/), а не исходники.

  detect()          — static | build | none: что лежит в workspace
  ensure_built()    — async: npm install + npm run build с кешем по отпечатку
                      исходников (пересборка ТОЛЬКО при изменениях — иначе каждая
                      публикация/приёмка жгла бы минуты на пустую пересборку)
  published_root()  — sync: какую папку публиковать/проверять критику ПРЯМО СЕЙЧАС
                      (dist для собранных, site/ для статики)
  cached_problem()  — sync: структурная проблема сборки для приёмки/критика
                      (читает кеш — приёмка синхронна и не имеет права собирать)

⚠️ Сборка = исполнение чужого кода (npm postinstall-скрипты пакетов) БЕЗ
изоляции от ФС хоста — тот же класс критического security-долга, что
execute_code/run_command (docs/audit-dd-2026-07.md §17). Поэтому гейт:
ALLOW_SITE_BUILD=1, по умолчанию наследует ALLOW_CODE_EXECUTION. При
выключенном гейте build-проект получает ЧЁТКИЙ фидбек приёмки «собери статику
или используй esm.sh-скилл» — офис деградирует в статику, а не молча падает.

Требование к проектам (живёт в скилле vite_react_site): база ассетов
ОТНОСИТЕЛЬНАЯ (`base: './'` в vite.config) — сайт хостится под
/site/{tenant}/{slug}/, абсолютные /assets/… не резолвятся. Билдер дополнительно
форсит `-- --base=./` для vite-сборок (защита от забытого конфига).

Кеш: data/tenants/<tid>/site_build.json —
  {ok, out_dir, log_tail, fingerprint, ts, reason}
Отпечаток — максимальный mtime исходников проекта (без node_modules и out-папок):
изменился любой исходник → отпечаток вырос → пересборка.
"""

import asyncio
import json
import os
import shutil
import subprocess
import time

from src.saas import context as ctx
from src.office import workspace

_CACHE_FILE = "site_build.json"

BUILD_TIMEOUT = int(os.getenv("SITE_BUILD_TIMEOUT", "600"))       # npm run build
INSTALL_TIMEOUT = int(os.getenv("SITE_INSTALL_TIMEOUT", "900"))   # npm install (первый — тяжёлый)

# Типовые выходные папки сборщиков (vite→dist, CRA→build, next export→out).
_OUT_DIR_NAMES = ("dist", "build", "out")


def build_allowed() -> bool:
    """Гейт исполнения сборки. Отдельная ручка ALLOW_SITE_BUILD (оператор может
    разрешить только сборку без терминала), по умолчанию — наследует общий
    ALLOW_CODE_EXECUTION: npm postinstall исполняет произвольный код пакетов."""
    v = os.getenv("ALLOW_SITE_BUILD", "").strip()
    if v in ("0", "1"):
        return v == "1"
    return workspace.code_execution_allowed()


# ─────────────────────────── детект ───────────────────────────

def _read_package_json(rel_dir: str) -> dict | None:
    raw = workspace.read_file(f"{rel_dir}/package.json" if rel_dir else "package.json")
    if not raw or raw.startswith("Файл не найден"):
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None


def detect() -> dict:
    """Что лежит в workspace: {"kind": "build"|"static"|"none", "root": str}.
    build — package.json со scripts.build (канонично в site/, допускаем корень);
    static — есть index.html без сборочного package.json рядом."""
    for root in ("site", ""):
        pkg = _read_package_json(root)
        if pkg and (pkg.get("scripts") or {}).get("build"):
            return {"kind": "build", "root": root}
    paths = {f["path"] for f in workspace.list_files()}
    if "site/index.html" in paths:
        return {"kind": "static", "root": "site"}
    for p in sorted(paths):
        if p == "index.html":
            return {"kind": "static", "root": ""}
        if p.endswith("/index.html") and not _in_out_dir(p):
            return {"kind": "static", "root": p[: -len("/index.html")]}
    return {"kind": "none", "root": ""}


def _in_out_dir(path: str) -> bool:
    parts = path.split("/")
    return any(seg in _OUT_DIR_NAMES for seg in parts[:-1])


# ─────────────────────────── отпечаток исходников ───────────────────────────

# Файлы, которые ГЕНЕРИТ сам npm install в папке исходников: производные от
# package.json, не исходники. Без исключения из отпечатка первая же сборка
# «трогала» проект (появлялся package-lock.json) → кеш мгновенно устаревал →
# каждая публикация запускала пересборку заново (пойман живым смоуком).
_DERIVED_FILES = ("package-lock.json", "yarn.lock", "pnpm-lock.yaml")


def _src_fingerprint(root: str) -> float:
    """Максимальный mtime исходников проекта — БЕЗ выходных папок сборки и
    lock-файлов (иначе сама сборка меняла бы отпечаток и вечно требовала
    пересборку). node_modules уже исключён из list_files глобально."""
    prefix = f"{root}/" if root else ""
    fp = 0.0
    for f in workspace.list_files():
        p = f["path"]
        if prefix and not p.startswith(prefix):
            continue
        rel = p[len(prefix):] if prefix else p
        if _in_out_dir(rel) or rel.rsplit("/", 1)[-1] in _DERIVED_FILES:
            continue
        fp = max(fp, f.get("mtime", 0.0))
    return fp


# ─────────────────────────── кеш результата ───────────────────────────

def _cache() -> dict:
    return ctx.read_json(_CACHE_FILE, {})


def _save_cache(d: dict) -> None:
    ctx.write_json(_CACHE_FILE, d)


def _cache_fresh(cache: dict, fingerprint: float) -> bool:
    return bool(cache) and cache.get("fingerprint", -1.0) >= fingerprint


# ─────────────────────────── сборка ───────────────────────────

def _npm() -> str | None:
    return shutil.which("npm") or shutil.which("npm.cmd")


def _run(cmd: list[str], cwd: str, timeout: int) -> tuple[int, str]:
    """Блокирующий запуск (вызывается через asyncio.to_thread). Возвращает
    (returncode, лог stdout+stderr)."""
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout,
                           shell=False)
        log = (r.stdout or "") + "\n" + (r.stderr or "")
        return r.returncode, log
    except subprocess.TimeoutExpired:
        return 1, f"таймаут: {' '.join(cmd)} работал дольше {timeout}с и был остановлен"
    except FileNotFoundError as e:
        return 1, f"исполняемый файл не найден: {e}"
    except Exception as e:
        return 1, f"ошибка запуска: {e}"


def _find_out_dir(root: str, started_ts: float) -> str | None:
    """Выходная папка сборки: типовое имя, внутри свежий index.html."""
    prefix = f"{root}/" if root else ""
    for name in _OUT_DIR_NAMES:
        idx_rel = f"{prefix}{name}/index.html"
        full = workspace.resolve(idx_rel)
        if full is not None and full.is_file():
            try:
                if full.stat().st_mtime >= started_ts - 5:
                    return f"{prefix}{name}".strip("/")
            except OSError:
                continue
    return None


def _is_vite(root: str) -> bool:
    pkg = _read_package_json(root) or {}
    deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
    return "vite" in deps or "vite" in (pkg.get("scripts", {}).get("build", ""))


def _build_sync(root: str, fingerprint: float) -> dict:
    """Полный прогон install+build (в thread). Пишет и возвращает кеш-запись."""
    from src.office import trace
    t0 = time.time()
    proj = workspace.resolve(root or ".")
    if proj is None or not proj.is_dir():
        return _finish(dict(ok=False, out_dir="", fingerprint=fingerprint,
                            reason="папка проекта не найдена", log_tail=""), t0)

    npm = _npm()
    if not npm:
        return _finish(dict(ok=False, out_dir="", fingerprint=fingerprint,
                            reason="npm не найден на сервере — сборка невозможна",
                            log_tail=""), t0)

    # npm install — только если node_modules нет или package.json новее него.
    node_modules = proj / "node_modules"
    pkg_file = proj / "package.json"
    need_install = not node_modules.is_dir()
    if not need_install:
        try:
            need_install = pkg_file.stat().st_mtime > node_modules.stat().st_mtime
        except OSError:
            need_install = True
    log = ""
    if need_install:
        trace.log("site_build", step="install", root=root)
        code, ilog = _run([npm, "install", "--no-audit", "--no-fund"],
                          str(proj), INSTALL_TIMEOUT)
        log += ilog
        if code != 0:
            # Реальный найденный баг (живая проверка сборки настоящего 3D-Vite-проекта,
            # 2026-07-16): прерванный npm install (ENOSPC/сеть/таймаут) оставляет
            # node_modules НАПОЛОВИНУ заполненным — следующий вызов видел, что
            # node_modules существует, и НИКОГДА больше не переустанавливал, поэтому
            # сборка молча падала на каждой попытке из-за одного и того же
            # повреждённого пакета, пока кто-то не удалял node_modules руками.
            # Удаляем недоустановленную папку — следующий вызов увидит её отсутствие
            # и честно переустановит с нуля, а не будет пересдавать один и тот же лог.
            shutil.rmtree(node_modules, ignore_errors=True)
            return _finish(dict(ok=False, out_dir="", fingerprint=fingerprint,
                                reason="npm install не прошёл",
                                log_tail=log[-1500:]), t0)

    build_started = time.time()
    cmd = [npm, "run", "build"]
    if _is_vite(root):
        # Форс относительной базы ассетов: сайт хостится под /site/{tid}/{slug}/,
        # абсолютные /assets/… не резолвятся. Дублирует требование скилла —
        # защита от забытого base в vite.config.
        cmd += ["--", "--base=./"]
    trace.log("site_build", step="build", root=root, vite=_is_vite(root))
    code, blog = _run(cmd, str(proj), BUILD_TIMEOUT)
    log += "\n" + blog
    if code != 0:
        return _finish(dict(ok=False, out_dir="", fingerprint=fingerprint,
                            reason="npm run build не прошёл",
                            log_tail=log[-1500:]), t0)

    out = _find_out_dir(root, build_started)
    if not out:
        return _finish(dict(ok=False, out_dir="", fingerprint=fingerprint,
                            reason="сборка прошла, но выходная папка с index.html "
                                   f"не найдена (искал {', '.join(_OUT_DIR_NAMES)})",
                            log_tail=log[-1500:]), t0)
    return _finish(dict(ok=True, out_dir=out, fingerprint=fingerprint,
                        reason="", log_tail=log[-800:]), t0)


def _finish(entry: dict, t0: float) -> dict:
    from src.office import trace
    entry["ts"] = time.time()
    entry["took_sec"] = round(time.time() - t0, 1)
    _save_cache(entry)
    trace.log("site_build", ok=entry["ok"], out=entry.get("out_dir", ""),
              sec=entry["took_sec"], reason=entry.get("reason", "")[:120])
    return entry


# Одна сборка на тенанта одновременно: параллельные публикация+приёмка не должны
# гонять два npm по одной папке. Ключ — tenant id (процессная живость, тот же
# признанный класс, что watchdog: вынос — по триггеру multi-process).
_locks: dict[str, asyncio.Lock] = {}


async def ensure_built(publish=None) -> dict:
    """Гарантирует актуальную сборку build-проекта. Для static/none — no-op
    {"ok": True, "kind": ...}. Кеш свежий → мгновенный возврат без npm."""
    d = detect()
    if d["kind"] != "build":
        return {"ok": True, "kind": d["kind"], "out_dir": d["root"]}

    fp = _src_fingerprint(d["root"])
    cache = _cache()
    # ⚠️ Реальный найденный баг (та же живая проверка сборки, 2026-07-16): кеш
    # считался "свежим" только по отпечатку исходников, БЕЗ учёта ok — упавшая
    # сборка (ENOSPC/сеть/временная недоступность npm-реестра) кешировалась и
    # НАВСЕГДА блокировала повторную попытку, пока исходники не изменятся хоть
    # на байт, даже если причина сбоя была временной и уже исчезла. Пропускаем
    # реальную сборку по кешу ТОЛЬКО если прошлая попытка реально удалась —
    # неудача всегда получает шанс на повтор.
    if cache.get("ok") and _cache_fresh(cache, fp):
        return {**cache, "kind": "build"}

    if not build_allowed():
        entry = dict(ok=False, out_dir="", fingerprint=fp, ts=time.time(), took_sec=0,
                     reason="сборка отключена оператором (ALLOW_SITE_BUILD=0)",
                     log_tail="")
        _save_cache(entry)
        return {**entry, "kind": "build"}

    lock = _locks.setdefault(ctx.get_tenant(), asyncio.Lock())
    async with lock:
        # Пока ждали лок, параллельная корутина могла уже собрать то же самое.
        cache = _cache()
        if cache.get("ok") and _cache_fresh(cache, fp):
            return {**cache, "kind": "build"}
        if publish:
            await publish({"type": "system",
                           "text": "🔧 Обнаружен проект со сборкой — собираю "
                                   "(npm install + build, первый раз может занять минуты)…"})
        entry = await asyncio.to_thread(_build_sync, d["root"], fp)
        if publish:
            if entry["ok"]:
                await publish({"type": "system",
                               "text": f"✅ Сборка прошла за {entry['took_sec']}с — "
                                       f"публикуется {entry['out_dir']}/"})
            else:
                await publish({"type": "system",
                               "text": f"❌ Сборка сайта не прошла: {entry['reason']} — "
                                       f"исполнитель получит лог на доработку"})
        return {**entry, "kind": "build"}


# ─────────────────────────── sync-читатели кеша ───────────────────────────

def published_root() -> str | None:
    """Какую папку хостить/проверять ПРЯМО СЕЙЧАС. static → её корень;
    build с актуальной успешной сборкой → out_dir; build без сборки → None
    (публиковать нечего — исходники Vite-проекта не сайт)."""
    d = detect()
    if d["kind"] == "static":
        return d["root"]
    if d["kind"] != "build":
        return None
    cache = _cache()
    if cache.get("ok") and _cache_fresh(cache, _src_fingerprint(d["root"])):
        return cache.get("out_dir") or None
    return None


def cached_problem() -> dict | None:
    """Структурная проблема сборки для приёмки/критика (sync, из кеша — приёмка
    не имеет права запускать npm). None — сборки не требуется или она актуальна."""
    d = detect()
    if d["kind"] != "build":
        return None
    fp = _src_fingerprint(d["root"])
    cache = _cache()
    if cache.get("ok") and _cache_fresh(cache, fp):
        return None
    if cache and not cache.get("ok") and _cache_fresh(cache, fp):
        reason = cache.get("reason", "сборка не прошла")
        tail = (cache.get("log_tail") or "")[-400:]
        if "отключена оператором" in reason:
            return {"code": "build_disabled", "severity": "critical",
                    "text": "Проект требует сборки (package.json+build), но исполнение сборки "
                            "отключено оператором платформы. Удали package.json/vite.config.js/"
                            "src/*.jsx и перепиши site/index.html в статический HTML/CSS/JS без "
                            "framework/JSX/type=module — раздел «ЕСЛИ СБОРКА ОТКЛЮЧЕНА» в скилле "
                            "«Сайт на React + Vite + Framer Motion» (use_skill за ним же)."}
        return {"code": "build_failed", "severity": "critical",
                "text": f"Сборка сайта не проходит ({reason}). Хвост лога:\n{tail}\n"
                        f"Почини ошибку сборки в исходниках (read_file → write_file)."}
    # Сборка ещё не запускалась для текущих исходников — не критикуем агента,
    # офис соберёт сам на ближайшей публикации/приёмке.
    return {"code": "build_pending", "severity": "cosmetic",
            "text": "Проект со сборкой ещё не собран — офис соберёт при публикации."}


def is_built_output(path: str) -> bool:
    """Файл лежит в выходной папке актуальной сборки (его валидирует сама сборка —
    verify/критик не должны гонять node --check по минифицированным бандлам)."""
    out = (_cache() or {}).get("out_dir") or ""
    return bool(out) and path.startswith(out + "/")


def reset() -> None:
    ctx.delete_file(_CACHE_FILE)
