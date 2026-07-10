from .base import BaseScraper
from playwright.async_api import async_playwright
import asyncio
import os

class BlueDartScraper(BaseScraper):
    async def track(self, awb: str) -> dict:
        from browser.playwright_manager import playwright_manager
        url = f"https://trackcourier.io/track-and-trace/blue-dart/{awb}"
        max_attempts = 2
        
        for attempt in range(1, max_attempts + 1):
            page = None
            try:
                page = await playwright_manager.new_page(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
                # Bypass headless webdriver detection to resolve Proof of Work / Anti-bot blocks
                await page.add_init_script("delete navigator.__proto__.webdriver;")
                
                # Intercept and block ads, stylesheets, fonts, images, and trackers to save memory/CPU and speed up load times
                async def intercept_route(route):
                    req = route.request
                    res_type = req.resource_type
                    url_lower = req.url.lower()
                    
                    # Block assets we don't need for data parsing
                    if res_type in ["image", "media", "font", "stylesheet"]:
                        await route.abort()
                        return
                    
                    # Block trackers and ads
                    ignored_domains = ["google", "analytics", "doubleclick", "adsense", "facebook", "fundingchoices", "gstatic"]
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
                        
                        const timeEl = item.querySelector('.checkpoint__time strong');
                        const activityEl = item.querySelector('.checkpoint__content strong span:not(.checkpoint__courier-name)');
                        const locationEl = item.querySelector('.checkpoint__content .hint');
                        
                        if (timeEl && activityEl) {
                            checkpoints.push({
                                time: timeEl.innerText.trim(),
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
                        "status": "Invalid AWB",
                        "last_location": "No record found on Blue Dart",
                        "timestamp": "-"
                    }
                
                checkpoints = result.get("checkpoints", [])
                
                status = "Unknown"
                last_location = "Awaiting scan"
                timestamp = "-"
                
                if additional_info:
                    status = additional_info
                    if ":" in additional_info:
                        status = additional_info.split(":")[0].strip()
                
                if checkpoints:
                    latest_cp = checkpoints[0]
                    timestamp = latest_cp.get("time", "-")
                    loc = latest_cp.get("location", "")
                    act = latest_cp.get("activity", "")
                    
                    if loc and act:
                        last_location = f"{loc} ({act})"
                    elif act:
                        last_location = act
                    elif loc:
                        last_location = loc
                        
                    if status == "Unknown" and act:
                        status = act
                        
                return {
                    "status": status,
                    "last_location": last_location,
                    "timestamp": timestamp
                }
                
            except Exception as e:
                # Capture debug screenshot on Render to see if it's blocked by Cloudflare/Captcha
                try:
                    os.makedirs("static", exist_ok=True)
                    await page.screenshot(path="static/screenshot.png")
                except:
                    pass
                    
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
