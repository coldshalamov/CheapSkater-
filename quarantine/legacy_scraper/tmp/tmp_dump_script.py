import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto('http://localhost:8000', wait_until='networkidle')
        scripts = await page.evaluate("Array.from(document.scripts).map(s => s.innerHTML)")
        for idx, script in enumerate(scripts):
            if len(script.strip())==0:
                continue
            print('script', idx, 'length', len(script.strip()))
            if idx==1:
                print(script)
        await browser.close()

asyncio.run(main())
