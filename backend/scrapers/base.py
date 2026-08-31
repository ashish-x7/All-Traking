class BaseScraper:
    async def track(self, awb: str, capture_screenshot: bool = False) -> dict:
        raise NotImplementedError

