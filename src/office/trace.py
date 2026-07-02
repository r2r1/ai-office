"""
Детальный системный трейс офиса — по тенанту (data/tenants/<tid>/trace.jsonl).

В отличие от «ленты событий» (`state.py`, только пользовательские типы без времени),
это ТЕХНИЧЕСКИЙ журнал: каждая запись с точным временем (мс) и всеми деталями —
кто кому передал задачу, какой инструмent вызвал, с какими аргументами, сколько
занял, какой моделью, сколько токенов, что опубликовал, вердикт критика и т.д.
Нужен для отладки: «что именно, когда и куда» произошло внутри системы.

Хранилище — построчный JSONL (append-friendly, устойчив к обрыву), с усечением
до MAX_LINES. Точка входа одна — `log(kind, **fields)`; читатели — `tail`, `as_text`.
"""

import json
import time
from datetime import datetime

from src.saas import context as ctx

_FILE = "trace.jsonl"
MAX_LINES = 4000  # ~последние N системных записей на тенанта


def _path():
    return ctx.tenant_dir() / _FILE


def _read_raw() -> str:
    try:
        p = _path()
        if p.exists():
            return p.read_text(encoding="utf-8")
    except Exception:
        pass
    return ""


def _append_raw(line: str) -> None:
    try:
        with open(_path(), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        # Трейс не должен ронять офис: молча пропускаем сбой записи.
        pass


_MAX_BYTES = 3_000_000  # ~3 МБ на тенант; при превышении оставляем последние MAX_LINES


def _truncate_if_needed() -> None:
    # Дёшево: смотрим РАЗМЕР файла (os.stat), а не читаем его целиком на каждой проверке.
    try:
        p = _path()
        if not p.exists() or p.stat().st_size < _MAX_BYTES:
            return
        keep = p.read_text(encoding="utf-8").splitlines()[-MAX_LINES:]
        p.write_text("\n".join(keep) + "\n", encoding="utf-8")
    except Exception:
        pass


def log(event_kind: str, **fields) -> None:
    """
    Пишет одну запись трейса. `event_kind` — категория (assign / agent_start / tool /
    publish / critic / …). Остальное — произвольные поля детали. Имя первого параметра
    НАРОЧНО необычное (event_kind, а не kind): вызывающие передают его позиционно, а
    любые **fields (в т.ч. с ключом 'kind') больше не могут с ним столкнуться.
    Значения обрезаются, чтобы огромные HTML/ответы не раздували журнал.
    """
    now = time.time()
    entry: dict = {
        "ts": datetime.now().strftime("%H:%M:%S.") + f"{int((now % 1) * 1000):03d}",
        "t": round(now, 3),
        "kind": event_kind,
    }
    for k, v in fields.items():
        if isinstance(v, str) and len(v) > 400:
            v = v[:400] + f"…(+{len(v) - 400})"
        entry[k] = v
    try:
        _append_raw(json.dumps(entry, ensure_ascii=False))
    except Exception:
        return
    # Периодическое усечение (дёшево: только при переполнении).
    if now % 1 < 0.02:
        _truncate_if_needed()


def tail(n: int = 300) -> list[dict]:
    out: list[dict] = []
    for ln in _read_raw().splitlines()[-n:]:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def as_text(n: int = 1500) -> str:
    """Плоский человекочитаемый вид для текстового экспорта лога."""
    lines = []
    for e in tail(n):
        kind = e.get("kind", "")
        rest = {k: v for k, v in e.items() if k not in ("ts", "t", "kind")}
        detail = "  ".join(f"{k}={v}" for k, v in rest.items())
        lines.append(f"  [{e.get('ts','')}] {kind:<12} {detail}")
    return "\n".join(lines)


def reset() -> None:
    try:
        ctx.delete_file(_FILE)
    except Exception:
        pass
