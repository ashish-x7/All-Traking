from playwright.async_api import async_playwright, Playwright, Browser, Page
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
        # Keep get_browser for compatibility
        if self._browser is None or not self._browser.is_connected:
            # We call new_page logic to initialize
            await self.new_page()
        return self._browser

    async def new_page(self, **kwargs) -> Page:
        async with self._lock:
            for attempt in range(2):
                try:
                    # Check connection
                    if self._browser is not None:
                        is_conn = False
                        try:
                            is_conn = self._browser.is_connected
                        except:
                            pass
                        if not is_conn:
                            try:
                                await self._browser.close()
                            except:
                                pass
                            self._browser = None

                    # Launch if not exists
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
                    
                    return await self._browser.new_page(**kwargs)
                except Exception as e:
                    print(f"PlaywrightManager new_page exception (attempt {attempt+1}): {e}")
                    # If it's the first attempt, close and reset browser to force relaunch
                    if attempt == 0:
                        try:
                            if self._browser:
                                await self._browser.close()
                        except:
                            pass
                        self._browser = None
                    else:
                        raise e

    async def close_browser(self):
        async with self._lock:
            if self._browser:
                try:
                    await self._browser.close()
                except:
                    pass
                self._browser = None
            if self._playwright:
                try:
                    await self._playwright.stop()
                except:
                    pass
                self._playwright = None

# Global instance helper
playwright_manager = PlaywrightManager()
