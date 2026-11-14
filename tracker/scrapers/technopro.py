from .base import PrestaShopScraper


class TechnoproScraper(PrestaShopScraper):
    site = "technopro"
    card_selector = "article.product-miniature"
    reference_selector = "div.product-reference"    # plain text: <div class="product-reference">CODE</div>
    stock_selector = "div.product-availability"
    price_selector = ".product-price-and-shipping .product-price"   # no .price class on this theme
