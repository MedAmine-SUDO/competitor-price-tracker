"""Send messages to a Telegram chat through the Bot API.

Without TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID the message is only logged and written to
logs/telegram_preview.txt, so the pipeline still runs end to end.
"""
from __future__ import annotations

import html
import logging
import time

import requests

from .config import settings

log = logging.getLogger("tracker.telegram")
MAX_LEN = 4000  # Telegram's limit is 4096 characters per message


def esc(text) -> str:
    return html.escape(str(text), quote=False)


def configured() -> bool:
    return bool(settings.telegram_token and settings.telegram_chat_id)


def send(text: str) -> bool:
    chunks = _split(text)
    if not configured():
        settings.log_dir.mkdir(parents=True, exist_ok=True)
        with open(settings.log_dir / "telegram_preview.txt", "a", encoding="utf-8") as f:
            f.write(text + "\n\n" + "-" * 40 + "\n\n")
        log.info("Telegram not configured; message written to logs/telegram_preview.txt")
        return False
    url = f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage"
    ok = True
    for chunk in chunks:
        for attempt in range(3):
            try:
                r = requests.post(url, timeout=20, data={
                    "chat_id": settings.telegram_chat_id, "text": chunk,
                    "parse_mode": "HTML", "disable_web_page_preview": "true",
                })
                if r.status_code == 429:
                    time.sleep(r.json().get("parameters", {}).get("retry_after", 5))
                    continue
                r.raise_for_status()
                break
            except requests.RequestException as exc:
                log.warning("Telegram send failed (%s), attempt %d/3", exc, attempt + 1)
                time.sleep(2 ** attempt)
        else:
            ok = False
    return ok


def _split(text: str) -> list[str]:
    if len(text) <= MAX_LEN:
        return [text]
    chunks, current = [], ""
    for block in text.split("\n\n"):
        if len(current) + len(block) + 2 > MAX_LEN and current:
            chunks.append(current)
            current = ""
        current = f"{current}\n\n{block}" if current else block
    if current:
        chunks.append(current)
    return chunks
