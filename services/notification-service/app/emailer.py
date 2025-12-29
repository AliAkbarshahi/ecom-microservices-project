from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Optional


def _bool_env(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


SMTP_HOST = os.getenv("SMTP_HOST", "mailhog")
SMTP_PORT = int(os.getenv("SMTP_PORT", "1025"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "no-reply@example.com")
SMTP_USE_TLS = _bool_env("SMTP_USE_TLS", False)

# If set, all notifications will be sent to this address (useful for testing)
NOTIFY_FORCE_TO = os.getenv("NOTIFY_FORCE_TO", "").strip()
# If user's email is missing, fallback to this
NOTIFY_FALLBACK_TO = os.getenv("NOTIFY_FALLBACK_TO", "test@example.com").strip()


def send_email(*, to_email: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
        if SMTP_USE_TLS:
            server.starttls()
        if SMTP_USERNAME and SMTP_PASSWORD:
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(msg)


def pick_recipient(user_email: Optional[str]) -> str:
    if NOTIFY_FORCE_TO:
        return NOTIFY_FORCE_TO
    if user_email and user_email.strip():
        return user_email.strip()
    return NOTIFY_FALLBACK_TO
