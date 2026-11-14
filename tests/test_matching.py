from decimal import Decimal

from tracker.cleaning import clean_listings
from tracker.matching import match_products
from tracker.scrapers.base import Listing


def P(id, site, name, ref=None, brand=None, category="PC portable"):
    from tracker.parsing import guess_brand
    return {"id": id, "site": site, "name": name, "reference": ref,
            "brand": brand or guess_brand(name), "category": category}


def pairs(groups):
    return sorted(tuple(sorted(m.id for m in g.members)) for g in groups)


def test_exact_and_prefix_reference():
    groups = match_products([
        P(1, "a", "Pc Portable Chuwi CoreBook i3 8Go 256Go", "COREBOOK-I3"),
        P(2, "b", "Pc Portable CHUWI CoreBook / i3-10100Y / 8 Go / 256 Go SSD", "COREBOOK-I3"),
        P(3, "a", "Lenovo IdeaPad 1 Celeron N4500 8Go 256Go", "82LX00G4FG"),
        P(4, "b", "Lenovo IdeaPad 1 / Celeron N4500 / 8 Go / 256 Go", "82LX00G4FG-2Y"),
    ])
    assert pairs(groups) == [(1, 2), (3, 4)]


def test_fuzzy_respects_colour_and_storage():
    groups = match_products([
        P(1, "a", "Smartphone Honor T10 6Go 32Go Silver", category="Smartphone"),
        P(2, "a", "Smartphone Honor T10 6Go 32Go Noir", category="Smartphone"),
        P(3, "b", "SMARTPHONE HONOR Choice T10 6Go / 32Go / Noir", category="Smartphone"),
        P(4, "b", "SMARTPHONE HONOR Choice T10 8Go / 64Go / Silver", category="Smartphone"),
    ])
    assert pairs(groups) == [(2, 3)]


def test_fuzzy_never_joins_different_part_numbers():
    groups = match_products([
        P(1, "a", "Lenovo IdeaPad 1 15IJL7 Celeron N4500 8Go 256Go", "82LX00CEFG-W11"),
        P(2, "b", "Lenovo IdeaPad 1 15IJL7 / Celeron N4500 / 8 Go / 256 Go", "82LX00CFFG-W11P"),
    ])
    assert groups == []


def test_one_listing_per_site_per_group():
    groups = match_products([
        P(1, "a", "Redmi A7 Pro 4Go 64Go Noir", "R1", category="Smartphone"),
        P(2, "a", "Redmi A7 Pro 4Go 64Go Noir", "R2", category="Smartphone"),
        P(3, "b", "Xiaomi Redmi A7 Pro / 4 Go / 64 Go / Noir", category="Smartphone"),
    ])
    assert len(groups) == 1 and len(groups[0].members) == 2


def L(pid, price, promo=None, site="a", name="Produit test 8Go 256Go"):
    return Listing(site=site, site_product_id=pid, url="https://x/" + pid, name=name,
                   price=Decimal(price), promo_price=Decimal(promo) if promo else None,
                   in_stock=True, stock_label="En stock", reference=None, brand=None, category="c")


def test_cleaning_dedupes_and_drops_bad_rows():
    df, stats = clean_listings([L("1", "100"), L("1", "100"), L("2", "0.5"), L("3", "200", promo="250")])
    assert stats == {"raw": 4, "invalid": 1, "duplicates": 1, "clean": 2}
    assert df.loc[df.site_product_id == "3", "promo_price"].isna().all()  # promo >= price is not a promo


def test_tier_words_must_agree():
    groups = match_products([
        P(1, "a", "Samsung Galaxy S26 5G 12Go 256Go Bleu", category="Smartphone"),
        P(2, "b", "Smartphone Samsung Galaxy S26 Ultra 5G / 12 Go / 256 Go / Bleu", category="Smartphone"),
        P(3, "a", "Lenovo IdeaPad Slim 3 i5 16Go 512Go Windows 11 Pro"),
        P(4, "b", "Lenovo IdeaPad Slim 3 / i5 / 16 Go / 512 Go"),
    ])
    assert pairs(groups) == [(3, 4)]


def test_phone_network_must_agree_in_fuzzy_pass():
    groups = match_products([
        P(1, "a", "Smartphone XIAOMI Redmi 15C / 4GO / 128GO / MINT GREEN", category="Smartphone"),
        P(2, "b", "Smartphone Xiaomi Redmi 15C 4Go 128Go 5G Vert", category="Smartphone"),
    ])
    assert groups == []
