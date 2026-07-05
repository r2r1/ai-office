"""
Интеграция с Gmail через Gmail API + Google OAuth 2.0.

Авторизация: нажми «Подключить Google» в разделе Доступы.
Использует Gmail REST API (не SMTP) — работает даже без App Password.

Действия: отправка писем, чтение входящих, поиск по почте.
"""

import base64
import email as email_lib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

from src.integrations.base import Action, CredField, Integration
from src.integrations import google_oauth

_API = "https://gmail.googleapis.com/gmail/v1/users/me"


def _build_raw_message(from_email: str, to: str, subject: str, body: str,
                        html: str = "", cc: str = "") -> str:
    """Собирает RFC 2822 письмо и кодирует в base64url для Gmail API."""
    msg = MIMEMultipart("alternative")
    msg["From"]    = from_email
    msg["To"]      = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc
    if html:
        msg.attach(MIMEText(body or html, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))
    else:
        msg.attach(MIMEText(body, "plain", "utf-8"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return raw


async def _get_profile(creds: dict, params: dict) -> str:
    """Показывает подключённый аккаунт Gmail и его статистику."""
    token = await google_oauth.get_valid_token()
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{_API}/profile",
                             headers={"Authorization": f"Bearer {token}"})
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))
    addr    = data.get("emailAddress", "?")
    total   = data.get("messagesTotal", "?")
    threads = data.get("threadsTotal", "?")
    return (f"✅ Подключён аккаунт: {addr}\n"
            f"Писем: {total}, веток: {threads}")


async def _send_email(creds: dict, params: dict) -> str:
    token      = await google_oauth.get_valid_token()
    to         = (params.get("to") or "").strip()
    subject    = (params.get("subject") or "(без темы)").strip()
    body       = (params.get("body") or "").strip()
    html       = (params.get("html") or "").strip()
    cc         = (params.get("cc") or "").strip()
    from_alias = (params.get("from_name") or "").strip()

    if not to:
        raise RuntimeError("Нужен получатель 'to'.")

    # Узнаём email отправителя
    async with httpx.AsyncClient(timeout=10) as client:
        pr = await client.get(f"{_API}/profile",
                              headers={"Authorization": f"Bearer {token}"})
    from_email = pr.json().get("emailAddress", "me")
    if from_alias:
        from_email = f"{from_alias} <{from_email}>"

    raw = _build_raw_message(from_email, to, subject, body, html, cc)

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{_API}/messages/send",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"raw": raw},
        )
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))
    return f"✅ Письмо отправлено на {to}. Тема: «{subject}» (id: {data.get('id')})"


async def _list_emails(creds: dict, params: dict) -> str:
    token      = await google_oauth.get_valid_token()
    query      = (params.get("query") or "in:inbox").strip()
    max_res    = int(params.get("max_results") or 10)

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            f"{_API}/messages",
            headers={"Authorization": f"Bearer {token}"},
            params={"q": query, "maxResults": max_res},
        )
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))

    messages = data.get("messages", [])
    if not messages:
        return f"Нет писем по запросу «{query}»."

    lines = []
    async with httpx.AsyncClient(timeout=20) as client:
        for m in messages[:max_res]:
            detail = await client.get(
                f"{_API}/messages/{m['id']}",
                headers={"Authorization": f"Bearer {token}"},
                params={"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]},
            )
            d    = detail.json()
            hdrs = {h["name"]: h["value"] for h in d.get("payload", {}).get("headers", [])}
            subj = hdrs.get("Subject", "(без темы)")
            frm  = hdrs.get("From", "?")
            date = hdrs.get("Date", "?")[:25]
            lines.append(f"• [{date}] {frm[:30]} — {subj[:50]}")

    return f"Письма ({len(messages)}):\n" + "\n".join(lines)


async def _read_email(creds: dict, params: dict) -> str:
    token    = await google_oauth.get_valid_token()
    msg_id   = (params.get("message_id") or "").strip()
    if not msg_id:
        raise RuntimeError("Нужен message_id (из list_emails).")

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            f"{_API}/messages/{msg_id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"format": "full"},
        )
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))

    hdrs    = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
    subject = hdrs.get("Subject", "(без темы)")
    frm     = hdrs.get("From", "?")
    date    = hdrs.get("Date", "?")

    # Извлекаем текст из payload
    def _get_text(part: dict) -> str:
        mime = part.get("mimeType", "")
        body = part.get("body", {})
        if mime in ("text/plain", "text/html") and body.get("data"):
            try:
                return base64.urlsafe_b64decode(body["data"] + "==").decode("utf-8", errors="replace")
            except Exception:
                return ""
        for p in part.get("parts", []):
            t = _get_text(p)
            if t:
                return t
        return ""

    text = _get_text(data.get("payload", {}))
    preview = text[:1500].strip() if text else "(нет текстового контента)"
    return (f"От: {frm}\nДата: {date}\nТема: {subject}\n\n{preview}")


async def _delete_email(creds: dict, params: dict) -> str:
    token  = await google_oauth.get_valid_token()
    msg_id = (params.get("message_id") or "").strip()
    if not msg_id:
        raise RuntimeError("Нужен message_id.")
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.delete(
            f"{_API}/messages/{msg_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
    if r.status_code in (200, 204):
        return f"✅ Письмо {msg_id} удалено."
    try:
        err = r.json().get("error", {}).get("message", "Ошибка")
    except Exception:
        err = f"HTTP {r.status_code}"
    raise RuntimeError(err)


INTEGRATION = Integration(
    name="gmail",
    title="Gmail",
    category="communication",
    icon="📧",
    description="Отправка и чтение писем через Gmail API. Авторизация через Google OAuth.",
    how_to="Нажми «Подключить Google» — это даёт доступ сразу к Gmail, Sheets и Calendar.",
    cred_fields=[],      # OAuth — поля вводить не нужно
    oauth_url="/auth/google/start",
    actions={
        "get_profile": Action(
            name="get_profile",
            description="Проверить подключённый Gmail-аккаунт.",
            handler=_get_profile,
        ),
        "send_email": Action(
            name="send_email",
            description="Отправить письмо через Gmail.",
            handler=_send_email,
            params={
                "to":        {"type": "string", "description": "Email получателя"},
                "subject":   {"type": "string", "description": "Тема письма"},
                "body":      {"type": "string", "description": "Текст письма (plain text)"},
                "html":      {"type": "string", "description": "HTML-версия (опционально)"},
                "cc":        {"type": "string", "description": "Копия CC (опционально)"},
                "from_name": {"type": "string", "description": "Имя отправителя (опционально)"},
            },
            required=["to", "subject", "body"],
        ),
        "list_emails": Action(
            name="list_emails",
            description="Получить список писем из Gmail. Поддерживает поиск.",
            handler=_list_emails,
            params={
                "query":       {"type": "string",  "description": "Поисковый запрос Gmail (default: in:inbox). Примеры: 'from:boss@co.ru', 'is:unread', 'subject:счёт'"},
                "max_results": {"type": "integer", "description": "Максимум писем (default: 10, max: 50)"},
            },
        ),
        "read_email": Action(
            name="read_email",
            description="Прочитать содержимое письма по его ID.",
            handler=_read_email,
            params={
                "message_id": {"type": "string", "description": "ID письма (из list_emails)"},
            },
            required=["message_id"],
        ),
        "delete_email": Action(
            name="delete_email",
            description="Удалить письмо из Gmail.",
            handler=_delete_email,
            params={
                "message_id": {"type": "string", "description": "ID письма"},
            },
            required=["message_id"],
        ),
    },
)
