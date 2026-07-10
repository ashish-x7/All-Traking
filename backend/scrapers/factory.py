from .ekart import EkartScraper
from .delhivery import DelhiveryScraper

class ScraperFactory:
    @staticmethod
    def get_scraper(courier_name: str):
        name = courier_name.lower().replace(" ", "").replace("-", "")
        if "ekart" in name:
            return EkartScraper()
        elif "delhivery" in name:
            return DelhiveryScraper()
        # Fallbacks for other couriers can be added here
        return None

