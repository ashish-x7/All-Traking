import asyncio
import sys
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        api_responses = []
        page.on("response", lambda response: api_responses.append(response) if "shipment" in response.url or "track" in response.url or "api" in response.url else None)
        
        await page.goto("https://www.ekartlogistics.com/", wait_until="networkidle")
        
        awb = "MY5C1314502865"
        await page.locator("input[placeholder*='Enter Tracking ID']").fill(awb)
        await page.get_by_role("button", name="TRACK", exact=True).click()
        
        await page.wait_for_timeout(5000)
        
        print("Page URL after search:", page.url)
        print("Page Title:", await page.title())
        body_text = await page.evaluate("() => document.body.innerText")
        print("Page Text contains 'No tracking data':", "No tracking data" in body_text)
        print("Page Text contains 'Current Status':", "Current Status" in body_text)
        print("\nFull page text preview:")
        print(body_text[:1000])
        
        print("\n--- Captured Responses ---")
        for resp in api_responses:
            if "css" in resp.url or "js" in resp.url or "png" in resp.url:
                continue
            print(f"URL: {resp.url}")
            print(f"Status: {resp.status}")
            try:
                text = await resp.text()
                print(f"Response: {text[:200]}")
            except Exception as e:
                print("Could not read text")
                
        await browser.close()

asyncio.run(run())
