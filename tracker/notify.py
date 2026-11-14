"""Send run reports and price-drop alerts to every configured channel (email, Telegram).

Messages are written in Telegram's small HTML subset (<b>, <i>, <a>, newlines), which is
also valid HTML for email. With no channel configured, the message is only written to
logs/notify_preview.txt, so the pipeline still runs end to end.
"""
from __future__ import annotations

import html
import logging
import re
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from . import telegram
from .config import settings

log = logging.getLogger("tracker.notify")


def email_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_user and settings.email_to)


def configured() -> bool:
    return email_configured() or telegram.configured()


def send(text: str, subject: str, attachments: list[Path] | None = None) -> bool:
    """True if at least one channel accepted the message."""
    if not configured():
        settings.log_dir.mkdir(parents=True, exist_ok=True)
        with open(settings.log_dir / "notify_preview.txt", "a", encoding="utf-8") as f:
            f.write(f"Subject: {subject}\n\n{text}\n\n" + "-" * 40 + "\n\n")
        log.info("no notification channel configured; message written to logs/notify_preview.txt")
        return False
    sent = []
    if email_configured():
        sent.append(send_email(text, subject, attachments or []))
    if telegram.configured():
        sent.append(telegram.send(text))
    return any(sent)


def to_plain(text: str) -> str:
    text = re.sub(r'<a href="([^"]+)">([^<]*)</a>', r"\2: \1", text)
    return html.unescape(re.sub(r"<[^>]+>", "", text))


def send_email(text: str, subject: str, attachments: list[Path]) -> bool:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.email_from or settings.smtp_user
    msg["To"] = ", ".join(settings.email_to)
    msg.set_content(to_plain(text))
    msg.add_alternative(
        '<div style="font-family:system-ui,sans-serif;font-size:14px;line-height:1.5;'
        f'white-space:pre-line">{text}</div>', subtype="html")
    for path in attachments:
        if path.exists():
            msg.add_attachment(path.read_bytes(), filename=path.name, maintype="application",
                               subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    for attempt in range(3):
        try:
            if settings.smtp_port == 465:
                server = smtplib.SMTP_SSL(settings.smtp_host, 465, timeout=30,
                                          context=ssl.create_default_context())
            else:
                server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30)
                server.starttls(context=ssl.create_default_context())
            with server:
                server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)
            return True
        except (smtplib.SMTPException, OSError) as exc:
            log.warning("email send failed (%s), attempt %d/3", exc, attempt + 1)
    return False
