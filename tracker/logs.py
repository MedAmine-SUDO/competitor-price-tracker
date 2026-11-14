"""Logging to the console and to a daily-rotated file in logs/."""
from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler

from .config import settings

FORMAT = "%(asctime)s %(levelname)-7s %(name)-22s %(message)s"


def setup_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(level)
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(FORMAT, "%H:%M:%S"))
    root.addHandler(console)

    settings.log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = TimedRotatingFileHandler(
        settings.log_dir / "tracker.log", when="midnight", backupCount=30, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(FORMAT))
    root.addHandler(file_handler)

    for noisy in ("urllib3", "asyncio", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
