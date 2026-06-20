"""
Шифрование секретов at-rest (Fernet/AES). Ключ выводится из APP_SECRET.

Используется для API-ключей пользователей (LLM-ключ, креды интеграций), чтобы они
не лежали на диске открытым текстом. ВАЖНО: при смене APP_SECRET старые секреты
не расшифруются — задайте стабильный APP_SECRET в .env на проде.
"""

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

_PREFIX = "enc::"


def _fernet() -> Fernet:
    secret = os.getenv("APP_SECRET", "dev-insecure-change-me")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def encrypt(plain: str) -> str:
    if plain is None:
        return ""
    token = _fernet().encrypt(str(plain).encode("utf-8")).decode("utf-8")
    return _PREFIX + token


def decrypt(value: str) -> str:
    if not value:
        return ""
    if not value.startswith(_PREFIX):
        return value  # совместимость со старыми незашифрованными значениями
    try:
        return _fernet().decrypt(value[len(_PREFIX):].encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""


def mask(plain: str) -> str:
    """Маска для показа в UI: последние 4 символа."""
    if not plain:
        return ""
    s = str(plain)
    return ("•" * max(0, len(s) - 4)) + s[-4:] if len(s) > 4 else "••••"
