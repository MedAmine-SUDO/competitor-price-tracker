"""PostgreSQL access (psycopg 3)."""
from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Iterator

import pandas as pd
import psycopg
from psycopg.rows import dict_row

from .config import ROOT, settings


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        yield conn


def init_db(conn: psycopg.Connection) -> None:
    conn.execute((ROOT / "sql" / "schema.sql").read_text(encoding="utf-8"))
    conn.commit()


def start_run(conn) -> int:
    run_id = conn.execute("INSERT INTO runs DEFAULT VALUES RETURNING id").fetchone()["id"]
    conn.commit()
    return run_id


def finish_run(conn, run_id: int, status: str, products: int, pages: int, errors: int, report: dict) -> None:
    conn.execute(
        """UPDATE runs SET finished_at = now(), status = %s, products_seen = %s,
                  pages_fetched = %s, errors = %s, report = %s WHERE id = %s""",
        (status, products, pages, errors, json.dumps(report, default=str), run_id),
    )
    conn.commit()


UPSERT_PRODUCT = """
INSERT INTO products (site, site_product_id, url, name, brand, reference, category)
VALUES (%(site)s, %(site_product_id)s, %(url)s, %(name)s, %(brand)s, %(reference)s, %(category)s)
ON CONFLICT (site, site_product_id) DO UPDATE SET
    url = EXCLUDED.url, name = EXCLUDED.name, brand = EXCLUDED.brand,
    reference = COALESCE(EXCLUDED.reference, products.reference),
    category = EXCLUDED.category, last_seen = now()
RETURNING id
"""

INSERT_SNAPSHOT = """
INSERT INTO price_snapshots (product_id, run_id, price, promo_price, in_stock, stock_label)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (product_id, run_id) DO NOTHING
"""


def save_listings(conn, run_id: int, df: pd.DataFrame) -> int:
    """Upsert products and write one price snapshot each. Returns rows written."""
    rows = df.astype(object).where(df.notna(), None).to_dict("records")
    with conn.cursor() as cur:
        for row in rows:
            pid = cur.execute(UPSERT_PRODUCT, row).fetchone()["id"]
            cur.execute(INSERT_SNAPSHOT, (pid, run_id, row["price"], row["promo_price"],
                                          row["in_stock"], row["stock_label"]))
    conn.commit()
    return len(rows)


def recent_site_volumes(conn, before_run: int, runs: int = 7) -> dict[str, float]:
    """Average products per site over the last `runs` successful runs."""
    q = """
    WITH r AS (SELECT id FROM runs WHERE id < %s AND status IN ('ok', 'degraded')
               ORDER BY id DESC LIMIT %s)
    SELECT p.site, COUNT(*)::float / COUNT(DISTINCT s.run_id) AS avg_products
    FROM price_snapshots s JOIN products p ON p.id = s.product_id
    WHERE s.run_id IN (SELECT id FROM r) GROUP BY p.site
    """
    return {r["site"]: r["avg_products"] for r in conn.execute(q, (before_run, runs))}


def read_sql(conn, query: str, params=None) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
        cols = [d.name for d in cur.description] if cur.description else []
    return pd.DataFrame(rows, columns=cols)
