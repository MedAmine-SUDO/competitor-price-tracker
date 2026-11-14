"""Clean and dedupe a run's raw listings with pandas."""
from __future__ import annotations

from decimal import Decimal

import pandas as pd

from .parsing import clean_text

COLUMNS = ["site", "site_product_id", "url", "name", "price", "promo_price", "in_stock",
           "stock_label", "reference", "brand", "category"]


def clean_listings(listings: list) -> tuple[pd.DataFrame, dict]:
    df = pd.DataFrame([l.as_dict() for l in listings], columns=COLUMNS)
    stats = {"raw": len(df)}
    if df.empty:
        return df, {**stats, "duplicates": 0, "invalid": 0, "clean": 0}

    df["name"] = df["name"].map(clean_text)
    df["reference"] = df["reference"].map(lambda r: clean_text(r) or None if isinstance(r, str) else None)

    # Drop rows that cannot be used: no name, no price, absurd prices.
    valid = (df["name"].str.len() > 3) & df["price"].notna()
    valid &= df["price"].map(lambda p: p is not None and Decimal("1") <= p <= Decimal("500000"))
    stats["invalid"] = int((~valid).sum())
    df = df[valid]

    # A promo price that is not lower than the regular price is not a promo.
    bad_promo = df["promo_price"].notna() & (df["promo_price"] >= df["price"])
    df.loc[bad_promo, "promo_price"] = None

    # The same product can show up in two categories (e.g. "PC portable" and "PC gamer").
    before = len(df)
    df = df.drop_duplicates(subset=["site", "site_product_id"], keep="first")
    stats["duplicates"] = before - len(df)
    stats["clean"] = len(df)
    return df.reset_index(drop=True), stats
