import asyncio
import urllib.request
import json
import ssl
from datetime import datetime
from .base import BaseScraper

def fetch_delhivery(awb: str) -> dict:
    url = f"https://dlv-api.delhivery.com/v3/unified-tracking-new?wbn={awb}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.delhivery.com",
        "Referer": f"https://www.delhivery.com/track/package/{awb}"
    }
    req = urllib.request.Request(url, headers=headers)
    context = ssl._create_unverified_context()
    # 10 second timeout for safety
    with urllib.request.urlopen(req, context=context, timeout=10) as response:
        return json.loads(response.read().decode())

class DelhiveryScraper(BaseScraper):
    async def track(self, awb: str, capture_screenshot: bool = False) -> dict:
        try:
            # Execute the network call in a thread pool to avoid blocking the asyncio event loop
            res_json = await asyncio.to_thread(fetch_delhivery, awb)
            if not res_json.get("data"):
                return {
                    "status": "",
                    "last_location": "",
                    "timestamp": "-",
                    "screenshot": "-"
                }
            
            data = res_json["data"][0]
            
            # Map status
            hq_status = data.get("hqStatus", "Unknown")
            status_obj = data.get("status", {})
            instructions = status_obj.get("instructions")
            
            if data.get("currentFlow") == "Returned" or status_obj.get("status") == "DELIVERED_SELLER":
                status = "Returned"
            elif status_obj.get("status") == "DELIVERED" or hq_status == "DELIVERED":
                status = "Delivered"
            else:
                status = instructions if instructions else hq_status
            
            # Parse timestamp from statusDateTime
            timestamp = "-"
            status_date_time = status_obj.get("statusDateTime")
            if status_date_time:
                try:
                    dt = datetime.fromisoformat(status_date_time.split(".")[0])
                    timestamp = dt.strftime("%d-%b-%Y %I:%M %p")  # e.g., "07-Jul-2026 12:26 PM"
                except Exception:
                    pass
            
            # Fallback for timestamp
            if timestamp == "-" and data.get("deliveryDate_v1"):
                v1_label = data["deliveryDate_v1"]
                if "on " in v1_label:
                    timestamp = v1_label.split("on ")[-1].strip()
            
            # Parse last location
            last_location = ""
            scans = []
            for state in (data.get("trackingStates") or []):
                for scan in (state.get("scans") or []):
                    scans.append(scan)
            
            if scans:
                # The trackingStates are ordered chronologically (oldest to newest),
                # so the latest scan is the last element in the list.
                latest_scan = scans[-1]
                scanned_loc = latest_scan.get("scannedLocation") or latest_scan.get("cityLocation")
                if scanned_loc:
                    last_location = scanned_loc
            
            # If screenshot not requested, return immediately in super-fast mode (0.2s)
            if not capture_screenshot:
                return {
                    "status": status,
                    "last_location": last_location,
                    "timestamp": timestamp,
                    "screenshot": "-"
                }
            
            # Take screenshot in background using playwright if requested
            screenshot_path = f"/static/screenshots/{awb}.png"
            try:
                import os
                from browser.playwright_manager import playwright_manager
                backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                screenshot_file = os.path.join(backend_dir, "static", "screenshots", f"{awb}.png")
                os.makedirs(os.path.dirname(screenshot_file), exist_ok=True)
                page = await playwright_manager.new_page(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
                await page.add_init_script("delete navigator.__proto__.webdriver;")
                
                # Block ads/trackers but allow stylesheets & first-party images for nice screenshots
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
                        if "delhivery.com" in url_lower:
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
                
                await page.goto(f"https://www.delhivery.com/track/package/{awb}", wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(2.5) # Wait for page rendering
                
                # Try to capture the main tracking panel if present
                card = page.locator(".track-card, .package-card, .status-card, #track-container, .container").first
                if await card.count() > 0:
                    await card.screenshot(path=screenshot_file)
                else:
                    await page.screenshot(path=screenshot_file)
                await page.close()
            except Exception as e:
                print(f"Failed to capture Delhivery screenshot for {awb}: {e}")
                screenshot_path = "-"

            return {
                "status": status,
                "last_location": last_location,
                "timestamp": timestamp,
                "screenshot": screenshot_path
            }
        except Exception as e:
            return {
                "status": "Scrape Error",
                "last_location": f"Error: {str(e)}",
                "timestamp": "-"
            }
