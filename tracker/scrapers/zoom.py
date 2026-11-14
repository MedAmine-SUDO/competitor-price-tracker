from .base import PrestaShopScraper


class ZoomScraper(PrestaShopScraper):
    site = "zoom"
    card_selector = "div.product-miniature"
    name_selector = "h5.product-name a"
    stock_selector = "div.product-availability"     # no reference code on Zoom's cards
