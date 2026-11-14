from .mytek import MytekScraper
from .spacenet import SpacenetScraper
from .technopro import TechnoproScraper
from .tunisianet import TunisianetScraper
from .zoom import ZoomScraper

SCRAPERS = {
    "tunisianet": TunisianetScraper,
    "spacenet": SpacenetScraper,
    "mytek": MytekScraper,
    "zoom": ZoomScraper,
    "technopro": TechnoproScraper,
}
