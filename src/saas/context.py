"""
Контекст тенанта + персистентность по тенанту.

Текущий тенант хранится в ContextVar (устанавливается middleware на каждый
HTTP-запрос и офис-задачей на каждый цикл). Все данные офиса лежат в
`data/tenants/<tenant_id>/<name>.json` — это и есть изоляция.

Модули офиса делают свои функции stateless: читают/пишут файл текущего тенанта,
без глобального состояния в памяти (нет утечки между клиентами).
"""

import asyncio
import contextvars
import copy
import itertools
import json
import os
import time
from pathlib import Path

_tenant: contextvars.ContextVar[str] = contextvars.ContextVar("tenant", default="default")
_tmp_seq = itertools.count()  # уникальный суффикс временного файла в write_json()

# Локи per (tenant, filename): страховка на будущее. Сегодня все read-modify-write
# функции офиса (plan.py, state.py и т.п.) синхронны от _data() до _save() — без
# await внутри — и потому атомарны под однопоточным asyncio без явных локов. Но
# это неявный инвариант, не гарантия: один случайно добавленный await внутри такой
# функции тихо откроет гонку (A читает → B читает тот же снапшот → A пишет → B
# затирает A). locked() делает эту гарантию явной и переживёт будущий рефакторинг.
_locks: dict[tuple[str, str], asyncio.Lock] = {}


def locked(name: str):
    """Async context manager: `async with ctx.locked("plan.json"): ...read-modify-write...`
    Оборачивает произвольный блок кода локом по (tenant, filename) — используйте
    вокруг read-modify-write, который содержит await между чтением и записью."""
    key = _cache_key(name)
    lock = _locks.setdefault(key, asyncio.Lock())
    return lock

ROOT = Path("data/tenants")

# Процессный кеш прочитанных JSON-файлов: (tenant_id, filename) -> распарсенные данные.
# Однопроцессный uvicorn (не multi-worker) — безопасно: нет другого процесса,
# который менял бы файлы мимо write_json/delete_file. Каждое чтение с кеш-хитом
# возвращает copy.deepcopy — вызывающий код сегодня получает от read_json НЕЗАВИСИМЫЙ
# объект на каждый вызов (json.loads создаёт новый), и это поведение нельзя менять:
# иначе два async-таска для одного тенанта могли бы держать ссылки на ОДИН и тот же
# мутируемый dict и потерять правки друг друга между await-точками.
_cache: dict[tuple[str, str], object] = {}


def _cache_key(name: str) -> tuple[str, str]:
    return (get_tenant(), name)


def set_tenant(tid: str) -> None:
    _tenant.set(tid or "default")


def get_tenant() -> str:
    return _tenant.get()


def tenant_dir() -> Path:
    p = ROOT / get_tenant()
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_json(name: str, default):
    key = _cache_key(name)
    if key in _cache:
        return copy.deepcopy(_cache[key])
    f = tenant_dir() / name
    if f.exists():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            # Битый JSON НЕ подменяем дефолтом молча (раньше офис «забывал всё» и
            # тихо генерировал план заново): файл уходит в карантин рядом, а в лог —
            # громкое предупреждение. Данные можно восстановить руками из карантина.
            try:
                q = f.with_name(f"{name}.broken-{int(time.time())}")
                f.rename(q)
                print(f"[context] ПОВРЕЖДЁН {f} — перемещён в карантин: {q.name}")
            except OSError:
                pass
            return default
        except OSError:
            return default
        _cache[key] = data
        return copy.deepcopy(data)
    # Файла ещё нет — НЕ кешируем отсутствие: разные вызовы могут передавать
    # разный default для одного имени файла, а после первой write_json кеш
    # заполнится сам и дальнейшие read_json станут кеш-хитами.
    return default


def write_json(name: str, obj) -> None:
    # Атомарная запись: tmp + os.replace. Прямой write_text оставлял битый файл,
    # если процесс убивали посреди записи, — и офис тенанта молча терял состояние.
    #
    # `tmp` — с уникальным суффиксом (pid + монотонный счётчик), а не общим
    # "<name>.tmp": два почти одновременных вызова write_json для ОДНОГО и того
    # же файла (например шквал POST /api/dashboard/reorder при перетаскивании
    # виджета — реальный кейс) иначе пишут в один и тот же временный файл и
    # гонятся за одним os.replace — на Windows это валится PermissionError
    # ([WinError 5], в отличие от POSIX rename там нет atomic-семантики поверх
    # уже открытого/переименовываемого файла). С уникальным tmp гонки в записи
    # не будет, останется только гонка «кто последний перезапишет f» — она
    # безобидна (последняя запись побеждает, как и раньше).
    f = tenant_dir() / name
    tmp = f.with_name(f"{name}.{os.getpid()}.{next(_tmp_seq)}.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    # os.replace на Windows иногда транзиторно падает PermissionError, если
    # другой процесс/хендл на долю секунды держит f открытым (антивирус,
    # почти одновременное чтение) — короткий ретрай вместо падения запроса.
    #
    # Реальный найденный баг (аудит масштабирования 2026-07-18): раньше здесь
    # был `time.sleep()` между попытками — эта функция синхронная и вызывается
    # из асинхронного кода (office/loop.py и др.) БЕЗ asyncio.to_thread, так
    # что sleep блокировал ВЕСЬ event loop процесса (до 0.75с суммарно на 5
    # попыток) — при множестве параллельных тенантов на одном процессе это
    # останавливало вообще всех, не только того, у кого случилась коллизия.
    # Полный асинхронный I/O здесь не сделан осознанно: read_json/write_json
    # вызываются синхронно из ~50 файлов office/* без единого await между
    # чтением и записью — это и есть их атомарность (см. докстринг модуля);
    # перевод в async потребовал бы протащить await через весь этот граф и
    # разрушил бы инвариант, а не просто ускорил запись. Ретрай БЕЗ сна —
    # коллизия транзиторная (доли миллисекунды), немедленная повторная
    # попытка почти всегда успевает застать хендл уже отпущенным; если нет —
    # последняя попытка честно падает, как и раньше.
    for attempt in range(5):
        try:
            os.replace(tmp, f)
            break
        except PermissionError:
            if attempt == 4:
                tmp.unlink(missing_ok=True)
                raise
    _cache[_cache_key(name)] = copy.deepcopy(obj)


def delete_file(name: str) -> None:
    _cache.pop(_cache_key(name), None)
    f = tenant_dir() / name
    if f.exists():
        f.unlink()


def wipe() -> None:
    """Полностью удаляет данные текущего тенанта (reset «новый клиент»)."""
    import shutil
    tid = get_tenant()
    for k in [k for k in _cache if k[0] == tid]:
        _cache.pop(k, None)
    d = ROOT / tid
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
