from .base import BaseScraper
from playwright.async_api import async_playwright
import re

class EkartScraper(BaseScraper):
    async def track(self, awb: str) -> dict:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            url = f"https://www.ekartlogistics.com/ekartlogistics-web/shipmenttrack/{awb}"
            try:
                # Go to the url and wait until no more network activity
                await page.goto(url, wait_until="networkidle")
                
                # Fetch text content to see if the record is valid
                text = await page.evaluate("() => document.body.innerText")
                
                if "No tracking data available" in text:
                    return {
                        "status": "Invalid AWB",
                        "last_location": "No record found on Ekart",
                        "timestamp": "-"
                    }
                
                # Parse status
                status = "Unknown"
                status_match = re.search(r"Current Status:\s*([^\n]+)", text)
                if status_match:
                    status = status_match.group(1).strip()
                
                # Parse tracking details table
                tables = await page.locator("table").all()
                last_location = "Awaiting scan"
                timestamp = "-"
                
                if tables:
                    rows = await tables[0].locator("tr").all()
                    if len(rows) > 1:
                        # get the last row
                        last_row = rows[-1]
                        cols = await last_row.locator("td").all_text_contents()
                        if len(cols) >= 4:
                            date = cols[0].strip()
                            time_str = cols[1].strip()
                            place = cols[2].strip()
                            status_detail = cols[3].strip()
                            
                            last_location = f"{place} ({status_detail})"
                            timestamp = f"{date} {time_str}"
                            if status == "Unknown":
                                status = status_detail
                
                return {
                    "status": status,
                    "last_location": last_location,
                    "timestamp": timestamp
                }
                
            except Exception as e:
                return {
                    "status": "Scrape Error",
                    "last_location": f"Error: {str(e)}",
                    "timestamp": "-"
                }
            finally:
                await browser.close()

