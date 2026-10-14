"""Background collection must never navigate or activate the user's tabs."""

import asyncio
from contextvars import Context
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from media_platform.douyin.browser_session import DouyinBrowserSession
from tools import douyin_collection_page as module
from tools.douyin_browser_coordinator import DouyinTabLease


@pytest.fixture(autouse=True)
def isolated_target_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "_TARGET_FILE", tmp_path / "collection-target.json")


def page(url="https://www.douyin.com/", name="", target_id="user"):
    result = MagicMock(url=url, target_id=target_id)
    result.is_closed.return_value = False
    result.tab_name = name

    async def evaluate(script):
        if script == module._MARK_TAB:
            result.tab_name = module.COLLECTION_TAB_NAME
        return result.tab_name

    result.evaluate = AsyncMock(side_effect=evaluate)
    result.add_init_script = AsyncMock()
    result.goto = AsyncMock()
    result.close = AsyncMock()
    result.bring_to_front = AsyncMock()
    return result


def browser_context(pages, *, competing_page=False, attach=True):
    context = MagicMock(pages=list(pages))
    context.new_page = AsyncMock(return_value=page("about:blank"))
    context.created = []
    context.commands = []
    context.sessions = []
    callbacks = {}
    context.on.side_effect = lambda event, fn: callbacks.update({event: fn})
    context.remove_listener.side_effect = lambda event, fn: callbacks.pop(event, None)

    async def cdp_session(anchor):
        session = SimpleNamespace(detach=AsyncMock())

        async def send(method, params=None):
            context.commands.append((method, params))
            if method == "Target.getTargetInfo":
                return {"targetInfo": {"targetId": anchor.target_id, "browserContextId": "logged-in-context"}}
            if method == "Target.createTarget":
                collection = page("about:blank", target_id=f"collection-{len(context.created)}")
                context.created.append(collection)
                if competing_page:
                    context.pages.append(page("about:blank", target_id="other-user-tab"))
                    callbacks["page"](context.pages[-1])
                if attach:
                    context.pages.append(collection)
                    callbacks["page"](collection)
                return {"targetId": collection.target_id}
            if method == "Target.closeTarget":
                for candidate in context.pages:
                    if candidate.target_id == params["targetId"]:
                        candidate.is_closed.return_value = True
                return {"success": True}
            pytest.fail(f"Unexpected CDP command: {method}")

        session.send = AsyncMock(side_effect=send)
        context.sessions.append(session)
        return session

    context.new_cdp_session = AsyncMock(side_effect=cdp_session)
    return context


@pytest.mark.asyncio
async def test_background_creation_keeps_foreground_and_shares_login_context():
    user = page("https://www.douyin.com/user/reading", "MediaCrawler")
    webui = page("http://localhost:5173/", "MediaCrawler", "webui")
    context = browser_context([webui, user])
    selected = await module.get_collection_page(context)
    assert selected is context.created[0]
    assert selected.tab_name == module.COLLECTION_TAB_NAME
    assert ("Target.createTarget", {"url": "about:blank", "background": True, "newWindow": False,
                                     "browserContextId": "logged-in-context"}) in context.commands
    context.new_page.assert_not_awaited()
    user.goto.assert_not_awaited()
    webui.goto.assert_not_awaited()
    user.bring_to_front.assert_not_awaited()
    selected.bring_to_front.assert_not_awaited()
    assert user.url == "https://www.douyin.com/user/reading"
    assert webui.url == "http://localhost:5173/"
    assert all(session.detach.await_count == 1 for session in context.sessions)


@pytest.mark.asyncio
async def test_operations_and_new_connections_reuse_the_same_collection_tab():
    context = browser_context([page()])
    first = await module.get_collection_page(context)
    first.url = "https://www.douyin.com/video/123"
    # A new Playwright connection sees the same tabs and their persisted names.
    reconnected = browser_context(context.pages)
    assert await module.get_collection_page(reconnected) is first
    assert not reconnected.created
    assert await module.get_collection_page(context) is first
    assert len(context.created) == 1


@pytest.mark.asyncio
async def test_detail_collection_navigates_background_only_and_keeps_it_after_cleanup():
    user = page("https://www.douyin.com/user/reading", "MediaCrawler")
    context = browser_context([user])
    user.context = context
    background = await module.get_collection_page(context)
    background.context = context
    response = SimpleNamespace(status=200, text=AsyncMock(return_value='{"aweme_detail":{"aweme_id":"123"}}'))
    waiter = MagicMock()
    waiter.__aenter__ = AsyncMock(return_value=waiter)
    waiter.__aexit__ = AsyncMock(return_value=False)
    waiter.value = asyncio.get_running_loop().create_future()
    waiter.value.set_result(response)
    background.expect_response.return_value = waiter

    async def navigate(url, **kwargs):
        background.url = url

    background.goto.side_effect = navigate
    session = DouyinBrowserSession(user)
    assert (await session._detail("123", 1))["status"] == 200
    await session.close()
    background.goto.assert_awaited_once_with("https://www.douyin.com/video/123", wait_until="commit", timeout=1000)
    background.close.assert_not_awaited()
    user.goto.assert_not_awaited()
    user.bring_to_front.assert_not_awaited()
    assert user.url == "https://www.douyin.com/user/reading"
    assert await module.get_collection_page(context) is background


@pytest.mark.asyncio
async def test_closing_background_tab_recreates_it_without_touching_user_tab():
    user = page()
    closed = page(name=module.COLLECTION_TAB_NAME)
    closed.is_closed.return_value = True
    context = browser_context([user, closed])
    assert await module.get_collection_page(context) is context.created[0]
    closed.evaluate.assert_not_awaited()
    user.goto.assert_not_awaited()
    user.bring_to_front.assert_not_awaited()


@pytest.mark.asyncio
async def test_concurrently_opened_user_tab_is_not_mistaken_for_created_target():
    context = browser_context([page()], competing_page=True)
    selected = await module.get_collection_page(context)
    assert selected.target_id.startswith("collection-")
    unrelated = next(item for item in context.pages if item.target_id == "other-user-tab")
    unrelated.evaluate.assert_not_awaited()
    unrelated.goto.assert_not_awaited()
    unrelated.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_foreign_tab_with_collection_name_is_never_reused():
    foreign = page("https://example.com/", module.COLLECTION_TAB_NAME)
    context = browser_context([foreign])
    assert await module.get_collection_page(context) is context.created[0]
    foreign.evaluate.assert_not_awaited()
    foreign.goto.assert_not_awaited()


@pytest.mark.asyncio
async def test_creation_timeout_removes_only_its_own_target():
    user = page()
    context = browser_context([user], attach=False)
    with pytest.raises(TimeoutError):
        await module._create_background_page(context, timeout=0.01)
    assert ("Target.closeTarget", {"targetId": "collection-0"}) in context.commands
    user.close.assert_not_awaited()
    assert context.sessions[0].detach.await_count == 1
    context.remove_listener.assert_called_once()


@pytest.mark.asyncio
async def test_cdp_failure_does_not_fall_back_to_a_foreground_tab():
    user = page()
    context = browser_context([user])
    context.new_cdp_session.side_effect = module.PlaywrightError("CDP unavailable")
    with pytest.raises(module.PlaywrightError):
        await module.get_collection_page(context)
    context.new_page.assert_not_awaited()
    user.goto.assert_not_awaited()
    user.close.assert_not_awaited()
    context.on.assert_not_called()


@pytest.mark.asyncio
async def test_empty_context_creates_only_its_first_page():
    context = browser_context([])
    first = await module.get_collection_page(context)
    assert first is context.new_page.return_value
    first.bring_to_front.assert_not_awaited()
    assert first.tab_name == module.COLLECTION_TAB_NAME


@pytest.mark.asyncio
async def test_global_lease_prevents_two_connections_creating_duplicate_tabs(tmp_path):
    context = browser_context([page()])
    original = DouyinTabLease
    lock_path = tmp_path / "collection.lock"
    with patch.object(module, "DouyinTabLease", lambda: original(lock_path)):
        tasks = [asyncio.create_task(module.get_collection_page(context), context=Context()) for _ in range(2)]
        first, second = await asyncio.gather(*tasks)
    assert first is second
    assert len(context.created) == 1


@pytest.mark.asyncio
async def test_reset_closes_only_registered_collection_target_even_with_hung_renderer():
    user = page("https://www.douyin.com/user/reading", "MediaCrawler")
    webui = page("http://localhost:5173/", target_id="webui")
    context = browser_context([user, webui])
    background = await module.get_collection_page(context)
    background.evaluate.side_effect = TimeoutError("Renderer unresponsive")
    assert await module.get_collection_page(context) is background
    await module.reset_collection_page(context)
    assert background.is_closed()
    assert not user.is_closed() and not webui.is_closed()
    closed = [params['targetId'] for method,params in context.commands if method=='Target.closeTarget']
    assert closed == [background.target_id]
    replacement = await module.get_collection_page(context)
    assert replacement is not background and replacement is not user
    user.goto.assert_not_awaited()


@pytest.mark.asyncio
async def test_reset_can_recover_legacy_tab_without_a_registry():
    user = page()
    legacy = page(name=module.COLLECTION_TAB_NAME,target_id="legacy")
    context = browser_context([user, legacy])
    await module.reset_collection_page(context)
    assert legacy.is_closed()
    assert not user.is_closed()


@pytest.mark.parametrize("data", ["[]", "null", "malformed"])
def test_invalid_registry_is_ignored(data):
    module._TARGET_FILE.write_text(data)
    assert module._remembered_target() is None


@pytest.mark.asyncio
async def test_reused_legacy_tab_remembers_target_for_future_hang():
    legacy = page(name=module.COLLECTION_TAB_NAME, target_id="legacy")
    context = browser_context([legacy])
    assert await module.get_collection_page(context) is legacy
    assert module._remembered_target() == "legacy"
    legacy.evaluate.side_effect = TimeoutError("Renderer unresponsive")
    await module.reset_collection_page(context)
    assert legacy.is_closed()
