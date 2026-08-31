from .base import BaseScraper
import asyncio
import re
import json
import requests
from datetime import datetime

def fetch_ekart(awb: str) -> dict:
    session = requests.Session()
    page_url = f"https://www.ekartlogistics.com/ekartlogistics-web/shipmenttrack/{awb}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    }
    
    r_page = session.get(page_url, headers=headers, timeout=10)
    csrf_match = re.search(r'name="csrf-token"\s+content="([^"]+)"', r_page.text)
    csrf_token = csrf_match.group(1) if csrf_match else ""
    
    api_url = "https://www.ekartlogistics.com/ekartlogistics-web-routes-api/ekartlogistics-web-proxy/trackings/v2"
    api_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": page_url,
        "content-type": "application/json",
        "csrf-token": csrf_token,
        "x-user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 EKCL/website/1"
    }
    payload = {"tracking_ids": awb}
    
    r_api = session.post(api_url, json=payload, headers=api_headers, timeout=10)
    if r_api.status_code != 200:
        return {
            "status": "",
            "last_location": "",
            "timestamp": "-"
        }
    
    data = r_api.json()
    shipment_info = data.get(awb)
    
    if not shipment_info or not isinstance(shipment_info, dict):
        return {
            "status": "",
            "last_location": "",
            "timestamp": "-"
        }
    
    tracking_details = shipment_info.get("shipmentTrackingDetails", [])
    if not tracking_details:
        return {
            "status": "No tracking details",
            "last_location": "",
            "timestamp": "-"
        }
    
    # Sort details by date timestamp ascending
    sorted_details = sorted(tracking_details, key=lambda x: x.get("date", 0))
    latest_event = sorted_details[-1]
    
    status_detail = (latest_event.get("statusDetails") or "").strip()
    city = (latest_event.get("city") or "").strip()
    event_timestamp_ms = latest_event.get("date")
    
    timestamp = "-"
    if event_timestamp_ms:
        try:
            dt = datetime.fromtimestamp(event_timestamp_ms / 1000)
            timestamp = dt.strftime("%d-%b-%Y %I:%M %p")
        except Exception:
            pass
            
    if city and status_detail:
        last_location = f"{city} ({status_detail})"
    elif city:
        last_location = city
    else:
        last_location = status_detail or "Awaiting scan"
    
    # Status normalization
    status = status_detail or "In Transit"
    status_lower = status.lower()
    if "delivered" in status_lower and "unsuccessful" not in status_lower and "undelivered" not in status_lower:
        status = "Delivered"
    elif "out for delivery" in status_lower:
        status = "Out for Delivery"
    elif "rto" in status_lower or "reject" in status_lower or "returned" in status_lower:
        status = status_detail
    elif "dispatched" in status_lower or "received at" in status_lower or "in transit" in status_lower:
        status = status_detail
    
    return {
        "status": status,
        "last_location": last_location,
        "timestamp": timestamp,
        "screenshot": "-"
    }

class EkartScraper(BaseScraper):
    async def track(self, awb: str, capture_screenshot: bool = False) -> dict:
        try:
            res = await asyncio.to_thread(fetch_ekart, awb)
            
            # If screenshot not requested, return immediately in super-fast mode (0.3s)
            if not capture_screenshot:
                res["screenshot"] = "-"
                return res
            
            # Optional screenshot capture via Playwright
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
                await page.goto(f"https://www.ekartlogistics.com/ekartlogistics-web/shipmenttrack/{awb}", wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(2.5)
                
                panel = page.locator(".tracking-panel, .card, .container, #track-container").first
                if await panel.count() > 0:
                    await panel.screenshot(path=screenshot_file)
                else:
                    await page.screenshot(path=screenshot_file)
                await page.close()
                res["screenshot"] = screenshot_path
            except Exception:
                res["screenshot"] = "-"
                
            return res
        except Exception as e:
            return {
                "status": "Scrape Error",
                "last_location": f"Error: {str(e)}",
                "timestamp": "-",
                "screenshot": "-"
            }

