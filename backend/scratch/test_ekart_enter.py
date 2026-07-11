import asyncio
import sys
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Go to ekart homepage
        await page.goto("https://www.ekartlogistics.com/", wait_until="networkidle")
        
        awb = "MY5P1420031892"
        # Fill tracking ID
        await page.locator("input[placeholder*='Enter Tracking ID']").fill(awb)
        # Press Enter key to submit form
        await page.locator("input[placeholder*='Enter Tracking ID']").press("Enter")
        
        # Wait for either navigation or results container
        await page.wait_for_timeout(6000)
        
        print("Page URL after Enter:", page.url)
        body_text = await page.evaluate("() => document.body.innerText")
        print("\nFull page text preview:")
        print(body_text[:1000])
        
        # Check tables on the page
        tables = await page.locator("table").all()
        print(f"Found {len(tables)} tables on page.")
        if tables:
            rows = await tables[0].locator("tr").all()
            for idx, r in enumerate(rows):
                text_content = await r.inner_text()
                print(f"Row {idx}: {text_content.strip()}")
                
        await browser.close()

asyncio.run(run())
