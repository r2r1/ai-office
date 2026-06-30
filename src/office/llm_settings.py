"""
Персональные настройки доступа к LLM у каждого тенанта: свой API-ключ, base_url
и модель по умолчанию. Ключ хранится зашифрованным (saas/crypto).

Если у тенанта ключ не задан — используется общий ключ оператора из .env
(LLM_API_KEY/LLM_BASE_URL) как fallback (удобно для демо/первого запуска).
"""

import os

from dotenv import load_dotenv

from src.saas import context as ctx
from src.saas import crypto

load_dotenv()

_FILE = "llm.json"

ENV_BASE_URL = os.getenv("LLM_BASE_URL", "https://apinet.cloud/v1")
ENV_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("ANTHROPIC_API_KEY", "")


def _cfg() -> dict:
    return ctx.read_json(_FILE, {})


def set_settings(base_url: str = "", api_key: str = "") -> None:
    cfg = _cfg()
    if base_url is not None and base_url.strip():
        cfg["base_url"] = base_url.strip()
    if api_key and api_key.strip():
        cfg["api_key_enc"] = crypto.encrypt(api_key.strip())
    ctx.write_json(_FILE, cfg)


def clear_key() -> None:
    cfg = _cfg()
    cfg.pop("api_key_enc", None)
    ctx.write_json(_FILE, cfg)


def has_own_key() -> bool:
    return bool(_cfg().get("api_key_enc"))


def credentials() -> tuple[str, str]:
    """(base_url, api_key) для вызова LLM. Свои настройки тенанта или fallback на .env."""
    cfg = _cfg()
    base_url = cfg.get("base_url") or ENV_BASE_URL
    api_key = crypto.decrypt(cfg.get("api_key_enc", "")) if cfg.get("api_key_enc") else ENV_API_KEY
    return base_url, api_key


def provision_tenant_key(tenant_id: str, name: str = "") -> dict:
    """
    Выдаёт тенанту СВОЙ apinet-ключ с лимитом квоты (изоляция расхода).
    Работает только если заданы APINET_ACCESS_TOKEN/USER_ID — иначе пропускает
    (тенант продолжит использовать общий ключ оператора из .env).
    Безопасно вызывать при создании workspace.
    """
    from src.saas import apinet
    if not apinet.is_configured():
        return {"ok": False, "skipped": "apinet creds не заданы"}

    prev = ctx.get_tenant()
    ctx.set_tenant(tenant_id)
    try:
        if has_own_key():
            return {"ok": True, "reused": True}
        res = apinet.create_token(name or f"office-{tenant_id}")
        if res.get("ok") and res.get("key"):
            set_settings(ENV_BASE_URL, res["key"])
            return {"ok": True, "key_id": res.get("id"), "reused": res.get("reused", False)}
        return {"ok": False, "message": res.get("message", "не удалось создать ключ")}
    finally:
        ctx.set_tenant(prev)


def public() -> dict:
    """Для UI: без открытого ключа."""
    cfg = _cfg()
    key = crypto.decrypt(cfg.get("api_key_enc", "")) if cfg.get("api_key_enc") else ""
    return {
        "base_url": cfg.get("base_url") or ENV_BASE_URL,
        "has_own_key": bool(cfg.get("api_key_enc")),
        "key_mask": crypto.mask(key) if key else "",
        "using_shared": not bool(cfg.get("api_key_enc")),
    }
