import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlsplit

from media_platform.douyin import browser_session as helper
from media_platform.douyin import client as module


class SessionSyncTests(unittest.IsolatedAsyncioTestCase):
    def make_client(self, cookies=None, proxy=None):
        page = MagicMock()
        page.context = MagicMock()
        page.evaluate = AsyncMock(return_value={"xmst": "test-token"})
        client = module.DouYinClient(
            headers={"Cookie": "old-cookie", "User-Agent": "Chrome/154.0.0.0", "Origin": "https://www.douyin.com"},
            cookie_dict=cookies or {}, playwright_page=page, proxy=proxy,
        )
        client._refresh_proxy_if_expired = AsyncMock()
        return client, page

    async def test_copied_headers_refresh_after_login(self):
        client, page = self.make_client({"UIFID": "old-id"})
        copied = dict(client.headers)
        with patch.object(module.utils, "convert_browser_context_cookies", AsyncMock(return_value=("new-cookie", {"UIFID": "new-id"}))):
            prepared = await client._prepare_request_headers(copied)
        self.assertEqual(prepared["Cookie"], "new-cookie")
        self.assertEqual(prepared["uifid"], "new-id")
        self.assertEqual(copied["Cookie"], "old-cookie")

    async def test_cleared_session_removes_stale_identifier(self):
        client, _ = self.make_client({"UIFID": "old-id"})
        with patch.object(module.utils, "convert_browser_context_cookies", AsyncMock(return_value=("", {}))):
            prepared = await client._prepare_request_headers(dict(client.headers))
        self.assertNotIn("uifid", prepared)

    async def test_detail_uses_same_session_and_actual_browser_version(self):
        client, _ = self.make_client()
        client.request = AsyncMock(return_value={"aweme_detail": {"aweme_id": "123"}})
        cookies = {"UIFID_TEMP": "current-id", "s_v_web_id": "current-device"}
        with patch.object(module.utils, "convert_browser_context_cookies", AsyncMock(return_value=("current-cookie", cookies))), patch.object(module, "get_a_bogus", AsyncMock(return_value="test-only-signature")) as signer:
            result = await client.get_video_by_id("123")
        signer.assert_not_awaited()
        self.assertEqual(result["aweme_id"], "123")
        call = client.request.await_args.kwargs
        self.assertEqual(call["params"]["uifid"], "current-id")
        self.assertEqual(call["params"]["verifyFp"], "current-device")
        self.assertEqual(call["params"]["fp"], "current-device")
        self.assertEqual(call["params"]["browser_version"], "154.0.0.0")
        self.assertEqual(call["headers"]["uifid"], "current-id")
        self.assertNotIn("Origin", call["headers"])

    async def test_protected_endpoint_uses_browser_and_not_copied_cookie(self):
        client, page = self.make_client({"UIFID": "real-session"})
        client._browser_session.request = AsyncMock(return_value={"status": 200, "body": json.dumps({"aweme_detail": {"aweme_id": "123"}})})
        with patch.object(module, "make_async_client") as http:
            result = await client.request("GET", "https://www.douyin.com/aweme/v1/web/aweme/detail/", params={"aweme_id": "123"}, headers=client.headers)
        http.assert_not_called()
        args = client._browser_session.request.await_args.args
        self.assertEqual(args[1], {"aweme_id": "123"})
        page.evaluate.assert_not_awaited()
        self.assertEqual(result["aweme_detail"]["aweme_id"], "123")

    async def test_rejection_does_not_fall_back_or_retry(self):
        client, page = self.make_client()
        client._browser_session.request = AsyncMock(return_value={"status": 403, "body": "Blocked by ArgusSecurityPlugin Uifid Not Found"})
        with patch.object(module, "make_async_client") as http:
            with self.assertRaisesRegex(module.DataFetchError, "HTTP 403.*Argus"):
                await client.request("GET", "https://www.douyin.com/aweme/v1/web/aweme/post/", params={"sec_user_id": "test"})
        http.assert_not_called()
        self.assertEqual(client._browser_session.request.await_count, 1)

    async def test_normal_page_matching_rejects_other_posts_and_hosts(self):
        valid = MagicMock(url="https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id=123")
        wrong = MagicMock(url="https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id=456")
        foreign = MagicMock(url="https://other.example/aweme/v1/web/aweme/detail/?aweme_id=123")
        shard = MagicMock(url="https://www-hj.douyin.com/aweme/v1/web/aweme/detail/?aweme_id=123")
        match = helper.DouyinBrowserSession.matches_response
        self.assertTrue(match(valid, "/aweme/v1/web/aweme/detail/", "aweme_id", "123"))
        self.assertFalse(match(wrong, "/aweme/v1/web/aweme/detail/", "aweme_id", "123"))
        self.assertFalse(match(foreign, "/aweme/v1/web/aweme/detail/", "aweme_id", "123"))
        self.assertTrue(match(shard, "/aweme/v1/web/aweme/detail/", "aweme_id", "123"))

    async def test_failed_detail_load_closes_only_its_owned_page(self):
        source = MagicMock()
        page = MagicMock()
        page.close = AsyncMock()
        source.context.new_page = AsyncMock(return_value=page)
        waiter = MagicMock()
        waiter.__aenter__ = AsyncMock(side_effect=TimeoutError("page timed out"))
        page.expect_response.return_value = waiter
        session = helper.DouyinBrowserSession(source)
        with self.assertRaises(TimeoutError):
            await session._detail("123", 1)
        page.close.assert_awaited_once()
        source.close.assert_not_called()

    async def test_creator_pagination_reuses_the_sites_page(self):
        source, page = MagicMock(), MagicMock()
        page.close = AsyncMock()
        source.context.new_page = AsyncMock(return_value=page)
        callbacks = {}
        source.context.on.side_effect = lambda event, callback: callbacks.update({event: callback})
        async def emit(cursor):
            response = MagicMock(url=f"https://www.douyin.com/aweme/v1/web/aweme/post/?sec_user_id=test-user&max_cursor={cursor}", status=200)
            response.text = AsyncMock(return_value=json.dumps({"cursor": cursor}))
            callbacks["response"](response)
        async def load(*args, **kwargs):
            await emit("0")
        async def scroll(*args, **kwargs):
            return {"x": 100, "y": 100}
        async def wheel(*args, **kwargs):
            await emit("100")
        page.goto = AsyncMock(side_effect=load)
        page.evaluate = AsyncMock(side_effect=scroll)
        page.mouse.move = AsyncMock()
        page.mouse.wheel = AsyncMock(side_effect=wheel)
        session = helper.DouyinBrowserSession(source)
        first = await session._posts("test-user", "0", 1)
        second = await session._posts("test-user", "100", 1)
        self.assertEqual(json.loads(first["body"])["cursor"], "0")
        self.assertEqual(json.loads(second["body"])["cursor"], "100")
        source.context.new_page.assert_awaited_once()
        await session.close()
        page.close.assert_awaited_once()

    async def test_proxy_keeps_its_existing_transport(self):
        client, page = self.make_client(proxy="http://test-proxy")
        http_client = MagicMock()
        http_client.request = AsyncMock(return_value=MagicMock(status_code=200, text='{"ok": true}'))
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=http_client)
        manager.__aexit__ = AsyncMock(return_value=False)
        with patch.object(module, "make_async_client", return_value=manager):
            result = await client.request("GET", "https://www.douyin.com/aweme/v1/web/aweme/detail/", params={})
        page.evaluate.assert_not_awaited()
        self.assertTrue(result["ok"])


if __name__ == "__main__":
    unittest.main()
