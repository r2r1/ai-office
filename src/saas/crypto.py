"""
Шифрование секретов at-rest (Fernet/AES). Ключ выводится из APP_SECRET.

Используется для API-ключей пользователей (LLM-ключ, креды интеграций), чтобы они
не лежали на диске открытым текстом. ВАЖНО: при смене APP_SECRET старые секреты
не расшифруются — задайте стабильный APP_SECRET в .env на проде.
"""

import base64
import hashlib
import os
import sys

from cryptography.fernet import Fernet, InvalidToken

_PREFIX = "enc::"
_INSECURE_DEFAULT = "dev-insecure-change-me"
_warned = False


def require_app_secret() -> str:
    """Единая точка резолва APP_SECRET для всего процесса (auth.py и crypto.py
    используют её же). Раньше оба модуля независимо подставляли захардкоженный
    дефолт при отсутствии переменной — сервер тихо стартовал в проде без секрета,
    и все сессии/шифрование at-rest оказывались на известном всем ключе. Теперь
    без APP_SECRET процесс падает при старте, если явно не включён DEV_MODE."""
    global _warned
    secret = os.getenv("APP_SECRET", "")
    if secret:
        return secret
    if os.getenv("DEV_MODE", "0") == "1":
        if not _warned:
            print("⚠️  APP_SECRET не задан — используется НЕБЕЗОПАСНЫЙ dev-ключ "
                  "(DEV_MODE=1). Все сессии/шифрование предсказуемы. "
                  "НЕ используйте это на проде.", file=sys.stderr)
            _warned = True
        return _INSECURE_DEFAULT
    raise RuntimeError(
        "APP_SECRET не задан. Укажите длинную случайную строку в .env "
        "(например: APP_SECRET=$(openssl rand -hex 32)) — иначе все сессии "
        "подделываемы, а зашифрованные креды тенантов читаемы известным ключом. "
        "Для локальной разработки без секрета явно выставьте DEV_MODE=1."
    )


def _fernet() -> Fernet:
    secret = require_app_secret()
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
