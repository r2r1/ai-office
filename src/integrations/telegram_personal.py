"""
Личный Telegram-аккаунт (MTProto через Telethon) — в отличие от Bot API
(telegram.py), может НАПИСАТЬ ПЕРВЫМ в ЛС любому пользователю (по @username или
телефону, если Telegram разрешает discovery по номеру). Это то, чего боту не
может Telegram в принципе: бот получает chat_id только от того, кто сам ему
написал первым.

⚠️ Обратная сторона: сообщение уходит от имени РЕАЛЬНОГО аккаунта. Массовая
холодная рассылка триггерит антиспам-эвристики Telegram и может привести к
ограничению аккаунта — это не гипотетический риск, а поведение платформы. Отсюда
намеренное отсутствие "разослать всем" — только одно сообщение одному лиду за раз,
явным действием.

Вход (получение session) — НЕ через обычный cred_fields-флоу (нужен интерактивный
код + опционально 2FA) — см. office/telegram_login.py + /api/integrations/
telegram_personal/login/* в server.py. Здесь только действия над УЖЕ полученной
сессией.
"""

import re

from src.integrations.base import Action, CredField, Integration


def _creds_ok(creds: dict) -> tuple[int, str, str] | None:
    try:
        api_id = int(creds.get("api_id") or 0)
    except ValueError:
        return None
    api_hash = (creds.get("api_hash") or "").strip()
    session = (creds.get("session") or "").strip()
    if not api_id or not api_hash or not session:
        return None
    return api_id, api_hash, session


async def _get_me(creds: dict, params: dict) -> str:
    ok = _creds_ok(creds)
    if not ok:
        return "Нет активной сессии — войдите в «Доступы» (Telegram, личный аккаунт)."
    api_id, api_hash, session = ok
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from src.office.telegram_login import proxy_from_env
    client = TelegramClient(StringSession(session), api_id, api_hash, proxy=proxy_from_env(), connection_retries=2, timeout=10)
    try:
        await client.connect()
    except ConnectionError:
        return "Не удалось подключиться к серверам Telegram — проверьте интернет/прокси."
    try:
        me = await client.get_me()
        return f"Сессия активна: {me.first_name or ''} (@{me.username or '—'}, id={me.id})."
    finally:
        await client.disconnect()


_PHONE_RE = re.compile(r"^\+?\d{10,15}$")


async def _send_dm(creds: dict, params: dict) -> str:
    ok = _creds_ok(creds)
    if not ok:
        return "Нет активной сессии — войдите в «Доступы» (Telegram, личный аккаунт)."
    api_id, api_hash, session = ok
    target = (params.get("target") or "").strip()
    text = (params.get("text") or "").strip()
    if not target or not text:
        return "Нужны target (@username или телефон +7...) и text."

    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon.tl.functions.contacts import ImportContactsRequest
    from telethon.tl.types import InputPhoneContact
    from telethon.errors import FloodWaitError, UserPrivacyRestrictedError
    from src.office.telegram_login import proxy_from_env

    client = TelegramClient(StringSession(session), api_id, api_hash, proxy=proxy_from_env(), connection_retries=2, timeout=10)
    try:
        await client.connect()
    except ConnectionError:
        return "Не удалось подключиться к серверам Telegram — проверьте интернет/прокси."
    try:
        entity = None
        if target.startswith("@"):
            entity = await client.get_entity(target)
        elif _PHONE_RE.match(target.replace(" ", "").replace("-", "")):
            phone = target.replace(" ", "").replace("-", "")
            res = await client(ImportContactsRequest(
                [InputPhoneContact(client_id=0, phone=phone, first_name="Лид", last_name="")]))
            if not res.users:
                return (f"{phone} не найден в Telegram или скрыл поиск по номеру "
                        "(настройки приватности) — напишите через @username или другой канал.")
            entity = res.users[0]
        else:
            return f"«{target}» не похож на @username или телефон — DM в Telegram невозможен."
        await client.send_message(entity, text)
        return f"Сообщение отправлено {target} в личку Telegram."
    except UserPrivacyRestrictedError:
        return f"{target} запретил личные сообщения от незнакомых аккаунтов — DM не доставлено."
    except FloodWaitError as e:
        return f"Telegram просит подождать {e.seconds}с (лимит на новые сообщения) — не повторяй сейчас."
    finally:
        await client.disconnect()


INTEGRATION = Integration(
    name="telegram_personal",
    title="Telegram (личный аккаунт)",
    category="communication",
    icon="👤",
    description=("Пишет ПЕРВЫМ в личные сообщения (в отличие от Bot API, который "
                 "может отвечать только тем, кто сам написал боту). Для follow-up "
                 "с недожатыми лидами."),
    how_to=(
        "Вход НЕ через обычную форму ключа — на вкладке «Доступы» нажми «Войти в Telegram»: "
        "1. Укажи api_id/api_hash (получить на my.telegram.org → API development tools) и номер телефона.\n"
        "2. Введи код, который придёт в Telegram/SMS.\n"
        "3. Если включена двухфакторная защита — введи пароль.\n"
        "⚠️ Это твой РЕАЛЬНЫЙ аккаунт — не рассылай массово, антиспам Telegram "
        "ограничивает аккаунты за холодные рассылки много незнакомцам подряд."
    ),
    cred_fields=[
        CredField(key="phone", label="Номер телефона", secret=False),
        CredField(key="api_id", label="api_id (my.telegram.org)", secret=True),
        CredField(key="api_hash", label="api_hash (my.telegram.org)", secret=True),
        CredField(key="session", label="Сессия (получена при входе)", secret=True),
    ],
    actions={
        "get_me": Action(
            name="get_me",
            description="Проверить, что сессия личного аккаунта активна. Параметры не нужны.",
            handler=_get_me,
        ),
        "send_dm": Action(
            name="send_dm",
            description=("Написать ПЕРВЫМ в личные сообщения конкретному человеку (по @username "
                        "или номеру телефона). Используй для follow-up ОДНОМУ лиду — не для рассылок."),
            handler=_send_dm,
            params={
                "target": {"type": "string", "description": "@username или номер телефона +7..."},
                "text": {"type": "string", "description": "Текст сообщения"},
            },
            required=["target", "text"],
        ),
    },
)
