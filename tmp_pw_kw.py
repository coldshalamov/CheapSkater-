import asyncio
from app.playwright_env import launch_kwargs
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        kwargs=launch_kwargs();
        print('kwargs', kwargs)
        browser=await p.chromium.launch(**kwargs)
        page=await browser.new_page()
        await page.goto('https://example.com')
        print('ok', await page.title())
        await browser.close()
asyncio.run(main())
