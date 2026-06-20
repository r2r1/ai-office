"""
Контекст тенанта + персистентность по тенанту.

Текущий тенант хранится в ContextVar (устанавливается middleware на каждый
HTTP-запрос и офис-задачей на каждый цикл). Все данные офиса лежат в
`data/tenants/<tenant_id>/<name>.json` — это и есть изоляция.

Модули офиса делают свои функции stateless: читают/пишут файл текущего тенанта,
без глобального состояния в памяти (нет утечки между клиентами).
"""

import contextvars
import json
from pathlib import Path

_tenant: contextvars.ContextVar[str] = contextvars.ContextVar("tenant", default="default")

ROOT = Path("data/tenants")


def set_tenant(tid: str) -> None:
    _tenant.set(tid or "default")


def get_tenant() -> str:
    return _tenant.get()


def tenant_dir() -> Path:
    p = ROOT / get_tenant()
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_json(name: str, default):
    f = tenant_dir() / name
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return default
    return default


def write_json(name: str, obj) -> None:
    f = tenant_dir() / name
    f.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def delete_file(name: str) -> None:
    f = tenant_dir() / name
    if f.exists():
        f.unlink()


def wipe() -> None:
    """Полностью удаляет данные текущего тенанта (reset «новый клиент»)."""
    import shutil
    d = ROOT / get_tenant()
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
