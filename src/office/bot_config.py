"""
Конфигурация Telegram-бота клиента (по тенанту).
Файл: data/tenants/<tid>/bot_config.json.

Движок бота один на всю платформу (bot_engine.py), а ПОВЕДЕНИЕ у каждого клиента своё —
оно задаётся этим конфигом + собственным токеном. Это как Tilda: один конструктор, но
у каждого сайт/бот свой за счёт настроек.
"""

import secrets

from src.saas import context as ctx
from src.office import connections

_FILE = "bot_config.json"

_DEFAULTS = {
    "enabled": False,            # запущен ли бот (выставлен webhook)
    "kind": "booking",           # тип сценария (пока один — запись клиентов)
    "title": "",                 # как бот представляется
    "greeting": "Здравствуйте! Я помогу вам записаться. Выберите услугу:",
    "services": [],              # список услуг (кнопки)
    "ask_fields": ["Имя", "Телефон"],   # какие поля собрать после выбора услуги
    "success_message": "Спасибо! Ваша заявка принята — мы скоро свяжемся с вами. ✅",
    "working_hours": "",         # справочно, показывается в приветствии если задано
    "lead_slug": "telegram-bot", # под каким slug писать лиды (вкладка «Лиды»)
    "webhook_secret": "",        # секрет в URL вебхука
    "bot_username": "",          # @username бота (для ссылок)
}


def get() -> dict:
    """Конфиг тенанта поверх дефолтов."""
    saved = ctx.read_json(_FILE, {})
    return {**_DEFAULTS, **saved}


def update(patch: dict) -> dict:
    cfg = get()
    cfg.update({k: v for k, v in patch.items() if k in _DEFAULTS})
    ctx.write_json(_FILE, cfg)
    return cfg


def set_enabled(enabled: bool) -> None:
    update({"enabled": enabled})


def ensure_secret() -> str:
    """Гарантирует наличие webhook-секрета, генерирует при первом запуске."""
    cfg = get()
    if not cfg.get("webhook_secret"):
        cfg = update({"webhook_secret": secrets.token_urlsafe(16)})
    return cfg["webhook_secret"]


def resolve_token() -> str:
    """
    Токен бота: из подключения Telegram (приоритет — там его сохраняет интегратор),
    иначе пусто. Конфиг сам токен не хранит (он в connections, шифруется at-rest).
    """
    conn = connections.get_by_name("telegram") or connections.get_by_name("Telegram")
    if conn:
        f = conn.get("fields", {})
        return (f.get("token") or f.get("key") or f.get("value") or "").strip()
    return ""


def reset() -> None:
    ctx.delete_file(_FILE)
