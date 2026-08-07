from .base import BaseScraper
from playwright.async_api import async_playwright
import asyncio
import os

class XpressBeesScraper(BaseScraper):
    async def track(self, awb: str) -> dict:
        from browser.playwright_manager import playwright_manager
        url = f"https://trackcourier.io/track-and-trace/xpressbees-logistics/{awb}"
        max_attempts = 2
        
        for attempt in range(1, max_attempts + 1):
            page = None
            try:
                page = await playwright_manager.new_page(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
                # Bypass headless webdriver detection to resolve Proof of Work / Anti-bot blocks
                await page.add_init_script("delete navigator.__proto__.webdriver;")
                
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
                        # Allow images from trackcourier.io domain (logos, etc.)
                        if "trackcourier.io" in url_lower:
                            await route.continue_()
                            return
                        else:
                            await route.abort()
                            return
                    
                    # Block trackers and ads
                    ignored_domains = [
                        "google", "analytics", "doubleclick", "adsense", 
                        "facebook", "fundingchoices", "gstatic", "amazon-adsystem", 
                        "adnxs", "criteo", "pubmatic", "rubiconproject"
                    ]
                    if any(kw in url_lower for kw in ignored_domains):
                        await route.abort()
                        return
                        
                    await route.continue_()
                    
                await page.route("**/*", intercept_route)
                
                # Use domcontentloaded to load page quickly and ignore slow ads/trackers
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                
                # Wait up to 15 seconds for the actual tracking result elements to be attached to the DOM
                await page.wait_for_selector("li.checkpoint.ng-scope, .additional-info:not(:empty)", state="attached", timeout=15000)
                
                # Evaluate and extract the tracking checkpoints using JS
                result = await page.evaluate("""() => {
                    const additionalInfoEl = document.querySelector('.additional-info');
                    const additionalInfo = additionalInfoEl ? additionalInfoEl.innerText.trim() : '';
                    
                    const noInfoEl = Array.from(document.querySelectorAll('.checkpoint__content strong')).find(el => {
                        const style = window.getComputedStyle(el.closest('li') || el);
                        return style.display !== 'none' && !el.closest('.ng-hide') && 
                               (el.innerText.includes('No information') || el.innerText.includes('No information present') || el.innerText.includes('No information is available'));
                    });
                    
                    const checkpoints = [];
                    const items = document.querySelectorAll('li.checkpoint');
                    for (const item of items) {
                        const style = window.getComputedStyle(item);
                        if (style.display === 'none' || item.classList.contains('ng-hide')) {
                            continue;
                        }
                        
                        const timeEl = item.querySelector('.checkpoint__time');
                        const dateEl = item.querySelector('.checkpoint__time strong');
                        const hourEl = item.querySelector('.checkpoint__time .hint');
                        let timeText = '';
                        if (dateEl && hourEl) {
                            timeText = dateEl.innerText.trim() + ' ' + hourEl.innerText.trim();
                        } else if (dateEl) {
                            timeText = dateEl.innerText.trim();
                        } else if (timeEl) {
                            timeText = timeEl.innerText.trim();
                        }
                        const activityEl = item.querySelector('.checkpoint__content strong span:not(.checkpoint__courier-name)');
                        const locationEl = item.querySelector('.checkpoint__content .hint');
                        
                        if (timeText && activityEl) {
                            checkpoints.push({
                                time: timeText,
                                activity: activityEl.innerText.trim(),
                                location: locationEl ? locationEl.innerText.trim() : ''
                            });
                        }
                    }
                    
                    return {
                        success: !noInfoEl,
                        additional_info: additionalInfo,
                        checkpoints: checkpoints
                    };
                }""")
                
                additional_info = result.get("additional_info", "")
                
                # If it's a temporary gateway fetch failure, retry
                if "FAILED TO FETCH" in additional_info.upper() and attempt < max_attempts:
                    await asyncio.sleep(1)
                    continue
                    
                if not result.get("success"):
                    # Double check if it's a fetch failure
                    if "FAILED TO FETCH" in additional_info.upper():
                        return {
                            "status": "Scrape Error",
                            "last_location": "Gateway failed to fetch tracking data. Please retry.",
                            "timestamp": "-"
                        }
                    return {
                        "status": "",
                        "last_location": "",
                        "timestamp": "-"
                    }
                
                checkpoints = result.get("checkpoints", [])
                
                status = "Unknown"
                last_location = "Awaiting scan"
                timestamp = "-"
                
                if checkpoints:
                    import re
                    from datetime import datetime
                    
                    def parse_checkpoint_time(time_str: str) -> datetime:
                        time_str = re.sub(r'\s+', ' ', time_str.strip())
                        if not time_str:
                            return datetime.min
                        formats = [
                            "%d-%b-%Y %H:%M:%S",
                            "%d-%b-%Y %H:%M",
                            "%d-%b-%Y %I:%M %p",
                            "%d-%b-%Y",
                            "%Y-%m-%d %H:%M:%S",
                            "%Y-%m-%d",
                        ]
                        for fmt in formats:
                            try:
                                return datetime.strptime(time_str, fmt)
                            except ValueError:
                                pass
                        return datetime.min
                    
                    # Sort checkpoints oldest to newest
                    checkpoints.sort(key=lambda cp: parse_checkpoint_time(cp.get("time", "")))
                    
                    latest_cp = checkpoints[-1]
                    timestamp = latest_cp.get("time", "-")
                    loc = latest_cp.get("location", "")
                    act = latest_cp.get("activity", "")
                    
                    if loc and act:
                        last_location = f"{loc} ({act})"
                    elif act:
                        last_location = act
                    elif loc:
                        last_location = loc
                        
                    if act:
                        status = act
                
                if (status == "Unknown" or not status) and additional_info:
                    status = additional_info
                    if ":" in additional_info:
                        status = additional_info.split(":")[0].strip()
                        
                # Normalize status for app.py compatibility
                status_lower = status.lower()
                if "delivered" in status_lower:
                    status = "Delivered"
                elif "out for delivery" in status_lower:
                    status = "Out for Delivery"
                elif "in transit" in status_lower or "transit" in status_lower:
                    status = "In Transit"
                elif "picked up" in status_lower:
                    status = "Picked Up"
                elif "out for pickup" in status_lower or "out for pick up" in status_lower:
                    status = "Out for Pickup"
                elif "failed" in status_lower or "undelivered" in status_lower or "unable to deliver" in status_lower:
                    status = "Failed"
                    
                # Take screenshot of the tracking details block
                screenshot_path = f"/static/screenshots/{awb}.png"
                try:
                    import os
                    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    screenshot_file = os.path.join(backend_dir, "static", "screenshots", f"{awb}.png")
                    os.makedirs(os.path.dirname(screenshot_file), exist_ok=True)
                    
                    # Try to capture the specific tracking card container (.block.m-b-2)
                    card = page.locator(".block.m-b-2").first
                    if await card.count() > 0:
                        await card.screenshot(path=screenshot_file)
                    else:
                        await page.screenshot(path=screenshot_file)
                except Exception as screenshot_err:
                    print(f"Failed to capture Xpressbees screenshot for {awb}: {screenshot_err}")
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

