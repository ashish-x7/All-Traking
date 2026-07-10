from .ekart import EkartScraper
from .delhivery import DelhiveryScraper
from .bluedart import BlueDartScraper
from .xpressbees import XpressBeesScraper

class ScraperFactory:
    @staticmethod
    def get_scraper(courier_name: str):
        name = courier_name.lower().replace(" ", "").replace("-", "")
        if "ekart" in name:
            return EkartScraper()
        elif "delhivery" in name:
            return DelhiveryScraper()
        elif "bluedart" in name:
            return BlueDartScraper()
        elif "xpressbees" in name:
            return XpressBeesScraper()
        # Fallbacks for other couriers can be added here
        return None


