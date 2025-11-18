import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto('http://localhost:8000', wait_until='networkidle')
        script1 = await page.evaluate("Array.from(document.scripts).map(s => s.innerHTML)[1]")
        non=[(i, ord(ch), ch) for i,ch in enumerate(script1) if ord(ch)>127]
        print('non count', len(non))
        if non:
            print(non[:20])
        with open('tmp_script1.js','w',encoding='utf-8') as f:
            f.write(script1)
        await browser.close()

asyncio.run(main())
