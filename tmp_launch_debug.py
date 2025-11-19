import asyncio
from playwright.async_api import async_playwright
from app.playwright_env import launch_browser, apply_stealth, close_browser

async def main():
    async with async_playwright() as p:
        apply_stealth(p)
        browser, ctx = await launch_browser(p)
        print('launch result', bool(browser), bool(ctx))
        page = None
        if ctx is not None:
            page = await ctx.new_page()
        else:
            page = await browser.new_context()
        new_ctx = None
        if hasattr(page, 'goto'):
            await page.goto('https://example.com')
            print('title', await page.title())
            await page.close()
        await close_browser(browser, ctx)

asyncio.run(main())
