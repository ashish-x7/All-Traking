import asyncio
from scrapers.xpressbees import XpressBeesScraper

async def test():
    scraper = XpressBeesScraper()
    res = await scraper.track("14187461420018")
    print("Result:", res)

asyncio.run(test())
