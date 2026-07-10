from .base import BaseScraper
from playwright.async_api import async_playwright

class BlueDartScraper(BaseScraper):
    async def track(self, awb: str) -> dict:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            # Use trackcourier.io to bypass Blue Dart's official captcha requirement
            url = f"https://trackcourier.io/track-and-trace/blue-dart-courier/{awb}"
            try:
                await page.goto(url, wait_until="networkidle")
                
                # Wait up to 10 seconds for the checkpoints to load
                try:
                    await page.wait_for_selector(".additional-info, li.checkpoint:not(.ng-hide), .checkpoint__content:has-text('No information')", timeout=10000)
                except:
                    pass
                
                # Evaluate and extract the tracking checkpoints using JS
                result = await page.evaluate("""() => {
                    const additionalInfoEl = document.querySelector('.additional-info');
                    const additionalInfo = additionalInfoEl ? additionalInfoEl.innerText.trim() : '';
                    
                    const noInfoEl = Array.from(document.querySelectorAll('.checkpoint__content strong')).find(el => {
                        const style = window.getComputedStyle(el.closest('li') || el);
                        return style.display !== 'none' && !el.closest('.ng-hide') && 
                               (el.innerText.includes('No information') || el.innerText.includes('No information present') || el.innerText.includes('No information is available'));
                    });
                    if (noInfoEl) {
                        return { success: false, error: 'No information present' };
                    }

                    
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
                        success: true,
                        additional_info: additionalInfo,
                        checkpoints: checkpoints
                    };
                }""")
                
                if not result.get("success"):
                    return {
                        "status": "Invalid AWB",
                        "last_location": "No record found on Blue Dart",
                        "timestamp": "-"
                    }
                
                additional_info = result.get("additional_info", "")
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
                return {
                    "status": "Scrape Error",
                    "last_location": f"Error: {str(e)}",
                    "timestamp": "-"
                }
            finally:
                await browser.close()
