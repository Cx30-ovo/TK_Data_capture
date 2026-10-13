"""One background collection tab in the existing Chrome login context."""

import asyncio
from contextlib import suppress
from urllib.parse import urlsplit

from playwright.async_api import Error as PlaywrightError

from tools.douyin_browser_coordinator import DouyinTabLease


COLLECTION_TAB_NAME = "MediaCrawlerCollection"
_MARK_TAB = f"window.name = '{COLLECTION_TAB_NAME}';"


async def is_collection_page(page):
    if page.is_closed():
        return False
    host = urlsplit(page.url).hostname or ""
    if page.url != "about:blank" and not (host == "douyin.com" or host.endswith(".douyin.com")):
        return False
    try:
        return await page.evaluate("() => window.name") == COLLECTION_TAB_NAME
    except PlaywrightError:
        return False


async def _create_background_page(context, timeout=10):
    pages_before = set(context.pages)
    anchor = next((page for page in context.pages if not page.is_closed()), None)
    if anchor is None:
        # A fresh, empty context has no user's selected tab to disturb.
        return await context.new_page()

    changed = asyncio.Event()
    def on_page(page):
        changed.set()

    session = await context.new_cdp_session(anchor)
    context.on("page", on_page)
    target_id = None
    try:
        info = (await session.send("Target.getTargetInfo"))["targetInfo"]
        params = {"url": "about:blank", "background": True, "newWindow": False}
        if info.get("browserContextId"):
            params["browserContextId"] = info["browserContextId"]
        target_id = (await session.send("Target.createTarget", params))["targetId"]
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            changed.clear()
            for page in context.pages:
                if page in pages_before or page.is_closed():
                    continue
                probe = await context.new_cdp_session(page)
                try:
                    target = (await probe.send("Target.getTargetInfo"))["targetInfo"]
                    if target["targetId"] == target_id:
                        return page
                finally:
                    await probe.detach()
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError("后台采集页签创建超时")
            try:
                await asyncio.wait_for(changed.wait(), remaining)
            except asyncio.TimeoutError as exc:
                raise TimeoutError("后台采集页签创建超时") from exc
    except BaseException:
        if target_id:
            # Only the target we just created may be removed on failure.
            with suppress(PlaywrightError):
                await session.send("Target.closeTarget", {"targetId": target_id})
        raise
    finally:
        context.remove_listener("page", on_page)
        with suppress(PlaywrightError):
            await session.detach()


async def get_collection_page(context):
    # The same lease is held by monitor operations and standalone crawlers, so
    # separate Playwright connections cannot race to create duplicate tabs.
    async with DouyinTabLease():
        for page in context.pages:
            if await is_collection_page(page):
                return page
        page = await _create_background_page(context)
        try:
            await page.add_init_script(_MARK_TAB)
            await page.evaluate(_MARK_TAB)
        except BaseException:
            with suppress(PlaywrightError):
                await page.close()
            raise
        return page
