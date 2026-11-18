"""Build the morning Excel file (French labels, for the client)."""
from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from .config import settings
from .db import read_sql

log = logging.getLogger("tracker.export")

NAVY = "1F3A5F"
HEADER_FILL = PatternFill("solid", fgColor=NAVY)
HEADER_FONT = Font(bold=True, color="FFFFFF")
GREEN_FILL = PatternFill("solid", fgColor="D9F2E3")
RED_FONT = Font(color="B42318", bold=True)
THIN = Border(bottom=Side(style="thin", color="D0D5DD"))
MONEY = '#,##0.000 "DT"'
PCT = '0.0"%"'

TODAY_SQL = """
SELECT site, name, brand, reference, category, price, promo_price, effective_price,
       in_stock, stock_label, url, group_id
FROM latest_prices WHERE run_id = %s ORDER BY site, category, name
"""

# A site skipped today (every_days) keeps the prices of its last scrapes, so it still
# shows in the comparison. Older listings fall out, as the site has probably dropped them.
CARRIED_SQL = """
SELECT site, name, brand, reference, category, price, promo_price, effective_price,
       in_stock, stock_label, url, group_id
FROM latest_prices WHERE site = %s AND scraped_at >= %s::date - %s * interval '1 day'
ORDER BY category, name
"""

DROPS_SQL = """
SELECT p.site, p.name, a.old_price, a.new_price, a.drop_pct, p.url
FROM alerts a JOIN products p ON p.id = a.product_id
WHERE a.run_id = %s ORDER BY a.drop_pct DESC
"""


def _header(ws: Worksheet, row: int, labels: list[str]) -> None:
    for col, label in enumerate(labels, start=1):
        c = ws.cell(row=row, column=col, value=label)
        c.fill, c.font = HEADER_FILL, HEADER_FONT
        c.alignment = Alignment(vertical="center", wrap_text=True)
    ws.row_dimensions[row].height = 30


def _widths(ws: Worksheet, widths: list[int]) -> None:
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _write_table(ws, df: pd.DataFrame, labels: list[str], widths: list[int], formats: dict[int, str],
                 link_col: int | None = None, start_row: int = 1) -> None:
    _header(ws, start_row, labels)
    for r, row in enumerate(df.itertuples(index=False), start=start_row + 1):
        for c, value in enumerate(row, start=1):
            if isinstance(value, float) and pd.isna(value):
                value = None
            if value is pd.NA or value is pd.NaT:
                value = None
            if hasattr(value, "is_finite"):  # Decimal -> float for Excel
                value = float(value)
            cell = ws.cell(row=r, column=c, value=value)
            cell.border = THIN
            if c in formats:
                cell.number_format = formats[c]
            if link_col == c and value:
                cell.hyperlink, cell.value, cell.font = value, "ouvrir", Font(color="1D4ED8", underline="single")
    _widths(ws, widths)
    ws.freeze_panes = ws.cell(row=start_row + 1, column=1)
    if len(df):
        ws.auto_filter.ref = f"A{start_row}:{get_column_letter(len(labels))}{start_row + len(df)}"


def comparison_table(today: pd.DataFrame, sites: list[str]) -> pd.DataFrame:
    """One row per matched product, one price column per site."""
    m = today[today["group_id"].notna()].copy()
    if m.empty:
        return pd.DataFrame()
    m["effective_price"] = m["effective_price"].astype(float)
    pivot = m.pivot_table(index="group_id", columns="site", values="effective_price", aggfunc="min")
    pivot = pivot.reindex(columns=[s for s in sites if s in pivot.columns])
    names = m.sort_values("site", key=lambda s: s.map({x: i for i, x in enumerate(sites)})) \
             .groupby("group_id")["name"].first()
    out = pd.DataFrame({"Produit": names}).join(pivot)
    prices = out[pivot.columns]
    ties = prices.eq(prices.min(axis=1), axis=0).sum(axis=1) > 1
    out["Moins cher"] = prices.idxmin(axis=1).str.capitalize().where(~ties, "Égalité")
    out["Écart max %"] = ((prices.max(axis=1) - prices.min(axis=1)) / prices.min(axis=1) * 100).round(1)
    return out.sort_values("Écart max %", ascending=False).reset_index(drop=True)


def build_excel(conn, run_id: int, report: dict, sites_cfg: dict) -> Path:
    sites = list(sites_cfg)
    today = read_sql(conn, TODAY_SQL, (run_id,))
    carried = [read_sql(conn, CARRIED_SQL, (site, s["last_day"], s["every_days"]))
               for site, s in report.get("skipped", {}).items()]
    if carried:
        today = pd.concat([today, *carried], ignore_index=True)
    drops = read_sql(conn, DROPS_SQL, (run_id,))
    wb = Workbook()

    # 1. Summary ------------------------------------------------------------------
    ws = wb.active
    ws.title = "Résumé"
    ws["A1"] = "Suivi des prix concurrents"
    ws["A1"].font = Font(bold=True, size=16, color=NAVY)
    run_time = datetime.fromisoformat(str(report["started_at"])).astimezone(ZoneInfo("Africa/Tunis"))
    ws["A2"] = f"Relevé du {run_time:%d/%m/%Y à %H:%M} · statut : {report['status'].upper()}"
    ws["A2"].font = Font(italic=True, color="475467")
    _header(ws, 4, ["Site", "Produits suivis", "En promo", "En stock", "Pages lues", "Erreurs"])
    for i, site in enumerate(sites, start=5):
        s = today[today["site"] == site]
        st = report["sites"].get(site, {})
        values = [sites_cfg[site]["name"], len(s), int(s["promo_price"].notna().sum()),
                  int((s["in_stock"] == True).sum()), st.get("pages", 0), st.get("errors", 0)]  # noqa: E712
        for c, v in enumerate(values, start=1):
            ws.cell(row=i, column=c, value=v).border = THIN
    r = 5 + len(sites) + 1
    comp = comparison_table(today, sites)
    for label, value in [
        ("Produits au total", len(today)),
        ("Produits trouvés sur plusieurs sites", len(comp)),
        (f"Baisses de prix > {settings.drop_threshold_pct:g}%", len(drops)),
        ("Durée du relevé", f"{report['duration_s'] / 60:.1f} min"),
    ]:
        ws.cell(row=r, column=1, value=label).font = Font(bold=True)
        ws.cell(row=r, column=2, value=value)
        r += 1
    _widths(ws, [38, 16, 12, 12, 12, 10])

    # 2. Cross-site comparison ---------------------------------------------------------
    ws = wb.create_sheet("Comparatif")
    if not comp.empty:
        price_cols = [c for c in comp.columns if c in sites]
        labels = ["Produit"] + [sites_cfg[s]["name"] for s in price_cols] + ["Moins cher", "Écart max %"]
        formats = {i: MONEY for i in range(2, 2 + len(price_cols))}
        formats[len(labels)] = PCT
        _write_table(ws, comp, labels, [70] + [16] * len(price_cols) + [14, 12], formats)
        # Highlight the cheapest price on each row.
        first, last = get_column_letter(2), get_column_letter(1 + len(price_cols))
        for row in range(2, len(comp) + 2):
            rng = f"{first}{row}:{last}{row}"
            ws.conditional_formatting.add(
                rng, CellIsRule(operator="equal", formula=[f"MIN(${first}{row}:${last}{row})"], fill=GREEN_FILL))
    else:
        ws["A1"] = "Aucun produit commun trouvé pour l'instant."

    # 3. Today's prices -------------------------------------------------------------
    ws = wb.create_sheet("Prix du jour")
    t = today.copy()
    for col in ("price", "promo_price", "effective_price"):
        t[col] = t[col].map(lambda v: float(v) if v is not None and pd.notna(v) else None)
    t["remise"] = ((t["price"] - t["effective_price"]) / t["price"] * 100).round(1).where(t["promo_price"].notna())
    t["site"] = t["site"].map(lambda s: sites_cfg.get(s, {}).get("name", s))
    t["in_stock"] = t["in_stock"].map({True: "Oui", False: "Non"})
    cols = ["site", "category", "name", "brand", "reference", "price", "promo_price", "remise",
            "in_stock", "stock_label", "url"]
    _write_table(ws, t[cols],
                 ["Site", "Catégorie", "Produit", "Marque", "Référence", "Prix", "Prix promo", "Remise %",
                  "En stock", "Disponibilité", "Lien"],
                 [12, 14, 70, 11, 20, 14, 14, 10, 9, 16, 9],
                 {6: MONEY, 7: MONEY, 8: PCT}, link_col=11)

    # 4. Price drops ---------------------------------------------------------------
    ws = wb.create_sheet("Baisses de prix")
    if drops.empty:
        ws["A1"] = f"Aucune baisse de plus de {settings.drop_threshold_pct:g}% depuis le dernier relevé."
    else:
        d = drops.copy()
        d["site"] = d["site"].map(lambda s: sites_cfg.get(s, {}).get("name", s))
        _write_table(ws, d, ["Site", "Produit", "Ancien prix", "Nouveau prix", "Baisse %", "Lien"],
                     [12, 70, 14, 14, 10, 9], {3: MONEY, 4: MONEY, 5: PCT}, link_col=6)
        for row in range(2, len(d) + 2):
            ws.cell(row=row, column=5).font = RED_FONT

    settings.export_dir.mkdir(parents=True, exist_ok=True)
    path = settings.export_dir / f"prix_concurrents_{run_time:%Y-%m-%d}.xlsx"
    wb.save(path)
    shutil.copyfile(path, settings.export_dir / "prix_concurrents_latest.xlsx")
    log.info("Excel written: %s", path)
    return path
