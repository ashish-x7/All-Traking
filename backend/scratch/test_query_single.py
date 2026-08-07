import asyncio
import sys
import os

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure Windows event loop policy
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from scrapers.shadowfax import ShadowfaxScraper

async def main():
    print("Testing ShadowfaxScraper with updated screenshot details for AWB R2107976294AJI...")
    scraper = ShadowfaxScraper()
    result = await scraper.track("R2107976294AJI")
    print("\n--- SCRAPING RESULT ---")
    print(result)
    print("------------------------")
    
    backend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "screenshots", "R2107976294AJI.png")
    print("Screenshot exists in backend/static/screenshots?:", os.path.exists(backend_path))
    if os.path.exists(backend_path):
        print("Screenshot size in bytes:", os.path.getsize(backend_path))

if __name__ == "__main__":
    asyncio.run(main())
