from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

import settings

LOGGER = logging.getLogger(__name__)


def _send_smtp(to_email: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = settings.EMAIL_FROM
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as client:
        if settings.SMTP_USE_TLS:
            client.starttls()
        if settings.SMTP_USERNAME:
            client.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        client.send_message(message)


async def send_auth_email(to_email: str, subject: str, body: str) -> None:
    if settings.AUTH_EMAIL_MODE == "log":
        LOGGER.info("Auth email for %s: %s\n%s", to_email, subject, body)
        return
    if settings.AUTH_EMAIL_MODE != "smtp" or not settings.SMTP_HOST or not settings.EMAIL_FROM:
        raise RuntimeError("Auth email delivery is not configured")
    await asyncio.to_thread(_send_smtp, to_email, subject, body)