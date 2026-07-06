"""
Шифрование секретов at-rest (Fernet/AES). Ключ выводится из APP_SECRET.

Используется для API-ключей пользователей (LLM-ключ, креды интеграций), чтобы они
не лежали на диске открытым текстом. Задайте стабильный APP_SECRET в .env на проде.

Ротация секрета: смена APP_SECRET раньше НАВСЕГДА делала нечитаемыми все уже
зашифрованные значения — без пути восстановления (docs/audit-dd-2026-07-06.md
§9/§19 п.9). Теперь decrypt() при неудаче с текущим ключом пробует ключи из
APP_SECRET_PREVIOUS (через запятую, старые значения APP_SECRET) — это позволяет
плавно перейти на новый секрет: задать новый APP_SECRET, старый положить в
APP_SECRET_PREVIOUS, прогнать `scripts/rotate_secret.py` (перешифровывает все
креды всех тенантов новым ключом), затем убрать APP_SECRET_PREVIOUS.
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


def _key_for(secret: str) -> bytes:
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())


def _fernet(secret: str | None = None) -> Fernet:
    return Fernet(_key_for(secret if secret is not None else require_app_secret()))


def _previous_secrets() -> list[str]:
    raw = os.getenv("APP_SECRET_PREVIOUS", "")
    return [s.strip() for s in raw.split(",") if s.strip()]


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
    raw = value[len(_PREFIX):].encode("utf-8")
    try:
        return _fernet().decrypt(raw).decode("utf-8")
    except (InvalidToken, ValueError):
        pass
    # Текущий APP_SECRET не подошёл — пробуем ключи ротации (APP_SECRET_PREVIOUS),
    # чтобы значения, зашифрованные ДО ротации, не терялись безвозвратно.
    for old_secret in _previous_secrets():
        try:
            return _fernet(old_secret).decrypt(raw).decode("utf-8")
        except (InvalidToken, ValueError):
            continue
    return ""


def mask(plain: str) -> str:
    """Маска для показа в UI: последние 4 символа."""
    if not plain:
        return ""
    s = str(plain)
    return ("•" * max(0, len(s) - 4)) + s[-4:] if len(s) > 4 else "••••"
