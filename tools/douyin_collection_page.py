"""One background collection tab in the existing Chrome login context."""

import asyncio
import json
from contextlib import suppress
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import Error as PlaywrightError

from tools.douyin_browser_coordinator import DouyinTabLease


COLLECTION_TAB_NAME = "MediaCrawlerCollection"
_MARK_TAB = f"window.name = '{COLLECTION_TAB_NAME}';"
_TARGET_FILE = Path(__file__).resolve().parents[1] / "browser_data" / "douyin-collection-target.json"


async def is_collection_page(page):
    if page.is_closed():
        return False
    host = urlsplit(page.url).hostname or ""
    if page.url != "about:blank" and not (host == "douyin.com" or host.endswith(".douyin.com")):
        return False
    try:
        return await asyncio.wait_for(page.evaluate("() => window.name"), 3) == COLLECTION_TAB_NAME
    except (PlaywrightError, TimeoutError):
        return False


async def _target_id(context, page):
    session = await asyncio.wait_for(context.new_cdp_session(page), 5)
    try:
        return (await asyncio.wait_for(session.send("Target.getTargetInfo"), 5))["targetInfo"]["targetId"]
    finally:
        with suppress(PlaywrightError, TimeoutError):
            await asyncio.wait_for(session.detach(), 5)


def _remembered_target():
    try:
        data = json.loads(_TARGET_FILE.read_text())
        return data.get("target_id") if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


async def reset_collection_page(context):
    """Replace only an owned collection target, even when its renderer is stuck."""
    async with DouyinTabLease():
        remembered = _remembered_target()
        for page in context.pages:
            if page.is_closed():
                continue
            own_target = remembered and await _target_id(context, page) == remembered
            if own_target or await is_collection_page(page):
                # CDP closes an unresponsive renderer without relying on its JS.
                session = await asyncio.wait_for(context.new_cdp_session(page), 5)
                try:
                    await asyncio.wait_for(session.send("Target.closeTarget", {"targetId": await _target_id(context, page)}), 5)
                finally:
                    with suppress(PlaywrightError, TimeoutError):
                        await asyncio.wait_for(session.detach(), 5)
        with suppress(FileNotFoundError):
            _TARGET_FILE.unlink()


async def _create_background_page(context, timeout=10):
    pages_before = set(context.pages)
    anchor = next((page for page in context.pages if not page.is_closed()), None)
    if anchor is None:
        # A fresh, empty context has no user's selected tab to disturb.
        return await asyncio.wait_for(context.new_page(), timeout)

    changed = asyncio.Event()
    def on_page(page):
        changed.set()

    session = await asyncio.wait_for(context.new_cdp_session(anchor), timeout)
    context.on("page", on_page)
    target_id = None
    try:
        info = (await asyncio.wait_for(session.send("Target.getTargetInfo"), timeout))["targetInfo"]
        params = {"url": "about:blank", "background": True, "newWindow": False}
        if info.get("browserContextId"):
            params["browserContextId"] = info["browserContextId"]
        target_id = (await asyncio.wait_for(session.send("Target.createTarget", params), timeout))["targetId"]
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            changed.clear()
            for page in context.pages:
                if page in pages_before or page.is_closed():
                    continue
                probe = await asyncio.wait_for(context.new_cdp_session(page), 5)
                try:
                    target = (await asyncio.wait_for(probe.send("Target.getTargetInfo"), 5))["targetInfo"]
                    if target["targetId"] == target_id:
                        return page
                finally:
                    with suppress(PlaywrightError, TimeoutError):
                        await asyncio.wait_for(probe.detach(), 5)
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
            with suppress(PlaywrightError, TimeoutError):
                await asyncio.wait_for(session.send("Target.closeTarget", {"targetId": target_id}), 5)
        raise
    finally:
        context.remove_listener("page", on_page)
        with suppress(PlaywrightError, TimeoutError):
            await asyncio.wait_for(session.detach(), 5)


async def get_collection_page(context):
    # The same lease is held by monitor operations and standalone crawlers, so
    # separate Playwright connections cannot race to create duplicate tabs.
    async with DouyinTabLease():
        remembered = _remembered_target()
        for page in context.pages:
            host = urlsplit(page.url).hostname or ""
            if remembered and not page.is_closed() and (page.url == "about:blank" or host == "douyin.com" or host.endswith(".douyin.com")):
                if await _target_id(context, page) == remembered:
                    return page
            if await is_collection_page(page):
                target_id = await _target_id(context, page)
                _TARGET_FILE.parent.mkdir(parents=True, exist_ok=True)
                _TARGET_FILE.write_text(json.dumps({"target_id": target_id}))
                return page
        page = await _create_background_page(context)
        try:
            await asyncio.wait_for(page.add_init_script(_MARK_TAB), 5)
            await asyncio.wait_for(page.evaluate(_MARK_TAB), 5)
            target_id = await _target_id(context, page)
            _TARGET_FILE.parent.mkdir(parents=True, exist_ok=True)
            _TARGET_FILE.write_text(json.dumps({"target_id": target_id}))
        except BaseException:
            with suppress(PlaywrightError, TimeoutError):
                await asyncio.wait_for(page.close(), 5)
            raise
        return page
