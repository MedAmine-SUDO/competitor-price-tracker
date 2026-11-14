"""Turning scraped text into clean values."""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation

_SPACES = re.compile(r"[\s   ]+")


def parse_price(text: str | None) -> Decimal | None:
    """'1 099,000 DT' -> Decimal('1099.000'). Returns None when there is no number."""
    if not text:
        return None
    t = _SPACES.sub("", text)
    t = re.sub(r"[^\d,.]", "", t)
    if not t:
        return None
    if "," in t and "." in t:
        # '1.099,000' (dot = thousands) or '1,099.000' (comma = thousands)
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".")
    elif t.count(".") > 1:
        t = t.replace(".", "")
    try:
        value = Decimal(t)
    except InvalidOperation:
        return None
    return value if value > 0 else None


IN_STOCK = ("en stock", "disponible", "in stock", "en magasin")
OUT_OF_STOCK = ("hors stock", "rupture", "épuisé", "epuise", "indisponible", "out of stock", "sur commande")
INCOMING = ("en arrivage", "arrivage", "bientôt", "bientot")


def parse_stock(label: str | None) -> tuple[bool | None, str | None]:
    """Normalize a stock label. Returns (in_stock, clean_label)."""
    if not label:
        return None, None
    clean = _SPACES.sub(" ", label).strip()
    low = clean.lower()
    if any(k in low for k in OUT_OF_STOCK):
        return False, clean
    if any(k in low for k in INCOMING):
        return False, clean
    if any(k in low for k in IN_STOCK):
        return True, clean
    return None, clean


def clean_text(text: str | None) -> str:
    return _SPACES.sub(" ", text or "").strip()


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def normalize_reference(ref: str | None) -> str | None:
    """'[MAXBOOK-X15]' -> 'MAXBOOKX15'. Very short codes are useless for matching."""
    if not ref:
        return None
    r = re.sub(r"[^A-Z0-9]", "", strip_accents(ref).upper())
    return r if len(r) >= 5 else None


# --- product specs, used to avoid matching two variants of the same model ---------------

_GB = r"(\d{1,4})\s*(?:go|gb)\b"
_TB = r"(\d(?:[.,]\d)?)\s*(?:to|tb)\b"


def extract_specs(name: str) -> dict:
    """Pull out the specs that tell variants apart: RAM, storage, CPU, colour-free model tokens."""
    low = strip_accents(name.lower())
    specs: dict = {}

    low = re.sub(r"\b(?:windows|win)\s?1[01]\s?(?:pro|famille|home|s)?\b", " ", low)
    # Graphics card memory ("RTX 3050 4G", "RTX 4060 8Go") is neither RAM nor a network.
    low = re.sub(r"\b(?:rtx|gtx|rx)\s?\d{3,4}\w*(?:\s*(?:ti|super))?(?:\s*\d+\s*(?:go|gb|g)\b)?", " ", low)
    sizes = [int(x) for x in re.findall(_GB, low)]
    sizes += [int(x) for x in re.findall(r"\b(8|12|16|24|32|64|128|256|512)g\b", low)]  # "8G", "512G"
    sizes += [int(float(x.replace(",", ".")) * 1024) for x in re.findall(_TB, low)]
    # The smallest "Go" figure is RAM, the largest is storage (for laptops/phones).
    if len(sizes) >= 2:
        specs["ram_gb"], specs["storage_gb"] = min(sizes), max(sizes)
    elif len(sizes) == 1:
        specs["storage_gb"] = sizes[0]

    cpu = re.search(
        r"\b(i[3579][- ]?\d{4,5}[a-z]{0,2}|ryzen\s?[3579]\s?\d{4}[a-z]{0,2}|n\d{3,4}"
        r"|celeron\s?n?\d{4}|m[1-4](?:\s?(?:pro|max))?)\b",
        low,
    )
    if cpu:
        specs["cpu"] = re.sub(r"[\s-]|celeron", "", cpu.group(1))
    family = re.search(
        r"\b(i[3579]|core\s?[3579]|ultra\s?[579]|ryzen\s?[3579]|celeron|pentium|n\d{3,4}|m[1-4])\b"
        r"|\b(i[3579])-?\d", low)
    if family:
        fam = re.sub(r"\s", "", family.group(1) or family.group(2))
        # Celeron / Pentium / N4500-style chips are one entry-level class; N100, N95... stay distinct.
        if fam in ("celeron", "pentium") or re.fullmatch(r"n\d{4}", fam):
            fam = "intel-entry"
        specs["cpu_family"] = fam
    # Model tier words: a "S26" is not a "S26 Ultra". Compared as a set, absence included.
    no_cpu = re.sub(r"\b(?:core\s)?ultra\s?[3579]\b", " ", low)  # "Core Ultra 7" is a CPU, not a tier
    specs["tier"] = frozenset(w for w in re.findall(r"[a-z]+", no_cpu) if w in TIERS)
    net = set(re.findall(r"\b([45]g)\b", low))
    if len(net) == 1:
        specs["network"] = net.pop()
    colours = {COLOURS[w] for w in re.findall(r"[a-z]+", low) if w in COLOURS}
    if len(colours) == 1:
        specs["colour"] = colours.pop()
    return specs


TIERS = {"pro", "max", "plus", "ultra", "lite", "mini", "fe", "neo", "prime", "edge"}

COLOURS = {
    "noir": "black", "black": "black", "midnight": "black", "graphite": "black",
    "blanc": "white", "white": "white", "starlight": "white",
    "argent": "silver", "silver": "silver", "gris": "grey", "grey": "grey", "gray": "grey",
    "bleu": "blue", "blue": "blue", "vert": "green", "green": "green",
    "rose": "pink", "pink": "pink", "rouge": "red", "red": "red", "violet": "purple",
    "purple": "purple", "gold": "gold", "dore": "gold", "orange": "orange",
    "titanium": "titanium", "titane": "titanium", "jaune": "yellow", "yellow": "yellow",
}


# Spec tokens that look like codes but are not model numbers: CPUs, GPUs, sizes, generations...
_NOT_MODEL = re.compile(
    r"\b(?:windows|win)\s?1[01]\s?(?:pro|famille|home|s)?\b"
    r"|\b(?:rtx|gtx|rx|mx|arc)\s?\d{3,4}\w*"
    r"|\b(?:core\s?)?(?:i[3579]|ultra\s?[3579]|core\s?[3579]|ryzen\s?[3579])[\s-]?\d{3,5}[a-z]{0,2}\b"
    r"|\b[a-z]?\d{3,5}[uhpkgx]{1,2}\b"           # 1315U, 7520U, 13420H, 100U
    r"|\bn\d{3,4}\b|\bcel\w*\s?n?\d{4}\b"
    r"|\b\d+(?:[.,]\d)?\s*(?:go|gb|g|to|tb|mo|mah|hz|w|mp|pouces|\")"
    r"|\b\d{1,2}\s?(?:e|eme|th)?\s?gen\w*"           # 13Gén, 13ème gén
    r"|\b(?:lp)?ddr\d\w*|\bwi-?fi\s?\d\w*|\b[45]g\b|\bw1[01]p?\b")


def model_codes(name: str, reference: str | None = None) -> frozenset[str]:
    """Model numbers found in a name, plus the reference's part number:
    'Dell Pro 15 Essential PV15250 / i5-1334U / 8 Go' -> {'pv15250'}.
    A code has letters and at least 3 digits, so CPUs, sizes and 'S26' are not codes."""
    low = _NOT_MODEL.sub(" ", strip_accents(name.lower()))
    codes = set()
    for tok in re.split(r"[\s/()\[\],|+]+", low):
        tok = re.sub(r"[^a-z0-9]", "", tok)
        if len(tok) >= 5 and re.search(r"[a-z]", tok) and len(re.findall(r"\d", tok)) >= 3:
            codes.add(tok)
    part = part_number(reference)
    if part:
        codes.add(re.sub(r"[^a-z0-9]", "", part.lower()))
    return frozenset(codes)


def codes_compatible(a: frozenset[str], b: frozenset[str]) -> bool:
    """False only when both sides name a model and none agree ('x1502va' agrees with 'x1502vabq905w')."""
    if not a or not b:
        return True
    return any(x.startswith(y) or y.startswith(x) for x in a for y in b)


def part_number(ref: str | None) -> str | None:
    """The leading code of a reference when it looks like a manufacturer part number
    (e.g. '82LX00CEFG-W11P' -> '82LX00CEFG'). Shop-made codes like 'HONOR-T10-4/64' return None."""
    if not ref:
        return None
    head = re.split(r"[-/ _]", ref.strip().upper())[0]
    if len(head) >= 7 and re.search(r"\d", head) and re.search(r"[A-Z]", head):
        return head
    return None


BRANDS = (
    "apple", "asus", "acer", "dell", "hp", "lenovo", "msi", "samsung", "xiaomi", "redmi", "poco",
    "oppo", "realme", "infinix", "tecno", "huawei", "honor", "nokia", "itel", "vivo", "motorola",
    "bmax", "gigabyte", "microsoft", "toshiba", "chuwi", "alcatel", "zte", "oneplus", "google",
    "evertek", "logicom", "iku", "geant", "condor", "nothing", "blackview", "doogee", "ulefone",
)
BRAND_ALIASES = {"redmi": "xiaomi", "poco": "xiaomi", "iphone": "apple", "macbook": "apple", "galaxy": "samsung"}


def guess_brand(name: str) -> str | None:
    words = re.findall(r"[a-z0-9]+", strip_accents(name.lower()))
    for w in words[:8]:
        if w in BRAND_ALIASES:
            return BRAND_ALIASES[w]
        if w in BRANDS:
            return w
    return None


NOISE_WORDS = {
    "pc", "portable", "ordinateur", "laptop", "smartphone", "telephone", "mobile", "tunisie",
    "en", "de", "avec", "et", "le", "la", "les", "pour", "windows", "win", "go", "gb", "to", "tb",
    "ssd", "hdd", "ram", "ecran", "noir", "gris", "blanc", "bleu", "vert", "rose", "silver",
    "black", "grey", "gray", "white", "blue", "green", "gold", "argent", "dore", "violet",
    "purple", "rouge", "red", "midnight", "starlight", "titanium", "sac", "offert", "cadeau",
    "garantie", "an", "ans", "dual", "sim", "4g", "5g", "lte", "wifi", "fhd", "hd", "full",
}


def name_tokens(name: str) -> str:
    """A cleaned, comparable version of a product name for fuzzy matching."""
    low = strip_accents(name.lower())
    low = re.sub(r"\b(?:windows|win)\s?1[01]\s?(?:pro|famille|home|s)?\b", " ", low)
    low = re.sub(r"\b\d+(?:[.,]\d)?\s*(?:go|gb|to|tb|mo|mah|hz|g|w)\b", " ", low)
    low = re.sub(r"[^a-z0-9]+", " ", low)
    # Sizes ("8go", "512gb", "1to") are compared separately as specs; brands are blocked on.
    return " ".join(
        w for w in low.split()
        if w not in NOISE_WORDS and w not in COLOURS and w not in BRANDS and w not in BRAND_ALIASES
        and not re.fullmatch(r"\d+(?:go|gb|to|tb|mo|mah|hz|w)", w)
    )
