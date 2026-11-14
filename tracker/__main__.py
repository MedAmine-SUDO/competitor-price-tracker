"""Command line: python -m tracker <command>

  run              full daily run (scrape, store, match, alert, Excel, report)
  init-db          create the tables
  export           rebuild the Excel file from the last run, without scraping
  test-notify      send a test message to every configured channel (email, Telegram)
  robots           show what robots.txt allows for each configured category
"""
from __future__ import annotations

import argparse
import logging
import sys

from .config import settings
from .logs import setup_logging

log = logging.getLogger("tracker")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tracker", description="Competitor price tracker")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="full daily run")
    run.add_argument("--sites", nargs="+", help="only these sites (keys from config/sites.yaml)")
    run.add_argument("--max-pages", type=int, help="cap pages per category (quick tests)")
    run.add_argument("--no-notify", "--no-telegram", dest="no_notify", action="store_true",
                     help="do not send email/Telegram messages")
    sub.add_parser("init-db")
    sub.add_parser("export")
    sub.add_parser("test-notify")
    sub.add_parser("robots")
    args = ap.parse_args(argv)
    setup_logging()

    if args.cmd == "run":
        from .pipeline import run_pipeline
        try:
            report = run_pipeline(args.sites, args.max_pages, send_notifications=not args.no_notify)
        except Exception as exc:
            log.exception("run crashed")
            if not args.no_notify:
                from . import notify
                from .telegram import esc
                notify.send(f"❌ <b>Relevé en échec</b>\n{esc(type(exc).__name__)}: {esc(str(exc)[:500])}",
                            "❌ Relevé des prix en échec")
            return 2
        return 0 if report["status"] != "failed" else 1

    if args.cmd == "init-db":
        from .db import connect, init_db
        with connect() as conn:
            init_db(conn)
        log.info("database ready")
        return 0

    if args.cmd == "export":
        from .db import connect
        from .export import build_excel
        with connect() as conn:
            row = conn.execute("SELECT id, report FROM runs WHERE status <> 'running' "
                               "ORDER BY id DESC LIMIT 1").fetchone()
            if not row:
                log.error("no finished run yet")
                return 1
            path = build_excel(conn, row["id"], row["report"], settings.load_sites())
        print(path)
        return 0

    if args.cmd == "test-notify":
        from . import notify
        if not notify.configured():
            log.error("set SMTP_HOST, SMTP_USER, SMTP_PASSWORD and EMAIL_TO (or Telegram) in .env first")
            return 1
        ok = notify.send("🔔 <b>Test</b> · le suivi des prix est bien connecté.", "🔔 Test du suivi des prix")
        log.info("sent" if ok else "failed")
        return 0 if ok else 1

    if args.cmd == "robots":
        from .fetch import DisallowedByRobots, Politeness
        from .scrapers import SCRAPERS
        p = Politeness()
        for key, cfg in settings.load_sites().items():
            scraper = SCRAPERS[key](cfg)
            p.set_min_delay(cfg["base_url"], 0)
            for cat in cfg["categories"]:
                for url in [cat["url"], scraper.page_url(cat["url"], 2)]:
                    try:
                        p.check_and_wait(url)
                        verdict = "allowed"
                    except DisallowedByRobots:
                        verdict = "DISALLOWED"
                    print(f"{key:11} {verdict:10} {url}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
