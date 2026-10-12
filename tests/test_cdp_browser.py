# -*- coding: utf-8 -*-
from unittest.mock import AsyncMock, MagicMock

import pytest

import config
from tools.cdp_browser import CDPBrowserManager


def test_platform_profile_uses_isolated_port_and_user_data_files(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    manager = CDPBrowserManager(profile_platform="dy")

    assert manager._port_file == tmp_path / "browser_data" / "cdp_debug_port_dy.txt"
    assert manager._profile_user_data_dir() == tmp_path / "browser_data" / "cdp_dy_user_data_dir"


@pytest.mark.asyncio
async def test_platform_profile_does_not_reuse_unrelated_default_port(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "CDP_DEBUG_PORT", 9222)
    manager = CDPBrowserManager(profile_platform="dy")
    manager._test_cdp_connection = AsyncMock(return_value=True)  # type: ignore[method-assign]
    manager._get_browser_websocket_url = AsyncMock(return_value="ws://unrelated")  # type: ignore[method-assign]

    assert await manager._find_reusable_browser_port() is None
    manager._test_cdp_connection.assert_not_awaited()


@pytest.mark.asyncio
async def test_existing_browser_connects_directly_to_devtools_browser(monkeypatch):
    monkeypatch.setattr(config, "CDP_CONNECT_EXISTING", True)
    monkeypatch.setattr(config, "BROWSER_LAUNCH_TIMEOUT", 60)

    manager = CDPBrowserManager()
    manager.debug_port = 9222
    manager._get_browser_websocket_url = AsyncMock(  # type: ignore[method-assign]
        side_effect=AssertionError("existing browser mode must not call /json/version")
    )

    browser = MagicMock()
    browser.is_connected.return_value = True
    browser.contexts = []

    playwright = MagicMock()
    playwright.chromium.connect_over_cdp = AsyncMock(return_value=browser)

    await manager._connect_via_cdp(playwright)

    playwright.chromium.connect_over_cdp.assert_awaited_once_with(
        "ws://localhost:9222/devtools/browser",
        timeout=60000,
    )


@pytest.mark.asyncio
async def test_existing_browser_falls_back_to_discovered_websocket_url(monkeypatch):
    monkeypatch.setattr(config, "CDP_CONNECT_EXISTING", True)
    monkeypatch.setattr(config, "BROWSER_LAUNCH_TIMEOUT", 60)

    manager = CDPBrowserManager()
    manager.debug_port = 9222
    manager._get_browser_websocket_url = AsyncMock(  # type: ignore[method-assign]
        return_value="ws://localhost:9222/devtools/browser/generated-id"
    )

    browser = MagicMock()
    browser.is_connected.return_value = True
    browser.contexts = []

    playwright = MagicMock()
    playwright.chromium.connect_over_cdp = AsyncMock(
        side_effect=[RuntimeError("direct websocket failed"), browser]
    )

    await manager._connect_via_cdp(playwright)

    manager._get_browser_websocket_url.assert_awaited_once_with(9222)
    assert playwright.chromium.connect_over_cdp.await_args_list[0].args == (
        "ws://localhost:9222/devtools/browser",
    )
    assert playwright.chromium.connect_over_cdp.await_args_list[0].kwargs == {
        "timeout": 60000,
    }
    assert playwright.chromium.connect_over_cdp.await_args_list[1].args == (
        "ws://localhost:9222/devtools/browser/generated-id",
    )
    assert playwright.chromium.connect_over_cdp.await_args_list[1].kwargs == {
        "timeout": 60000,
    }


@pytest.mark.asyncio
async def test_launched_browser_uses_discovered_websocket_url(monkeypatch):
    monkeypatch.setattr(config, "CDP_CONNECT_EXISTING", False)

    manager = CDPBrowserManager()
    manager.debug_port = 9223
    manager._get_browser_websocket_url = AsyncMock(  # type: ignore[method-assign]
        return_value="ws://localhost:9223/devtools/browser/generated-id"
    )

    browser = MagicMock()
    browser.is_connected.return_value = True
    browser.contexts = []

    playwright = MagicMock()
    playwright.chromium.connect_over_cdp = AsyncMock(return_value=browser)

    await manager._connect_via_cdp(playwright)

    manager._get_browser_websocket_url.assert_awaited_once_with(9223)
    playwright.chromium.connect_over_cdp.assert_awaited_once_with(
        "ws://localhost:9223/devtools/browser/generated-id"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("force,auto_close", [(False, False), (True, False), (False, True)])
async def test_cleanup_preserves_borrowed_context_and_other_cdp_clients(monkeypatch, force, auto_close):
    monkeypatch.setattr(config, "CDP_CONNECT_EXISTING", False)
    monkeypatch.setattr(config, "AUTO_CLOSE_BROWSER", auto_close)
    shared_context = MagicMock()
    shared_context.close = AsyncMock()
    shared_context.pages = [MagicMock()]
    other_browser = MagicMock()
    other_browser.is_connected.return_value = True
    browser = MagicMock()
    browser.contexts = [shared_context]
    browser.close = AsyncMock()
    browser.is_connected.return_value = True
    manager = CDPBrowserManager()
    manager.browser = browser
    manager.browser_context = await manager._create_browser_context()
    manager.launcher = MagicMock(browser_process=None)
    manager._clear_recorded_port = MagicMock()

    await manager.cleanup(force=force)

    shared_context.close.assert_not_awaited()
    shared_context.pages[0].close.assert_not_called()
    browser.close.assert_awaited_once()
    other_browser.close.assert_not_called()
    manager.launcher.cleanup.assert_not_called()
    manager._clear_recorded_port.assert_not_called()
    assert manager.browser is None
    assert manager.browser_context is None
    await manager.cleanup(force=force)
    browser.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_cleanup_closes_only_a_context_created_by_this_manager(monkeypatch):
    monkeypatch.setattr(config, "CDP_CONNECT_EXISTING", False)
    monkeypatch.setattr(config, "AUTO_CLOSE_BROWSER", False)
    owned_context = MagicMock()
    owned_context.close = AsyncMock()
    browser = MagicMock()
    browser.contexts = []
    browser.new_context = AsyncMock(return_value=owned_context)
    browser.close = AsyncMock()
    browser.is_connected.return_value = True
    manager = CDPBrowserManager()
    manager.browser = browser
    manager.browser_context = await manager._create_browser_context()
    assert manager._owns_browser_context

    await manager.cleanup()

    owned_context.close.assert_awaited_once()
    browser.close.assert_awaited_once()
    assert not manager._owns_browser_context


@pytest.mark.asyncio
@pytest.mark.parametrize("force,auto_close", [(True, False), (False, True)])
async def test_explicit_shutdown_only_terminates_owned_browser_process(monkeypatch, force, auto_close):
    monkeypatch.setattr(config, "CDP_CONNECT_EXISTING", False)
    monkeypatch.setattr(config, "AUTO_CLOSE_BROWSER", auto_close)
    manager = CDPBrowserManager()
    manager.launcher = MagicMock(browser_process=MagicMock())
    manager._clear_recorded_port = MagicMock()
    await manager.cleanup(force=force)
    manager.launcher.cleanup.assert_called_once()
    manager._clear_recorded_port.assert_called_once()


@pytest.mark.asyncio
async def test_disconnect_failure_still_releases_references_without_closing_shared_context(monkeypatch):
    monkeypatch.setattr(config, "AUTO_CLOSE_BROWSER", False)
    context = MagicMock()
    context.close = AsyncMock()
    manager = CDPBrowserManager()
    manager.browser_context = context
    manager.browser = MagicMock()
    manager.browser.is_connected.return_value = True
    manager.browser.close = AsyncMock(side_effect=RuntimeError("connection closed"))
    await manager.cleanup()
    context.close.assert_not_awaited()
    assert manager.browser is None
    assert manager.browser_context is None
