from decimal import Decimal

import pytest

from tracker.parsing import (extract_specs, guess_brand, normalize_reference, parse_price,
                             parse_stock, part_number)


@pytest.mark.parametrize("text,expected", [
    ("1 099,000 DT", Decimal("1099.000")),
    ("1 099,000 DT", Decimal("1099.000")),
    ("459,000 TND", Decimal("459.000")),
    ("1.299,500 DT", Decimal("1299.500")),
    ("1,299.50", Decimal("1299.50")),
    ("2099", Decimal("2099")),
    ("", None),
    ("Prix sur demande", None),
    ("0,000 DT", None),
])
def test_parse_price(text, expected):
    assert parse_price(text) == expected


@pytest.mark.parametrize("label,in_stock", [
    ("En stock", True),
    ("Disponible 514", True),
    ("Indisponible", False),
    ("Hors stock", False),
    ("En Arrivage", False),
    ("Sur commande", False),
    ("", None),
])
def test_parse_stock(label, in_stock):
    assert parse_stock(label)[0] is in_stock


def test_specs_ram_storage_cpu():
    s = extract_specs("Pc Portable CHUWI CoreBook / i3-10100Y / 8 Go / 256 Go SSD / Gris")
    assert s["ram_gb"] == 8 and s["storage_gb"] == 256 and s["cpu_family"] == "i3"
    assert s["colour"] == "grey"


def test_specs_terabyte_and_entry_cpu():
    s = extract_specs("Lenovo IdeaPad 1 Celeron N4500 8Go 1To")
    assert s["storage_gb"] == 1024 and s["cpu_family"] == "intel-entry"
    assert extract_specs("HP 15 N4500 8Go 256Go")["cpu"] == extract_specs("HP 15 Celeron N4500 8Go 256Go")["cpu"]


def test_colour_synonyms():
    assert extract_specs("Redmi 15C 4Go 128Go Noir")["colour"] == extract_specs("Redmi 15C / MIDNIGHT BLACK")["colour"]


def test_reference_helpers():
    assert normalize_reference("[MAXBOOK-X15]") == "MAXBOOKX15"
    assert normalize_reference("AB1") is None
    assert part_number("82LX00CEFG-W11P") == "82LX00CEFG"
    assert part_number("HONOR-T10-4/64-BLACK") is None


def test_brand_aliases():
    assert guess_brand("Smartphone Redmi A7 Pro") == "xiaomi"
    assert guess_brand("Pc Portable Lenovo IdeaPad") == "lenovo"
    assert guess_brand("Câble USB-C") is None
