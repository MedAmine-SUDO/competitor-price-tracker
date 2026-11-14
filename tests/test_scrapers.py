"""Card parsing on small hand-written HTML that mirrors each site's markup.
(No real site data is stored in the repository.)"""
from decimal import Decimal

from tracker.scrapers.mytek import MytekScraper
from tracker.scrapers.spacenet import SpacenetScraper
from tracker.scrapers.tunisianet import TunisianetScraper

TUNISIANET = """
<article class="product-miniature js-product-miniature" data-id-product="111">
  <h2 class="h3 product-title"><a href="https://shop.example/pc/111-demo.html">Pc Portable DEMO X1 / i5 / 8 Go / 512 Go SSD</a></h2>
  <span class="product-reference">[DEMO-X1-I5]</span>
  <div class="product-price-and-shipping">
    <span class="price">1 179,000 DT</span><span class="regular-price">1 299,000 DT</span>
  </div>
  <div id="stock_availability"><span class="in-stock">En stock</span></div>
</article>
<article class="product-miniature js-product-miniature" data-id-product="112">
  <h2 class="h3 product-title"><a href="https://shop.example/pc/112-demo.html?foo=1">Pc Portable DEMO X2</a></h2>
  <div class="product-price-and-shipping"><span class="price">999,000 DT</span></div>
</article>
<article class="product-miniature js-product-miniature" data-id-product="113">
  <h2 class="h3 product-title"><a href="https://shop.example/pc/113.html">Broken card without price</a></h2>
</article>
"""

SPACENET = """
<div class="product-miniature js-product-miniature" data-id-product="222">
  <div class="product-reference"><label class="label">Réf : </label><span>DEMO-PHONE-4/64-BK</span></div>
  <h2 class="product_name"><a href="https://shop.example/222-phone.html"> Smartphone Demo 4Go 64Go Noir</a></h2>
  <div class="product-price-and-shipping"><span class="regular-price">529,000 DT</span>
     <span class="discount-amount">-40,000 DT</span><span class="price">489,000 DT</span></div>
  <div class="product-quantities"><label class="label-available">En Arrivage</label></div>
</div>
<div class="product-miniature js-product-miniature" data-id-product="222">
  <h2 class="product_name"><a href="https://shop.example/222-phone.html">duplicate render</a></h2>
  <div class="product-price-and-shipping"><span class="price">489,000 DT</span></div>
</div>
"""

MYTEK = """
<div class="product-container card h-100"><div class="shimmer-wrapper skeleton-title"></div></div>
<div class="product-container card h-100" data-product-id="333">
  <h1 class="product-item-name"><a class="product-item-link" href="https://shop.example/pc-demo.html"> PC Portable Demo Z 16Go 1To </a></h1>
  <div class="sku">[ZDEMO-16-1T]</div>
  <div class="price-box"><span class="final-price text-danger">2499.000 DT</span>
    <span class="original-price">2799.000 DT</span></div>
  <div class="availability"><h4>Disponibilité</h4><div class="stock instock"><span>En stock</span></div></div>
</div>
"""


def test_tunisianet_cards():
    items = TunisianetScraper({}).parse_listing(TUNISIANET, "PC portable")
    assert [i.site_product_id for i in items] == ["111", "112"]  # broken card skipped
    promo = items[0]
    assert promo.price == Decimal("1299.000") and promo.promo_price == Decimal("1179.000")
    assert promo.reference == "DEMO-X1-I5" and promo.in_stock is True
    assert items[1].promo_price is None and items[1].url.endswith("112-demo.html")


def test_spacenet_cards_dedupe_and_stock():
    items = SpacenetScraper({}).parse_listing(SPACENET, "Smartphone")
    assert len(items) == 1
    it = items[0]
    assert it.price == Decimal("529.000") and it.promo_price == Decimal("489.000")
    assert it.in_stock is False and it.stock_label == "En Arrivage"


def test_mytek_cards():
    items = MytekScraper({}).parse_listing(MYTEK, "PC portable")
    assert len(items) == 1
    it = items[0]
    assert it.site_product_id == "333"
    assert it.price == Decimal("2799") and it.promo_price == Decimal("2499")
    assert it.reference == "ZDEMO-16-1T" and it.in_stock is True


def test_pagination_url():
    s = TunisianetScraper({})
    assert s.page_url("https://shop.example/301-pc", 3) == "https://shop.example/301-pc?page=3"
