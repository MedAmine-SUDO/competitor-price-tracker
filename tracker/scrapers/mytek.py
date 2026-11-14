from bs4 import Tag

from ..parsing import clean_text, guess_brand, parse_price, parse_stock
from .base import Listing, Scraper


class MytekScraper(Scraper):
    """Mytek renders its product grid with JavaScript, so pages are loaded with Playwright
    (engine: browser in config/sites.yaml). Until the script runs, the grid only holds
    empty skeleton cards; `wait_selector` makes the browser wait for real ones."""

    site = "mytek"
    card_selector = "div.product-container[data-product-id]"
    wait_selector = "div.product-container .product-item-link"

    def parse_card(self, card: Tag, category: str) -> Listing | None:
        pid = card.get("data-product-id")
        link = card.select_one("a.product-item-link")
        final = card.select_one(".final-price")
        if not (pid and link and final):
            return None
        current = parse_price(final.get_text())
        old = card.select_one(".original-price")
        regular = parse_price(old.get_text()) if old else None
        if current is None:
            return None
        price, promo = (regular, current) if regular and regular > current else (current, None)
        sku = card.select_one(".sku")
        stock = card.select_one(".stock")
        in_stock, label = parse_stock(stock.get_text(" ") if stock else None)
        name = clean_text(link.get_text())
        return Listing(
            site=self.site, site_product_id=str(pid), url=link["href"].split("?")[0], name=name,
            price=price, promo_price=promo, in_stock=in_stock, stock_label=label,
            reference=clean_text(sku.get_text()).strip("[] ") or None if sku else None,
            brand=guess_brand(name), category=category,
        )
