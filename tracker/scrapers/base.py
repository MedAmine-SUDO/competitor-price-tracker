"""Shared scraper logic: walk category pages, parse product cards, stop when pages run out."""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from decimal import Decimal
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

from bs4 import BeautifulSoup, Tag

from ..fetch import BotChallenge, DisallowedByRobots, FetchError
from ..parsing import clean_text, guess_brand, parse_price, parse_stock

log = logging.getLogger("tracker.scraper")


@dataclass
class Listing:
    site: str
    site_product_id: str
    url: str
    name: str
    price: Decimal               # regular price
    promo_price: Decimal | None  # None if not discounted
    in_stock: bool | None
    stock_label: str | None
    reference: str | None
    brand: str | None
    category: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class CategoryResult:
    category: str
    pages: int = 0
    listings: int = 0
    errors: list[str] | None = None


class Scraper:
    site: str = ""
    card_selector: str = ""

    def __init__(self, site_cfg: dict):
        self.cfg = site_cfg
        self.paginate = site_cfg.get("paginate", True)

    # -- to implement per site -------------------------------------------------------
    def parse_card(self, card: Tag, category: str) -> Listing | None:
        raise NotImplementedError

    def page_url(self, url: str, page: int) -> str:
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query))
        query["page"] = str(page)
        return urlunsplit(parts._replace(query=urlencode(query)))

    def has_next_page(self, html: str) -> bool | None:
        """True/False when the page says whether a next page exists, None when it can't tell."""
        return None

    # -- shared -----------------------------------------------------------------------
    def parse_listing(self, html: str, category: str) -> list[Listing]:
        soup = BeautifulSoup(html, "lxml")
        out: list[Listing] = []
        for card in soup.select(self.card_selector):
            try:
                item = self.parse_card(card, category)
            except Exception as exc:  # one broken card must not lose the page
                log.warning("%s: skipped a card (%s)", self.site, exc)
                continue
            if item:
                out.append(item)
        # Some themes render each card twice (desktop + mobile layout).
        unique: dict[str, Listing] = {}
        for item in out:
            unique.setdefault(item.site_product_id, item)
        return list(unique.values())

    def scrape_category(self, fetcher, cat: dict) -> tuple[list[Listing], CategoryResult]:
        name, url = cat["name"], cat["url"]
        max_pages = cat.get("max_pages", 50) if self.paginate else 1
        result = CategoryResult(category=name, errors=[])
        items: list[Listing] = []
        seen_ids: set[str] = set()
        saw_next_link = False

        for page in range(1, max_pages + 1):
            page_url = url if page == 1 else self.page_url(url, page)
            try:
                html = fetcher.get(page_url)
            except BotChallenge:
                raise
            except DisallowedByRobots:
                log.info("%s: robots.txt disallows %s, stopping category", self.site, page_url)
                break
            except FetchError as exc:
                log.error("%s: %s", self.site, exc)
                result.errors.append(str(exc))
                if page == 1:
                    break
                continue
            result.pages += 1
            page_items = self.parse_listing(html, name)
            new = [i for i in page_items if i.site_product_id not in seen_ids]
            # Past the last page, PrestaShop shows the last page again: nothing new = done.
            if not new:
                break
            seen_ids.update(i.site_product_id for i in new)
            items.extend(new)
            log.info("%s | %-12s | page %2d | %3d products", self.site, name, page, len(new))
            # Trust a missing "next" link only once the theme has shown one: some sites answer
            # HTTP 500 past the last page instead of repeating it.
            has_next = self.has_next_page(html)
            saw_next_link = saw_next_link or bool(has_next)
            if saw_next_link and has_next is False:
                break

        result.listings = len(items)
        if not items and not result.errors:
            result.errors.append(f"{name}: 0 products parsed (selectors may have changed)")
        return items, result


class PrestaShopScraper(Scraper):
    """Tunisianet, Spacenet, Zoom and Technopro all run PrestaShop with small theme differences."""

    card_selector = "article.product-miniature, div.product-miniature"
    name_selector = ".product-title a, .product_name a"
    reference_selector = ".product-reference"
    stock_selector = "#stock_availability, .product-quantities"
    price_selector = ".product-price-and-shipping .price, .price"

    def has_next_page(self, html: str) -> bool | None:
        nav = BeautifulSoup(html, "lxml").select_one("nav.pagination, .pagination")
        if nav is None:
            return None
        return nav.select_one('a[rel~="next"], a.next') is not None

    def parse_card(self, card: Tag, category: str) -> Listing | None:
        pid = card.get("data-id-product")
        link = card.select_one(self.name_selector)
        price_el = card.select_one(self.price_selector)
        if not (pid and link and price_el):
            return None
        current = parse_price(price_el.get_text())
        regular_el = card.select_one(".regular-price")
        regular = parse_price(regular_el.get_text()) if regular_el else None
        if current is None:
            return None
        if regular and regular > current:
            price, promo = regular, current
        else:
            price, promo = current, None

        ref_el = card.select_one(self.reference_selector)
        ref = None
        if ref_el:
            span = ref_el.select_one("span")
            ref = clean_text((span or ref_el).get_text()).strip("[] ") or None

        stock_el = card.select_one(self.stock_selector)
        in_stock, stock_label = parse_stock(stock_el.get_text(" ") if stock_el else None)

        name = clean_text(link.get_text())
        return Listing(
            site=self.site, site_product_id=str(pid), url=link["href"].split("?")[0], name=name,
            price=price, promo_price=promo, in_stock=in_stock, stock_label=stock_label,
            reference=ref, brand=guess_brand(name), category=category,
        )
