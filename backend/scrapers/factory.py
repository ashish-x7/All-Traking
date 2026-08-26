from .ekart import EkartScraper
from .delhivery import DelhiveryScraper
from .bluedart import BlueDartScraper
from .xpressbees import XpressBeesScraper
from .shadowfax import ShadowfaxScraper

class ScraperFactory:
    @staticmethod
    def get_scraper(courier_name: str):
        if not courier_name:
            return None
        name = str(courier_name).lower().replace(" ", "").replace("-", "").replace("_", "")
        if "ekart" in name or "ekl" in name or "myntra" in name or "mysc" in name:
            return EkartScraper()
        elif "delhivery" in name:
            return DelhiveryScraper()
        elif "bluedart" in name or "blue" in name:
            return BlueDartScraper()
        elif "xpressbees" in name or "xpress" in name or "xb" in name:
            return XpressBeesScraper()
        elif "shadowfax" in name or "sf" in name:
            return ShadowfaxScraper()
        # Fallbacks for other couriers can be added here
        return None


