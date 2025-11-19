import asyncio
from app.playwright_env import launch_browser, apply_stealth
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        apply_stealth(p)
        browser, ctx = await launch_browser(p)
        print('browser', browser)
        page = await browser.new_page()
        await page.goto('https://example.com')
        print('title', await page.title())
        await browser.close()
asyncio.run(main())
