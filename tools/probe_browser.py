"""Check whether a normal JavaScript-enabled browser can read the public viewer."""
import asyncio
import sys
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout


async def main():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page()
            response = await page.goto(sys.argv[1], wait_until='domcontentloaded', timeout=30000)
            try:
                await page.wait_for_function("document.querySelector('script#__NEXT_DATA__') !== null", timeout=30000)
            except PlaywrightTimeout:
                print('Browser response:', response.status if response else None)
                print('Browser page title:', await page.title())
                print('Visible page:', (await page.locator('body').inner_text())[:1200])
                raise RuntimeError('The ordinary browser did not receive the public viewer. No interactive verification was attempted.')
            data = await page.locator('script#__NEXT_DATA__').text_content()
            import json
            deck = json.loads(data)['props']['pageProps']['slideshow']
            print('Browser received viewer:', deck['title'], 'slides:', deck['totalSlides'], 'private:', deck['isPrivate'])
        finally:
            await browser.close()


asyncio.run(main())

