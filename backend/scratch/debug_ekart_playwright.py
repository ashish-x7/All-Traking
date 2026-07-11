import asyncio
import sys
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Intercept requests to /ws/getTrackingDetails
        target_request = None
        async def on_request(request):
            nonlocal target_request
            if "getTrackingDetails" in request.url:
                target_request = request
                print("\n--- Captured Request ---")
                print("URL:", request.url)
                print("Method:", request.method)
                print("Headers:", request.headers)
                print("Post Data:", request.post_data)
                
        page.on("request", on_request)
        
        # Go to ekart homepage and track
        await page.goto("https://www.ekartlogistics.com/", wait_until="networkidle")
        
        awb = "MY5C1314502865"
        await page.locator("input[placeholder*='Enter Tracking ID']").fill(awb)
        await page.locator("input[placeholder*='Enter Tracking ID']").press("Enter")
        
        # Wait a bit for the API call to trigger and load
        await page.wait_for_timeout(6000)
        
        if target_request:
            # Let's inspect response
            response = await page.goto(page.url) # trigger reload or read from cache
            body_text = await page.evaluate("() => document.body.innerText")
            print("\nPage text preview:")
            print(body_text[:1000])
        else:
            print("Did not capture any request to getTrackingDetails.")
            
        await browser.close()

asyncio.run(run())
