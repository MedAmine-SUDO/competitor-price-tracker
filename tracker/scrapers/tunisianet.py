from .base import PrestaShopScraper


class TunisianetScraper(PrestaShopScraper):
    site = "tunisianet"
    card_selector = "article.product-miniature"
    name_selector = "h2.product-title a"
    reference_selector = "span.product-reference"   # "[MAXBOOK-X15]"
    stock_selector = "#stock_availability"
