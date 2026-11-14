"""Find the same product across sites.

Two passes, from most to least certain:
  1. reference code: the manufacturer part number most shops print on the card
     (exact match, or one code extending the other, e.g. MAXBOOKX15 / MAXBOOKX15N4100);
  2. fuzzy name: same brand + similar cleaned name.
Both passes refuse a match when the specs that separate variants (RAM, storage, CPU,
colour) disagree, and the fuzzy pass never pairs two different manufacturer part numbers. A group never holds two listings from the same site.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from .parsing import extract_specs, name_tokens, normalize_reference, part_number

log = logging.getLogger("tracker.matching")

FUZZY_THRESHOLD = 90
PREFIX_NAME_THRESHOLD = 75


@dataclass
class Item:
    id: int
    site: str
    name: str
    brand: str | None
    category: str | None
    ref: str | None
    part: str | None
    specs: dict
    tokens: str


@dataclass
class Group:
    members: list[Item] = field(default_factory=list)
    method: str = "reference"

    @property
    def sites(self) -> set[str]:
        return {m.site for m in self.members}


def specs_compatible(a: dict, b: dict) -> bool:
    for key in ("ram_gb", "storage_gb", "cpu", "cpu_family", "colour", "network", "tier"):
        if key in a and key in b and a[key] != b[key]:
            return False
    return True


def _to_items(products: list[dict]) -> list[Item]:
    return [
        Item(
            id=p["id"], site=p["site"], name=p["name"], brand=p.get("brand"), category=p.get("category"),
            ref=normalize_reference(p.get("reference")), part=part_number(p.get("reference")),
            specs=extract_specs(p["name"]),
            tokens=name_tokens(p["name"]),
        )
        for p in products
    ]


def match_products(products: list[dict]) -> list[Group]:
    """products: dicts with id, site, name, brand, reference, category. Returns multi-site groups."""
    items = _to_items(products)
    group_of: dict[int, Group] = {}

    def merge(a: Item, b: Item, method: str) -> bool:
        ga, gb = group_of.get(a.id), group_of.get(b.id)
        if ga is not None and ga is gb:
            return False
        sites_a = ga.sites if ga else {a.site}
        sites_b = gb.sites if gb else {b.site}
        if sites_a & sites_b:
            return False  # would put two listings of one site in one group
        members_a = ga.members if ga else [a]
        members_b = gb.members if gb else [b]
        if not all(specs_compatible(x.specs, y.specs) for x in members_a for y in members_b):
            return False
        g = Group(members=members_a + members_b,
                  method="fuzzy" if "fuzzy" in (method, getattr(ga, "method", ""), getattr(gb, "method", "")) else method)
        for m in g.members:
            group_of[m.id] = g
        return True

    # Pass 1a: exact reference.
    by_ref: dict[str, list[Item]] = {}
    for it in items:
        if it.ref:
            by_ref.setdefault(it.ref, []).append(it)
    for same in by_ref.values():
        for other in same[1:]:
            merge(same[0], other, "reference")

    # Pass 1b: one reference is a prefix of another, and the names agree.
    refs = sorted((it for it in items if it.ref and len(it.ref) >= 7), key=lambda i: i.ref)
    for i, a in enumerate(refs):
        for b in refs[i + 1:]:
            if not b.ref.startswith(a.ref):
                break
            if a.site != b.site and fuzz.token_set_ratio(a.tokens, b.tokens) >= PREFIX_NAME_THRESHOLD:
                merge(a, b, "reference")

    # Pass 2: fuzzy names within the same brand and category, best candidate first.
    blocks: dict[tuple, list[Item]] = {}
    for it in items:
        if it.brand and it.tokens:
            blocks.setdefault((it.brand, it.category), []).append(it)
    for block in blocks.values():
        pairs = []
        for i, a in enumerate(block):
            for b in block[i + 1:]:
                if a.site == b.site or not specs_compatible(a.specs, b.specs):
                    continue
                # Two different manufacturer part numbers = two different SKUs, however close the names.
                if a.part and b.part and a.part != b.part:
                    continue
                # Phones often come in 4G and 5G versions; one site may just omit "4G".
                if a.category and "phone" in a.category.lower() and a.specs.get("network") != b.specs.get("network"):
                    continue
                # Without RAM/storage on both sides, a name match is too risky.
                if not (a.specs.get("storage_gb") and b.specs.get("storage_gb")):
                    continue
                score = fuzz.token_set_ratio(a.tokens, b.tokens)
                if score >= FUZZY_THRESHOLD:
                    pairs.append((score, fuzz.ratio(a.tokens, b.tokens), a, b))
        for _, _, a, b in sorted(pairs, key=lambda p: (p[0], p[1]), reverse=True):
            merge(a, b, "fuzzy")

    groups = {id(g): g for g in group_of.values()}.values()
    out = [g for g in groups if len(g.sites) >= 2]
    log.info("matching: %d products -> %d cross-site groups (%d by reference, %d fuzzy)",
             len(items), len(out), sum(g.method == "reference" for g in out),
             sum(g.method == "fuzzy" for g in out))
    return out


def save_groups(conn, groups: list[Group], site_order: list[str]) -> None:
    """Rebuild the product_groups table from scratch. History lives per product, so this is safe."""
    rank = {s: i for i, s in enumerate(site_order)}
    with conn.cursor() as cur:
        cur.execute("UPDATE products SET group_id = NULL, match_method = NULL")
        cur.execute("DELETE FROM product_groups")
        for g in groups:
            first = min(g.members, key=lambda m: (rank.get(m.site, 99), len(m.name)))
            key = "-".join(str(i) for i in sorted(m.id for m in g.members))
            gid = cur.execute(
                "INSERT INTO product_groups (canonical_name, match_key) VALUES (%s, %s) RETURNING id",
                (first.name, key),
            ).fetchone()["id"]
            cur.execute("UPDATE products SET group_id = %s, match_method = %s WHERE id = ANY(%s)",
                        (gid, g.method, [m.id for m in g.members]))
    conn.commit()
