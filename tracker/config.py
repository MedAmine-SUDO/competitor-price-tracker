"""Settings, read from environment variables (and a local .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


@dataclass
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql://tracker:tracker@localhost:5433/pricetracker"
    )
    telegram_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    # Email over SMTP, e.g. Gmail: smtp.gmail.com, port 587, an app password.
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", 587))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    email_from: str = os.getenv("EMAIL_FROM", "")
    # Comma-separated recipients
    email_to: list[str] = field(
        default_factory=lambda: [a.strip() for a in os.getenv("EMAIL_TO", "").split(",") if a.strip()]
    )
    drop_threshold_pct: float = _float("PRICE_DROP_THRESHOLD_PCT", 10.0)
    user_agent: str = os.getenv(
        "USER_AGENT",
        "Mozilla/5.0 (compatible; PriceTrackerBot/1.0; +https://github.com/MedAmine-SUDO/competitor-price-tracker)",
    )
    # Comma-separated list, e.g. "http://user:pass@1.2.3.4:8080,http://5.6.7.8:3128"
    proxies: list[str] = field(
        default_factory=lambda: [p.strip() for p in os.getenv("PROXY_LIST", "").split(",") if p.strip()]
    )
    # "" = Playwright's bundled Chromium; "chrome" = the Google Chrome installed on the machine.
    browser_channel: str = os.getenv("BROWSER_CHANNEL", "")
    max_retries: int = int(os.getenv("MAX_RETRIES", 4))
    request_timeout_s: float = _float("REQUEST_TIMEOUT_S", 30)
    export_dir: Path = Path(os.getenv("EXPORT_DIR", ROOT / "exports"))
    log_dir: Path = Path(os.getenv("LOG_DIR", ROOT / "logs"))
    sites_file: Path = Path(os.getenv("SITES_FILE", ROOT / "config" / "sites.yaml"))
    # A site is flagged if it returns fewer products than this share of its recent average.
    volume_drop_warn: float = _float("VOLUME_DROP_WARN", 0.7)

    def load_sites(self) -> dict:
        with open(self.sites_file, encoding="utf-8") as f:
            return yaml.safe_load(f)["sites"]


settings = Settings()
