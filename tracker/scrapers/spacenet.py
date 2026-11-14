from .base import PrestaShopScraper


class SpacenetScraper(PrestaShopScraper):
    site = "spacenet"
    card_selector = "div.product-miniature"
    name_selector = "h2.product_name a"
    reference_selector = "div.product-reference"    # <label>Réf :</label><span>CODE</span>
    stock_selector = "div.product-quantities"
