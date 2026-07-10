from playwright.async_api import async_playwright, Playwright, Browser
import asyncio

class PlaywrightManager:
    _instance = None
    _lock = asyncio.Lock()
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(PlaywrightManager, cls).__new__(cls)
            cls._instance._playwright = None
            cls._instance._browser = None
        return cls._instance

    async def get_browser(self) -> Browser:
        async with self._lock:
            # If browser is disconnected or crashed, reset it
            if self._browser is not None and not self._browser.is_connected:
                try:
                    await self._browser.close()
                except:
                    pass
                self._browser = None

            if self._browser is None:
                if self._playwright is None:
                    self._playwright = await async_playwright().start()
                
                # Launch single browser instance with optimized flags to avoid Render OOM crashes
                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-accelerated-2d-canvas',
                        '--no-first-run',
                        '--no-zygote',
                        '--single-process',
                        '--disable-gpu'
                    ]
                )
            return self._browser

    async def close_browser(self):
        async with self._lock:
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None

# Global instance helper
playwright_manager = PlaywrightManager()
