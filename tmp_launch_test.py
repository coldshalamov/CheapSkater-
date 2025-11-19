import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=False)
        page = await b.new_page()
        await page.goto('https://example.com')
        await asyncio.sleep(5)
        await b.close()
asyncio.run(main())
