import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        # Go to ekart homepage
        await page.goto("https://www.ekartlogistics.com/", wait_until="networkidle")
        print("Page Title:", await page.title())
        
        # Let's inspect the page inputs
        inputs = await page.locator("input").all()
        for idx, inp in enumerate(inputs):
            print(f"Input {idx}: placeholder='{await inp.get_attribute('placeholder')}', name='{await inp.get_attribute('name')}', id='{await inp.get_attribute('id')}'")
        
        # Let's inspect buttons
        buttons = await page.locator("button").all()
        for idx, btn in enumerate(buttons):
            print(f"Button {idx}: text='{await btn.inner_text()}', type='{await btn.get_attribute('type')}'")
            
        # Try direct link as well to see what happens
        await page.goto("https://www.ekartlogistics.com/ekartlogistics-web/shipmenttrack/MY5C1314502865", wait_until="networkidle")
        print("Direct URL Title:", await page.title())
        body_text = await page.evaluate("() => document.body.innerText")
        print("Direct URL Text preview:", body_text[:500])
        
        await browser.close()

asyncio.run(run())
