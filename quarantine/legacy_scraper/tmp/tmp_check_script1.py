import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto('http://localhost:8000', wait_until='networkidle')
        scripts = await page.evaluate("Array.from(document.scripts).map(s => ({type:s.type||'text/javascript', text:s.innerHTML}))")
        for idx,s in enumerate(scripts):
            if idx==1:
                try:
                    await page.evaluate("new Function(`" + s['text'].replace('`','\\`') + "`);")
                    print('script1 ok')
                except Exception as exc:
                    print('script1 fail', exc)
        await browser.close()

asyncio.run(main())
