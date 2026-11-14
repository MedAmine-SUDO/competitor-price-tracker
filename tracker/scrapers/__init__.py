from .mytek import MytekScraper
from .spacenet import SpacenetScraper
from .tunisianet import TunisianetScraper

SCRAPERS = {
    "tunisianet": TunisianetScraper,
    "spacenet": SpacenetScraper,
    "mytek": MytekScraper,
}
