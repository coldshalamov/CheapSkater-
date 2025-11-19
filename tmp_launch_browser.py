import asyncio
from app.playwright_env import launch_browser
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser, ctx = await launch_browser(p)
        page = await (ctx.new_page() if ctx else browser.new_page())
        await page.goto('https://example.com')
        print('title', await page.title())
        await browser.close()
asyncio.run(main())
