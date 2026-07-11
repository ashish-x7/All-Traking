import asyncio
import sys
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        captured_apis = []
        page.on("response", lambda resp: captured_apis.append(resp) if "api" in resp.url or "ajax" in resp.url or "json" in resp.url or "track" in resp.url else None)
        
        # Load trackcourier page for xpressbees
        url = "https://trackcourier.io/track-and-trace/xpressbees-logistics/14187461420018"
        await page.goto(url, wait_until="networkidle")
        
        print("Page loaded. URL:", page.url)
        print("\n--- Captured Requests ---")
        for resp in captured_apis:
            if "google" in resp.url or "analytics" in resp.url or "facebook" in resp.url:
                continue
            print(f"URL: {resp.url}")
            print(f"Status: {resp.status}")
            try:
                text = await resp.text()
                print("Response Preview:", text[:300])
            except Exception:
                print("Could not read body")
                
        await browser.close()

asyncio.run(run())
