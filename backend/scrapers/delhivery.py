from .base import BaseScraper
from playwright.async_api import async_playwright
import re

class DelhiveryScraper(BaseScraper):
    async def track(self, awb: str) -> dict:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            url = f"https://www.delhivery.com/track/package/{awb}"
            try:
                await page.goto(url, wait_until="networkidle")
                text = await page.evaluate("() => document.body.innerText")
                
                if "404 Error" in text or "wrong route" in text:
                    return {
                        "status": "Invalid AWB",
                        "last_location": "No record found on Delhivery",
                        "timestamp": "-"
                    }
                
                # Try to extract status and timestamp from timeline first (lines containing '|')
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                timeline_events = []
                
                for i, line in enumerate(lines):
                    if line == '|' and i > 0 and i + 1 < len(lines):
                        event_status = lines[i-1]
                        event_time = lines[i+1]
                        timeline_events.append((event_status, event_time))
                
                status = "Unknown"
                timestamp = "-"
                
                if timeline_events:
                    # Use the latest event from the timeline
                    latest_status, latest_time = timeline_events[-1]
                    status = latest_status
                    timestamp = latest_time
                else:
                    # Fallback 1: Extract status using "Your order has been"
                    status_match = re.search(r"Your order has been\s*([^\n]+)", text, re.IGNORECASE)
                    if status_match:
                        status = status_match.group(1).strip()
                    else:
                        for i, line in enumerate(lines):
                            if line == "Order Details" and i + 1 < len(lines):
                                status = lines[i+1]
                                break
                    
                    # Fallback 2: Extract timestamp using "on Date" pattern
                    time_match = re.search(r"([A-Za-z\s]+) on (\d{2}\s+[A-Za-z]{3})", text)
                    if time_match:
                        timestamp = time_match.group(2).strip()
                        if status == "Unknown":
                            status = time_match.group(1).strip()
                
                last_location = f"Delhivery Network ({status})"
                
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

