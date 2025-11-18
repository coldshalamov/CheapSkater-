import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto('http://localhost:8000', wait_until='networkidle')
        last=0
        for i in range(20):
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await page.wait_for_timeout(300)
            count = await page.locator('.product-card').count()
            if count != last:
                print(f'batch {i}: {count}')
                last = count
            if count >= 120:
                break
        await browser.close()

asyncio.run(main())
