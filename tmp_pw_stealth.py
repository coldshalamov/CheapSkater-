import asyncio
from app.playwright_env import apply_stealth, launch_kwargs
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        apply_stealth(p)
        kwargs=launch_kwargs();
        browser=await p.chromium.launch(**kwargs)
        page=await browser.new_page()
        await page.goto('https://example.com')
        print('ok stealth', await page.title())
        await browser.close()
asyncio.run(main())
