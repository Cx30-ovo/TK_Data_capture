"""Bootstrap a dedicated Douyin tab without navigating existing user websites."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

import config
from api.services import monitor_service as module
from api.services.monitor_service import MonitorService
from media_platform.douyin.core import DouYinCrawler
from media_platform.douyin.exception import DataFetchError


def make_page(url, name=""):
    page = MagicMock(url=url)
    page.evaluate = AsyncMock(return_value=name)
    page.goto = AsyncMock()
    page.bring_to_front = AsyncMock()
    return page


def make_crawler(pages):
    crawler = DouYinCrawler()
    context = MagicMock()
    context.pages = pages
    context.new_page = AsyncMock(return_value=make_page("about:blank"))
    crawler.browser_context = context
    return crawler, context


@pytest.mark.asyncio
@pytest.mark.parametrize("landing", ["chrome://newtab/", "chrome://newtab", "chrome://new-tab-page/", "about:blank"])
async def test_startup_reuses_empty_chrome_tab_without_opening_another(landing):
    new_tab = make_page(landing)
    webui = make_page("http://localhost:5173/", "MediaCrawler")
    crawler, context = make_crawler([webui, new_tab])
    assert await crawler._get_or_create_context_page(bootstrap=True) is new_tab
    context.new_page.assert_not_awaited()
    webui.evaluate.assert_not_awaited()
    webui.goto.assert_not_awaited()


@pytest.mark.asyncio
async def test_startup_creates_missing_douyin_tab_but_keeps_webui():
    webui = make_page("http://localhost:5173/", "MediaCrawler")
    unrelated = make_page("https://example.com/")
    crawler, context = make_crawler([webui, unrelated])
    selected = await crawler._get_or_create_context_page(bootstrap=True)
    assert selected is context.new_page.return_value
    context.new_page.assert_awaited_once()
    webui.evaluate.assert_not_awaited()
    unrelated.evaluate.assert_not_awaited()
    assert webui.url == "http://localhost:5173/"


@pytest.mark.asyncio
async def test_startup_prefers_existing_douyin_tab_and_keeps_its_account_page():
    webui = make_page("http://localhost:5173/", "MediaCrawler")
    new_tab = make_page("chrome://newtab/")
    douyin = make_page("https://www.douyin.com/user/test")
    crawler, context = make_crawler([webui, new_tab, douyin])
    assert await crawler._get_or_create_context_page(bootstrap=True) is douyin
    context.new_page.assert_not_awaited()
    webui.evaluate.assert_not_awaited()
    new_tab.evaluate.assert_not_awaited()


@pytest.mark.asyncio
async def test_collection_still_requires_existing_douyin_tab():
    crawler, context = make_crawler([make_page("chrome://newtab/"), make_page("http://localhost:5173/")])
    with pytest.raises(DataFetchError, match="不会跳转 WebUI"):
        await crawler._get_or_create_context_page()
    context.new_page.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("headless", [False, True])
async def test_browser_preparation_bootstraps_tab_and_preserves_shared_browser(monkeypatch, headless):
    page = make_page("chrome://newtab/")
    crawler = MagicMock()
    crawler.index_url = "https://www.douyin.com"
    crawler._get_or_create_context_page = AsyncMock(return_value=page)
    manager = MagicMock()
    manager.launch_and_connect = AsyncMock(return_value=object())
    manager.cleanup = AsyncMock()

    @asynccontextmanager
    async def playwright_context():
        yield object()

    @asynccontextmanager
    async def lease():
        yield

    monkeypatch.setattr(config, "CDP_HEADLESS", headless)
    monkeypatch.setattr(module, "async_playwright", playwright_context)
    monkeypatch.setattr(module, "DouyinTabLease", lease)
    monkeypatch.setattr(module, "CDPBrowserManager", lambda **kw: manager)
    monkeypatch.setattr(module, "DouYinCrawler", lambda: crawler)
    goto = AsyncMock()
    monkeypatch.setattr(module, "safe_page_goto", goto)
    monkeypatch.setattr(module.crawler_manager, "add_log", AsyncMock())
    service = MonitorService()
    monkeypatch.setattr(service, "_crawler_is_busy", lambda: False)
    assert await service.ensure_browser_ready() == {"status": "ok"}
    crawler._get_or_create_context_page.assert_awaited_once_with(bootstrap=True)
    goto.assert_awaited_once_with(page, crawler.index_url, accepted_hosts=("douyin.com",))
    if headless:
        page.bring_to_front.assert_not_awaited()
    else:
        page.bring_to_front.assert_awaited_once()
    manager.cleanup.assert_awaited_once()


@pytest.mark.asyncio
async def test_startup_prepares_browser_before_monitor_and_scheduler(monkeypatch):
    from api import main

    events = []

    def record(event):
        async def action(*args, **kwargs):
            events.append(event)
        return action

    monkeypatch.setattr(config, "START_BROWSER_ON_SERVICE_START", True)
    monkeypatch.setattr(main.db, "init_db", record("database"))
    monkeypatch.setattr(main.monitor_service, "ensure_browser_ready", record("browser"))
    monkeypatch.setattr(main.monitor_service, "start", record("monitor"))
    monkeypatch.setattr(main.scheduler_service, "start", record("scheduler"))
    monkeypatch.setattr(main.maintenance_service, "start", record("maintenance"))
    monkeypatch.setattr(main.monitor_service, "stop", AsyncMock())
    monkeypatch.setattr(main.scheduler_service, "stop", AsyncMock())
    monkeypatch.setattr(main.maintenance_service, "stop", AsyncMock())
    async with main.lifespan(MagicMock()):
        assert events == ["database", "browser", "scheduler", "monitor", "maintenance"]
