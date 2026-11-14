"""Generate the dashboard's demo dataset (dashboard/demo/): five fictional shops, three weeks of
daily runs, with promos, price changes and drops. Real product models, invented prices.

    python scripts/make_demo_data.py
"""
from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "dashboard" / "demo"
RUNS = 21
LAST_RUN = datetime(2026, 11, 14, 6, 30, tzinfo=timezone.utc)  # 07:30 in Tunis
DROP_PCT = 10

# key: (display name, share of the catalog it lists, price level vs. market)
SHOPS = {
    "boutique_a": ("Boutique A", 0.85, 1.000),
    "boutique_b": ("Boutique B", 0.80, 0.985),
    "boutique_c": ("Boutique C", 0.35, 1.020),
    "boutique_d": ("Boutique D", 0.55, 0.995),
    "boutique_e": ("Boutique E", 0.45, 1.010),
}

# brand, line, model code, cpu, [(ram, storage, price)]
LAPTOPS = [
    ("Lenovo", "IdeaPad Slim 3", "15IRH8", "i5-13420H", [(8, 512, 1849), (16, 512, 2049)]),
    ("Lenovo", "IdeaPad 1", "15AMN7", "Ryzen 5 7520U", [(8, 256, 1299), (8, 512, 1399)]),
    ("Lenovo", "ThinkBook 16 G9", "21US002XFE", "Core 5 210H", [(16, 512, 2799)]),
    ("Lenovo", "LOQ", "15IRX10", "i7-13650HX", [(16, 512, 3999)]),
    ("HP", "15", "fd0438nk", "i3-1315U", [(8, 512, 1599), (16, 512, 1779)]),
    ("HP", "15", "fd0580nk", "i5-1334U", [(8, 512, 1949)]),
    ("HP", "Victus 16", "r0001nk", "i5-13500H", [(16, 512, 3299)]),
    ("HP", "ProBook 450 G10", "85B03EA", "i7-1355U", [(16, 512, 3449)]),
    ("Asus", "Vivobook 15", "X1502VA", "i5-13420H", [(8, 512, 1999), (16, 512, 2199)]),
    ("Asus", "Vivobook 16", "X1605VA", "Core 9 270H", [(16, 1024, 2899)]),
    ("Asus", "TUF Gaming A16", "FA607NU", "Ryzen 7 7435HS", [(16, 512, 3899)]),
    ("Asus", "Zenbook 14", "UX3405MA", "Ultra 7 155H", [(16, 1024, 4299)]),
    ("Dell", "Pro 15 Essential", "PV15250", "i5-1334U", [(8, 512, 2299), (16, 512, 2499)]),
    ("Dell", "Pro 15 Essential", "PV15255", "Ryzen 5 7520U", [(8, 512, 1999)]),
    ("Dell", "Vostro 3530", "N1604PVNB3530", "i5-1335U", [(8, 512, 2149)]),
    ("Acer", "Aspire 3", "A315-59", "i3-1215U", [(8, 256, 1349), (8, 512, 1449)]),
    ("Acer", "Nitro V 15", "ANV15-51", "i5-13420H", [(16, 512, 3199)]),
    ("MSI", "Thin 15", "B13UC", "i7-13620H", [(16, 512, 3599), (32, 512, 3899)]),
    ("MSI", "Modern 15", "B13M", "i5-1335U", [(8, 512, 1899)]),
    ("Apple", "MacBook Air 13", "MC6T4FN", "M4", [(16, 256, 4699)]),
]
# brand, model, [(ram, storage, price)], colours
PHONES = [
    ("Samsung", "Galaxy A16", [(4, 128, 649), (6, 128, 729)], ["Noir", "Bleu"]),
    ("Samsung", "Galaxy A26 5G", [(6, 128, 999), (8, 256, 1199)], ["Noir", "Blanc"]),
    ("Samsung", "Galaxy A56 5G", [(8, 256, 1699)], ["Gris", "Rose"]),
    ("Samsung", "Galaxy S26 Ultra 5G", [(12, 256, 5999)], ["Noir", "Gris"]),
    ("Xiaomi", "Redmi 15C", [(4, 128, 449), (8, 256, 599)], ["Noir", "Vert"]),
    ("Xiaomi", "Redmi Note 15", [(8, 256, 899)], ["Noir", "Bleu"]),
    ("Xiaomi", "Redmi Note 15 Pro 5G", [(8, 256, 1349)], ["Noir", "Violet"]),
    ("Honor", "X7c", [(8, 256, 699)], ["Noir", "Vert"]),
    ("Honor", "X9d 5G", [(12, 256, 1399)], ["Noir", "Orange"]),
    ("Infinix", "Hot 60", [(8, 128, 529)], ["Noir", "Bleu"]),
    ("Infinix", "Note 50 Pro", [(8, 256, 849)], ["Gris", "Violet"]),
    ("Tecno", "Spark 40", [(8, 128, 499)], ["Noir", "Blanc"]),
    ("Oppo", "A5 Pro", [(8, 256, 899)], ["Noir", "Marron"]),
    ("Vivo", "Y29", [(6, 128, 649)], ["Noir", "Vert"]),
    ("Apple", "iPhone 16", [(8, 128, 4299)], ["Noir", "Blanc"]),
    ("Apple", "iPhone 17 Pro", [(12, 256, 6499)], ["Argent", "Orange"]),
]


def laptop_name(shop: str, brand, line, code, cpu, ram, sto) -> str:
    s = f"{sto // 1024} To" if sto >= 1024 else f"{sto} Go"
    return {
        "boutique_a": f"Pc Portable {brand} {line} {code} / {cpu} / {ram} Go / {s} SSD",
        "boutique_b": f"PC Portable {brand} {line} {code} {cpu} {ram}Go {s.replace(' ', '')} SSD",
        "boutique_c": f"PC Portable {brand.upper()} {line} {code} {cpu} {ram}G {s.replace(' Go', 'G')} SSD",
        "boutique_d": f"PC Portable {brand} {line} {code} – {cpu} – {ram} Go – {s} SSD",
        "boutique_e": f"Pc Portable {brand} {line} {code} {ram}Go {s.replace(' ', '')} SSD",
    }[shop]


def phone_name(shop: str, brand, model, ram, sto, colour) -> str:
    return {
        "boutique_a": f"Smartphone {brand} {model} / {ram} Go / {sto} Go / {colour}",
        "boutique_b": f"Smartphone {brand} {model} {ram}Go {sto}Go {colour}",
        "boutique_c": f"Smartphone {brand.upper()} {model} {ram}G/{sto}G - {colour}",
        "boutique_d": f"Smartphone {brand} {model} – {ram} Go – {sto} Go – {colour}",
        "boutique_e": f"Smartphone {brand} {model} {ram}Go {sto}Go {colour}",
    }[shop]


def shop_price(base: float) -> float:
    """Shop prices end in 9 (1 849,000 DT)."""
    return max(9.0, round(base / 10) * 10 - 1.0)


def catalog():
    """One entry per real-world SKU: (category, brand, base price, {shop: name})."""
    skus = []
    for brand, line, code, cpu, variants in LAPTOPS:
        for ram, sto, price in variants:
            names = {k: laptop_name(k, brand, line, code, cpu, ram, sto) for k in SHOPS}
            skus.append(("PC portable", brand.lower(), price, names))
    for brand, model, variants, colours in PHONES:
        for ram, sto, price in variants:
            for colour in colours:
                names = {k: phone_name(k, brand, model, ram, sto, colour) for k in SHOPS}
                skus.append(("Smartphone", brand.lower(), price, names))
    return skus


def main(seed: int = 7) -> None:
    rnd = random.Random(seed)
    products, listings = [], []  # listing = [product_id, shop, current base, promo_until, promo_pct]
    group = 0
    for category, brand, price, names in catalog():
        shops = [k for k, (_, share, _) in SHOPS.items() if rnd.random() < share]
        if not shops:
            continue
        group_id = None
        if len(shops) >= 2:
            group += 1
            group_id = group
        market = price * rnd.uniform(0.97, 1.03)
        for k in shops:
            pid = len(products) + 1
            level = 1.0 if rnd.random() < 0.45 else SHOPS[k][2] * rnd.uniform(0.98, 1.02)
            products.append({"id": pid, "site": k, "name": names[k], "brand": brand, "category": category,
                             "url": f"https://{k.replace('_', '-')}.example/produit/{pid}", "group_id": group_id})
            listings.append({"pid": pid, "shop": k, "base": shop_price(market * level), "promo": None})

    runs, snapshots, alerts = [], [], []
    last_eff: dict[int, float] = {}
    for n in range(RUNS):
        run_id = n + 1
        started = LAST_RUN - timedelta(days=RUNS - 1 - n)
        blocked = n % 3 == 1  # Boutique C stops at a bot check now and then, like a real site
        per_site = {k: 0 for k in SHOPS}
        drops = 0
        for li in listings:
            if n:
                if li["promo"] and li["promo"][0] < run_id:
                    li["promo"] = None
                r = rnd.random()
                if not li["promo"] and r < 0.025:
                    li["promo"] = (run_id + rnd.randint(2, 7), rnd.choice([0.05, 0.08, 0.10, 0.12, 0.15, 0.18]))
                elif r > 0.992:
                    li["base"] = shop_price(li["base"] * rnd.uniform(0.86, 1.06))
            if blocked and li["shop"] == "boutique_c" and rnd.random() < 0.6:
                continue
            promo = shop_price(li["base"] * (1 - li["promo"][1])) if li["promo"] else None
            eff = promo or li["base"]
            prev = last_eff.get(li["pid"])
            if prev and eff <= prev * (1 - DROP_PCT / 100):
                alerts.append({"product_id": li["pid"], "run_id": run_id, "old_price": prev, "new_price": eff,
                               "drop_pct": round((prev - eff) / prev * 100, 2)})
                drops += 1
            last_eff[li["pid"]] = eff
            snapshots.append({"product_id": li["pid"], "run_id": run_id, "price": li["base"],
                              "promo_price": promo, "in_stock": rnd.random() > 0.12})
            per_site[li["shop"]] += 1
        duration = rnd.uniform(170, 290)
        warnings = ["boutique_c: arrêté par une vérification anti-bot"] if blocked else []
        report = {
            "run_id": run_id, "status": "degraded" if blocked else "ok", "duration_s": round(duration, 1),
            "price_drops": drops, "warnings": warnings, "matched_groups": group,
            "sites": {k: {"products": c, "pages": max(1, c // 24), "retries": rnd.choice([0, 0, 0, 1, 2]),
                          "errors": int(blocked and k == "boutique_c")} for k, c in per_site.items()},
        }
        runs.append({"id": run_id, "started_at": started.isoformat(),
                     "finished_at": (started + timedelta(seconds=duration)).isoformat(),
                     "status": report["status"], "products_seen": sum(per_site.values()),
                     "pages_fetched": sum(s["pages"] for s in report["sites"].values()),
                     "errors": int(blocked), "report": report})

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sites.json").write_text(json.dumps({k: v[0] for k, v in SHOPS.items()}, ensure_ascii=False, indent=1))
    (OUT / "runs.json").write_text(json.dumps(runs, ensure_ascii=False))
    for name, rows in [("products", products), ("snapshots", snapshots), ("alerts", alerts)]:
        with open(OUT / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    print(f"{len(products)} listings, {group} cross-shop products, {len(snapshots)} snapshots, "
          f"{len(alerts)} drops over {RUNS} runs -> {OUT}")


if __name__ == "__main__":
    main()
