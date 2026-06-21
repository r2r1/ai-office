"""
Интеграция с почтой через SMTP — отправка писем.

Работает с Gmail (нужен App Password, не обычный пароль),
Yandex, Mail.ru, Outlook и любым SMTP-сервером.

Для Gmail:
  1. Включи двухэтапную аутентификацию в аккаунте Google
  2. myaccount.google.com → Безопасность → Пароли приложений → создай пароль
  3. Вставь email и этот пароль ниже (не обычный пароль!)
"""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from src.integrations.base import Action, CredField, Integration

_SMTP_PRESETS = {
    "gmail.com": ("smtp.gmail.com", 587),
    "googlemail.com": ("smtp.gmail.com", 587),
    "yandex.ru": ("smtp.yandex.ru", 587),
    "ya.ru": ("smtp.yandex.ru", 587),
    "mail.ru": ("smtp.mail.ru", 587),
    "bk.ru": ("smtp.mail.ru", 587),
    "inbox.ru": ("smtp.mail.ru", 587),
    "outlook.com": ("smtp-mail.outlook.com", 587),
    "hotmail.com": ("smtp-mail.outlook.com", 587),
    "live.com": ("smtp-mail.outlook.com", 587),
}


def _smtp_host(email: str, creds: dict) -> tuple[str, int]:
    domain = email.split("@")[-1].lower()
    host = creds.get("smtp_host") or _SMTP_PRESETS.get(domain, ("smtp." + domain, 587))[0]
    port = int(creds.get("smtp_port") or _SMTP_PRESETS.get(domain, ("", 587))[1])
    return host, port


def _creds(creds: dict) -> tuple[str, str]:
    email = (creds.get("email") or creds.get("login") or creds.get("key") or "").strip()
    password = (creds.get("password") or creds.get("app_password") or creds.get("value") or "").strip()
    if not email or not password:
        raise RuntimeError("Нужны email и пароль (для Gmail — App Password из настроек безопасности).")
    return email, password


async def _send_email(creds: dict, params: dict) -> str:
    from_email, password = _creds(creds)
    to = (params.get("to") or "").strip()
    subject = (params.get("subject") or "(без темы)").strip()
    body = (params.get("body") or "").strip()
    html = (params.get("html") or "").strip()
    cc = (params.get("cc") or "").strip()
    if not to:
        raise RuntimeError("Нужен получатель 'to'.")

    msg = MIMEMultipart("alternative")
    msg["From"] = from_email
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc

    if html:
        msg.attach(MIMEText(body or html, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))
    else:
        msg.attach(MIMEText(body, "plain", "utf-8"))

    host, port = _smtp_host(from_email, creds)
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(from_email, password)
            recipients = [to] + ([cc] if cc else [])
            server.sendmail(from_email, recipients, msg.as_string())
        return f"✅ Письмо отправлено на {to}. Тема: «{subject}»"
    except smtplib.SMTPAuthenticationError:
        raise RuntimeError(
            "Ошибка авторизации. Для Gmail нужен App Password (не обычный пароль) — "
            "создай на myaccount.google.com → Безопасность → Пароли приложений."
        )
    except smtplib.SMTPException as e:
        raise RuntimeError(f"SMTP ошибка: {e}")


async def _check_connection(creds: dict, params: dict) -> str:
    email, password = _creds(creds)
    host, port = _smtp_host(email, creds)
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(email, password)
        return f"✅ Подключение работает. Аккаунт: {email} (сервер: {host}:{port})"
    except smtplib.SMTPAuthenticationError:
        raise RuntimeError(
            "Ошибка авторизации. Для Gmail нужен App Password — "
            "myaccount.google.com → Безопасность → Пароли приложений."
        )
    except Exception as e:
        raise RuntimeError(f"Не удалось подключиться к {host}:{port}: {e}")


INTEGRATION = Integration(
    name="gmail",
    title="Почта (Email/SMTP)",
    icon="📧",
    description="Отправка писем через Gmail, Яндекс.Почту, Mail.ru или любой SMTP-сервер.",
    how_to=(
        "Для Gmail:\n"
        "1. Включи двухэтапную аутентификацию: myaccount.google.com → Безопасность\n"
        "2. Создай пароль приложения: myaccount.google.com → Безопасность → Пароли приложений\n"
        "3. Введи свой Gmail и полученный 16-символьный пароль приложения\n\n"
        "Для Яндекс: включи IMAP в настройках почты, используй обычный пароль или пароль приложения.\n"
        "Для корпоративной почты: уточни SMTP-хост и порт у провайдера."
    ),
    cred_fields=[
        CredField(key="email", label="Email адрес (от кого)", secret=False),
        CredField(key="password", label="Пароль (для Gmail — App Password)", secret=True),
        CredField(key="smtp_host", label="SMTP сервер (оставь пустым для авто)", secret=False),
        CredField(key="smtp_port", label="Порт (оставь пустым для авто, обычно 587)", secret=False),
    ],
    actions={
        "check": Action(
            name="check",
            description="Проверить подключение к почтовому серверу.",
            handler=_check_connection,
        ),
        "send_email": Action(
            name="send_email",
            description="Отправить письмо на email адрес.",
            handler=_send_email,
            params={
                "to": {"type": "string", "description": "Email получателя"},
                "subject": {"type": "string", "description": "Тема письма"},
                "body": {"type": "string", "description": "Текст письма (plain text)"},
                "html": {"type": "string", "description": "HTML-версия письма (опционально)"},
                "cc": {"type": "string", "description": "Копия (CC), опционально"},
            },
            required=["to", "subject", "body"],
        ),
    },
)
