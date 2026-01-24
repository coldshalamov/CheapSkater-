import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        page.on('pageerror', lambda exc: print('pageerror:', getattr(exc, 'message', exc)))
        page.on('console', lambda msg: print('console', msg.type, msg.text))
        await page.goto('http://localhost:8000', wait_until='networkidle')
        await page.wait_for_timeout(1000)
        await browser.close()

asyncio.run(main())
