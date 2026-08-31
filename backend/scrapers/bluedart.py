from .base import BaseScraper
import asyncio
import os
import re
import urllib.request
from datetime import datetime

def fetch_bluedart(awb: str) -> dict:
    url = f"https://www.bluedart.com/trackdartresult?trackFor=0&trackNo={awb}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=12) as response:
        html = response.read().decode('utf-8', errors='ignore')
        
    if "No record found" in html or "Invalid Waybill" in html or "No records found" in html or "No information is available" in html:
        return {
            "status": "Invalid AWB / Not Found",
            "last_location": "No tracking data available",
            "timestamp": "-",
            "screenshot": "-"
        }
        
    scans = []
    
    # Locate Status and Scans section
    idx = html.find("Status and Scans")
    search_html = html[idx:] if idx != -1 else html
    
    # Match all <tr> that have 4 <td> elements
    row_matches = re.finditer(r'<tr[^>]*>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>', search_html, re.DOTALL | re.IGNORECASE)
    for m in row_matches:
        cols = [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', c)).strip() for c in m.groups()]
        loc, detail, date_str, time_str = cols[0], cols[1], cols[2], cols[3]
        if detail and ("Shipment" in detail or "Delivered" in detail or "Connected" in detail or "Arrived" in detail or "Out" in detail or "Picked" in detail or "RTO" in detail or "In Transit" in detail):
            scans.append({
                "location": loc,
                "details": detail,
                "date": date_str,
                "time": time_str
            })
            
    status = ""
    last_location = ""
    timestamp = "-"
    
    if scans:
        latest = scans[0]
        status_text = latest["details"]
        loc_text = latest["location"]
        date_str = latest["date"]
        time_str = latest["time"]
        
        if date_str:
            full_time = f"{date_str} {time_str}".strip()
            try:
                dt = datetime.strptime(full_time, "%d %b %Y %H:%M")
                timestamp = dt.strftime("%d-%b-%Y %I:%M %p")
            except Exception:
                timestamp = full_time
                
        st_lower = status_text.lower()
        if "delivered" in st_lower and "undelivered" not in st_lower:
            status = "Delivered"
        elif "out for delivery" in st_lower:
            status = "Out for Delivery"
        elif "in transit" in st_lower or "arrived" in st_lower or "connected" in st_lower:
            status = "In Transit"
        elif "picked" in st_lower:
            status = "Picked Up"
        elif "rto" in st_lower or "return" in st_lower:
            status = "Returned"
        else:
            status = status_text
            
        if loc_text and status_text:
            last_location = f"{loc_text} ({status_text})"
        elif loc_text:
            last_location = loc_text
        else:
            last_location = status_text
            
    # Fallback to Summary Table if scans table was empty
    if not status:
        sum_match = re.search(r'Status\s*</td>\s*<td[^>]*>(.*?)</td>', html, re.DOTALL | re.IGNORECASE)
        if sum_match:
            clean_sum = re.sub(r'<[^>]+>', '', sum_match.group(1)).strip()
            status = "Delivered" if "delivered" in clean_sum.lower() else clean_sum
            last_location = "Location available in summary"
            
    return {
        "status": status or "Pending",
        "last_location": last_location or "Awaiting scan",
        "timestamp": timestamp,
        "screenshot": "-"
    }

class BlueDartScraper(BaseScraper):
    async def track(self, awb: str, capture_screenshot: bool = False) -> dict:
        try:
            # Fast direct fetch via official Blue Dart tracking page
            res = await asyncio.to_thread(fetch_bluedart, awb)
            
            # If screenshot not requested, return immediately in super-fast mode
            if not capture_screenshot:
                res["screenshot"] = "-"
                return res
                
            # Optional screenshot capture via Playwright
            screenshot_path = f"/static/screenshots/{awb}.png"
            try:
                from browser.playwright_manager import playwright_manager
                backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                screenshot_file = os.path.join(backend_dir, "static", "screenshots", f"{awb}.png")
                os.makedirs(os.path.dirname(screenshot_file), exist_ok=True)
                
                page = await playwright_manager.new_page(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
                await page.add_init_script("delete navigator.__proto__.webdriver;")
                await page.goto(f"https://www.bluedart.com/trackdartresult?trackFor=0&trackNo={awb}", wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(1.5)
                
                card = page.locator(".panel-group, #accordion, table").first
                if await card.count() > 0:
                    await card.screenshot(path=screenshot_file)
                else:
                    await page.screenshot(path=screenshot_file)
                await page.close()
                res["screenshot"] = screenshot_path
            except Exception as ss_err:
                print(f"Failed to capture BlueDart screenshot for {awb}: {ss_err}")
                res["screenshot"] = "-"
                
            return res
        except Exception as e:
            return {
                "status": "Scrape Error",
                "last_location": f"Error: {str(e)}",
                "timestamp": "-",
                "screenshot": "-"
            }

