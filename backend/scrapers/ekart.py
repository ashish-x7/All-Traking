from .base import BaseScraper
from playwright.async_api import async_playwright
import re

class EkartScraper(BaseScraper):
    async def track(self, awb: str) -> dict:
        from browser.playwright_manager import playwright_manager
        url = f"https://www.ekartlogistics.com/ekartlogistics-web/shipmenttrack/{awb}"
        max_attempts = 2
        
        for attempt in range(1, max_attempts + 1):
            page = None
            try:
                page = await playwright_manager.new_page(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
                
                # Intercept to block ads/trackers but allow stylesheets & first-party images for nice screenshots
                async def intercept_route(route):
                    req = route.request
                    res_type = req.resource_type
                    url_lower = req.url.lower()
                    
                    # Allow stylesheets so the screenshot layout is styled correctly.
                    # Block media and fonts to save bandwidth.
                    if res_type in ["media", "font"]:
                        await route.abort()
                        return
                        
                    # Only block images if they are ads/third-party
                    if res_type == "image":
                        if "ekartlogistics.com" in url_lower:
                            await route.continue_()
                            return
                        else:
                            await route.abort()
                            return
                    
                    # Block trackers and ads
                    ignored_domains = [
                        "google", "analytics", "doubleclick", "adsense", 
                        "facebook", "fundingchoices", "gstatic", "amazon-adsystem"
                    ]
                    if any(kw in url_lower for kw in ignored_domains):
                        await route.abort()
                        return
                        
                    await route.continue_()
                await page.route("**/*", intercept_route)
                
                # Go to the url and wait until no more network activity
                await page.goto(url, wait_until="networkidle")
                
                # Fetch text content to see if the record is valid
                text = await page.evaluate("() => document.body.innerText")
                
                if "No tracking data available" in text:
                    return {
                        "status": "",
                        "last_location": "",
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
                
                # Take screenshot of the tracking card/table container
                screenshot_path = f"/static/screenshots/{awb}.png"
                try:
                    import os
                    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    screenshot_file = os.path.join(backend_dir, "static", "screenshots", f"{awb}.png")
                    os.makedirs(os.path.dirname(screenshot_file), exist_ok=True)
                    
                    # Try to capture the main tracking panel if present
                    panel = page.locator(".tracking-panel, .card, .container").first
                    if await panel.count() > 0:
                        await panel.screenshot(path=screenshot_file)
                    else:
                        await page.screenshot(path=screenshot_file)
                except Exception as screenshot_err:
                    print(f"Failed to capture Ekart screenshot for {awb}: {screenshot_err}")
                    screenshot_path = "-"

                return {
                    "status": status,
                    "last_location": last_location,
                    "timestamp": timestamp,
                    "screenshot": screenshot_path
                }
                
            except Exception as e:
                if attempt < max_attempts:
                    await asyncio.sleep(1)
                    continue
                return {
                    "status": "Scrape Error",
                    "last_location": f"Error: {str(e)}",
                    "timestamp": "-"
                }
            finally:
                if page:
                    try:
                        await page.close()
                    except:
                        pass

