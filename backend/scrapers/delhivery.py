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
    async def track(self, awb: str) -> dict:
        try:
            # Execute the network call in a thread pool to avoid blocking the asyncio event loop
            res_json = await asyncio.to_thread(fetch_delhivery, awb)
            if not res_json.get("data"):
                return {
                    "status": "",
                    "last_location": "",
                    "timestamp": "-"
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
