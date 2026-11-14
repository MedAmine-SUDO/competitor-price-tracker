"""One full daily run: scrape -> clean -> store -> match -> alert -> export -> report."""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import alerts, notify
from .cleaning import clean_listings
from .config import settings
from .db import connect, finish_run, init_db, recent_site_volumes, save_listings, start_run
from .export import build_excel
from .fetch import BotChallenge, HttpFetcher, Politeness
from .matching import match_products, save_groups
from .scrapers import SCRAPERS
from .scrapers.base import CategoryResult
from .telegram import esc

log = logging.getLogger("tracker.pipeline")


def scrape_site(key: str, cfg: dict, politeness: Politeness, max_pages: int | None) -> dict:
    """Runs in its own thread. Returns listings + per-site stats."""
    t0 = time.monotonic()
    scraper = SCRAPERS[key](cfg)
    politeness.set_min_delay(cfg["base_url"], cfg.get("min_delay_s", 3))
    listings, categories = [], []

    def run(fetcher):
        for cat in cfg["categories"]:
            if max_pages:
                cat = {**cat, "max_pages": min(cat.get("max_pages", max_pages), max_pages)}
            try:
                items, result = scraper.scrape_category(fetcher, cat)
            except BotChallenge as exc:
                # The site asked us to stop. Keep what we have and do not insist.
                log.error("%s: %s", key, exc)
                categories.append(CategoryResult(category=cat["name"], errors=[str(exc)]))
                break
            listings.extend(items)
            categories.append(result)

    try:
        if cfg.get("engine") == "browser":
            from .browser import BrowserFetcher
            with BrowserFetcher(politeness, wait_selector=getattr(scraper, "wait_selector", None)) as f:
                run(f)
        else:
            run(HttpFetcher(politeness))
    except Exception as exc:  # a crashed site must not take the others down
        log.exception("%s crashed", key)
        categories.append(CategoryResult(category="*", errors=[f"{type(exc).__name__}: {exc}"]))

    return {
        "site": key,
        "listings": listings,
        "pages": sum(c.pages for c in categories),
        "errors": [e for c in categories for e in (c.errors or [])],
        "categories": {c.category: c.listings for c in categories},
        "duration_s": round(time.monotonic() - t0, 1),
    }


def decide_status(site_reports: dict, expected: dict[str, float]) -> tuple[str, list[str]]:
    """ok / degraded / failed, plus human-readable warnings."""
    warnings = []
    empty = [s for s, r in site_reports.items() if r["products"] == 0]
    for s, r in site_reports.items():
        if r["products"] == 0:
            warnings.append(f"{s}: aucun produit récupéré")
        elif s in expected and r["products"] < expected[s] * settings.volume_drop_warn:
            warnings.append(f"{s}: {r['products']} produits contre {expected[s]:.0f} en moyenne "
                            f"(structure du site modifiée ?)")
        if r["errors"]:
            warnings.append(f"{s}: {len(r['errors'])} erreur(s) de récupération")
    if len(empty) == len(site_reports):
        return "failed", warnings
    return ("degraded" if warnings else "ok"), warnings


def run_pipeline(sites: list[str] | None = None, max_pages: int | None = None,
                 send_notifications: bool = True) -> dict:
    started = datetime.now(timezone.utc)
    t0 = time.monotonic()
    sites_cfg = settings.load_sites()
    if sites:
        sites_cfg = {k: v for k, v in sites_cfg.items() if k in sites}

    with connect() as conn:
        init_db(conn)
        run_id = start_run(conn)
        log.info("run #%d started for %s", run_id, ", ".join(sites_cfg))

        politeness = Politeness()
        with ThreadPoolExecutor(max_workers=len(sites_cfg)) as pool:
            futures = [pool.submit(scrape_site, k, v, politeness, max_pages) for k, v in sites_cfg.items()]
            results = [f.result() for f in futures]

        all_listings = [l for r in results for l in r["listings"]]
        df, clean_stats = clean_listings(all_listings)
        saved = save_listings(conn, run_id, df) if len(df) else 0

        # Re-match everything we know (cheap: a few thousand rows).
        products = conn.execute(
            "SELECT id, site, name, brand, reference, category FROM products").fetchall()
        groups = match_products(products)
        save_groups(conn, groups, list(settings.load_sites()))

        drops = alerts.find_drops(conn, run_id)
        n_alerts = alerts.record_and_send(conn, run_id, drops, send=send_notifications)

        expected = recent_site_volumes(conn, run_id)
        site_reports = {}
        for r in results:
            host = settings.load_sites()[r["site"]]["base_url"].split("//")[1]
            st = politeness.stats.get(host)
            site_reports[r["site"]] = {
                "products": int((df["site"] == r["site"]).sum()) if len(df) else 0,
                "pages": r["pages"], "categories": r["categories"],
                "retries": st.retries if st else 0, "errors": r["errors"],
                "blocked_by_robots": st.blocked_by_robots if st else 0,
                "mb": round(st.bytes / 1e6, 1) if st else 0, "duration_s": r["duration_s"],
            }
        status, warnings = decide_status(site_reports, expected)
        report = {
            "run_id": run_id, "started_at": started.isoformat(), "status": status,
            "duration_s": round(time.monotonic() - t0, 1), "cleaning": clean_stats,
            "matched_groups": len(groups), "price_drops": n_alerts, "warnings": warnings,
            "sites": {k: {**v, "errors": len(v["errors"]), "error_details": v["errors"][:5]}
                      for k, v in site_reports.items()},
        }
        excel = build_excel(conn, run_id, report, {k: settings.load_sites()[k] for k in sites_cfg})
        report["excel"] = str(excel)
        report["duration_s"] = round(time.monotonic() - t0, 1)
        finish_run(conn, run_id, status, saved, sum(r["pages"] for r in results),
                   sum(len(r["errors"]) for r in results), report)

    log.info("run #%d %s: %d products, %d groups, %d drops, %.1fs",
             run_id, status.upper(), saved, len(groups), n_alerts, report["duration_s"])
    if send_notifications:
        notify.send(format_run_report(report, sites_cfg), report_subject(report), [excel])
    return report


def report_subject(report: dict) -> str:
    label = {"ok": "✅ Relevé des prix OK", "degraded": "⚠️ Relevé des prix incomplet",
             "failed": "❌ Relevé des prix en échec"}[report["status"]]
    day = report["started_at"][:10]
    return f"{label} · {day} · {report['price_drops']} baisse(s)"


def format_run_report(report: dict, sites_cfg: dict) -> str:
    icon = {"ok": "✅", "degraded": "⚠️", "failed": "❌"}[report["status"]]
    label = {"ok": "Relevé OK", "degraded": "Relevé incomplet", "failed": "Relevé en échec"}[report["status"]]
    lines = [f"{icon} <b>{label}</b> · run #{report['run_id']} · {report['duration_s'] / 60:.1f} min"]
    for key, s in report["sites"].items():
        name = sites_cfg.get(key, {}).get("name", key)
        extra = f", {s['retries']} relance(s)" if s["retries"] else ""
        extra += f", {s['errors']} erreur(s)" if s["errors"] else ""
        lines.append(f"• {esc(name)} : {s['products']} produits, {s['pages']} pages{extra}")
    lines.append(f"🔗 {report['matched_groups']} produits comparés entre sites")
    lines.append(f"📉 {report['price_drops']} baisse(s) &gt; {settings.drop_threshold_pct:g}%")
    for w in report["warnings"]:
        lines.append(f"⚠️ {esc(w)}")
    return "\n".join(lines)
