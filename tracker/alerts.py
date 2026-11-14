"""Detect price drops versus each product's previous snapshot and send an alert."""
from __future__ import annotations

import logging

import pandas as pd

from . import notify
from .config import settings
from .db import read_sql
from .telegram import esc

log = logging.getLogger("tracker.alerts")

DROPS_SQL = """
WITH cur AS (
    SELECT product_id, COALESCE(promo_price, price) AS eff
    FROM price_snapshots WHERE run_id = %(run)s
), prev AS (
    SELECT DISTINCT ON (s.product_id) s.product_id, COALESCE(s.promo_price, s.price) AS eff
    FROM price_snapshots s JOIN cur USING (product_id)
    WHERE s.run_id < %(run)s
    ORDER BY s.product_id, s.run_id DESC
)
SELECT p.id AS product_id, p.site, p.name, p.url, p.group_id,
       prev.eff AS old_price, cur.eff AS new_price,
       ROUND((prev.eff - cur.eff) / prev.eff * 100, 2) AS drop_pct
FROM cur JOIN prev USING (product_id) JOIN products p ON p.id = cur.product_id
WHERE cur.eff <= prev.eff * (1 - %(pct)s / 100.0)
ORDER BY drop_pct DESC
"""

# Cheapest price among the other sites for the same product, to give each alert context.
COMPETITORS_SQL = """
SELECT group_id, site, effective_price FROM latest_prices
WHERE group_id = ANY(%s)
"""


def find_drops(conn, run_id: int, threshold_pct: float | None = None) -> pd.DataFrame:
    pct = settings.drop_threshold_pct if threshold_pct is None else threshold_pct
    return read_sql(conn, DROPS_SQL, {"run": run_id, "pct": pct})


def record_and_send(conn, run_id: int, drops: pd.DataFrame, send: bool = True) -> int:
    if drops.empty:
        return 0
    new_rows = []
    with conn.cursor() as cur:
        for r in drops.itertuples():
            inserted = cur.execute(
                """INSERT INTO alerts (product_id, run_id, old_price, new_price, drop_pct)
                   VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING RETURNING id""",
                (r.product_id, run_id, r.old_price, r.new_price, r.drop_pct),
            ).fetchone()
            if inserted:
                new_rows.append(r)
    conn.commit()
    if not new_rows or not send:
        return len(new_rows)

    groups = [int(r.group_id) for r in new_rows if pd.notna(r.group_id)]
    competitors: dict[int, list[tuple[str, float]]] = {}
    if groups:
        for row in conn.execute(COMPETITORS_SQL, (groups,)):
            competitors.setdefault(row["group_id"], []).append((row["site"], float(row["effective_price"])))

    text = format_alert(new_rows, competitors)
    subject = f"📉 {len(new_rows)} baisse(s) de prix > {settings.drop_threshold_pct:g}%"
    if notify.send(text, subject):
        conn.execute("UPDATE alerts SET sent = true WHERE run_id = %s", (run_id,))
        conn.commit()
    return len(new_rows)


def fmt_dt(value) -> str:
    """1099.5 -> '1 099,500'"""
    return f"{float(value):,.3f}".replace(",", " ").replace(".", ",")


def format_alert(rows, competitors: dict) -> str:
    head = (f"📉 <b>{len(rows)} baisse(s) de prix &gt; {settings.drop_threshold_pct:g}%</b>\n"
            f"<i>par rapport au relevé précédent</i>")
    blocks = [head]
    for r in rows[:40]:
        line = (f"<b>{esc(r.site.capitalize())}</b> · {esc(r.name[:90])}\n"
                f"{fmt_dt(r.old_price)} → <b>{fmt_dt(r.new_price)} DT</b> "
                f"(−{float(r.drop_pct):.1f}%)\n<a href=\"{esc(r.url)}\">voir le produit</a>")
        others = [c for c in competitors.get(int(r.group_id), []) if c[0] != r.site] if pd.notna(r.group_id) else []
        if others:
            site, price = min(others, key=lambda c: c[1])
            verdict = "désormais le moins cher" if float(r.new_price) < price else f"toujours plus cher que {site.capitalize()}"
            line += f"\n↳ {site.capitalize()} : {fmt_dt(price)} DT ({verdict})"
        blocks.append(line)
    if len(rows) > 40:
        blocks.append(f"… et {len(rows) - 40} autres (voir le fichier Excel).")
    return "\n\n".join(blocks)
