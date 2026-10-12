"""Read responses produced by the logged-in Douyin site's normal page loads."""

import asyncio
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

from .exception import DataFetchError
from tools.douyin_browser_coordinator import DouyinTabLease


@dataclass
class CreatorPage:
    page: object
    responses: dict = field(default_factory=dict)
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    response_handler: object = None


class DouyinBrowserSession:
    MIN_PAGE_INTERVAL_SECONDS = 5

    def __init__(self, source_page):
        self.source_page = source_page
        self.creator_pages = {}
        self.lock = asyncio.Lock()
        self.last_page_request_at = 0

    async def request(self, url, params, timeout):
        async with self.lock, DouyinTabLease():
            loop = asyncio.get_running_loop()
            remaining = self.MIN_PAGE_INTERVAL_SECONDS - (loop.time() - self.last_page_request_at)
            if remaining > 0:
                await asyncio.sleep(remaining)
            self.last_page_request_at = loop.time()
            path = urlsplit(url).path
            if path == "/aweme/v1/web/aweme/detail/":
                return await self._detail(str(params["aweme_id"]), timeout)
            if path == "/aweme/v1/web/aweme/post/":
                return await self._posts(str(params["sec_user_id"]), str(params.get("max_cursor") or "0"), timeout)
            raise ValueError("Unsupported browser-session endpoint")

    @staticmethod
    def matches_response(response, path, key, value):
        target = urlsplit(response.url)
        host = target.hostname or ""
        return (
            target.scheme == "https" and (host == "douyin.com" or host.endswith(".douyin.com"))
            and target.path == path
            and parse_qs(target.query).get(key) == [value]
        )

    async def _work_page(self):
        """Reuse an existing Douyin tab; never commandeer the WebUI or open a tab."""
        pages = [self.source_page, *self.source_page.context.pages]
        for page in pages:
            host = urlsplit(page.url).hostname or ""
            if not page.is_closed() and (host == "douyin.com" or host.endswith(".douyin.com")):
                return page
        raise DataFetchError("请先在专用 Chrome 中打开抖音页签，再开始采集")

    def _clear_creator_pages(self):
        for state in self.creator_pages.values():
            if state.response_handler is not None:
                state.page.remove_listener("response", state.response_handler)
        self.creator_pages.clear()

    async def _detail(self, aweme_id, timeout):
        page = await self._work_page()
        # A detail navigation invalidates the shared tab's creator pagination.
        self._clear_creator_pages()
        try:
            async with page.expect_response(
                lambda r: self.matches_response(r, "/aweme/v1/web/aweme/detail/", "aweme_id", aweme_id),
                timeout=timeout * 1000,
            ) as response_info:
                await page.goto(f"https://www.douyin.com/video/{aweme_id}",
                                wait_until="domcontentloaded", timeout=timeout * 1000)
            response = await response_info.value
        except Exception as exc:
            if page.is_closed() or urlsplit(page.url).path not in (f"/video/{aweme_id}", "/"):
                raise DataFetchError("抖音页签已切换或关闭，请重新开始采集") from exc
            raise
        return {"status": response.status, "body": await response.text()}

    async def _posts(self, sec_user_id, cursor, timeout):
        state = self.creator_pages.get(sec_user_id)
        if state is not None and (
            state.page.is_closed() or urlsplit(state.page.url).path != f"/user/{sec_user_id}"
            or (cursor == "0" and "0" not in state.responses)
        ):
            self._clear_creator_pages()
            state = None
        if state is None:
            if cursor != "0":
                raise DataFetchError("抖音页签已切换，分页状态失效，请重新开始发现")
            page = await self._work_page()
            self._clear_creator_pages()
            state = CreatorPage(page)
            self.creator_pages[sec_user_id] = state

            def receive(response):
                if not self.matches_response(response, "/aweme/v1/web/aweme/post/", "sec_user_id", sec_user_id):
                    return
                request_cursor = parse_qs(urlsplit(response.url).query).get("max_cursor", ["0"])[0] or "0"
                # Retain the response immediately; read its body in the requesting
                # coroutine rather than launching an untracked background reader.
                state.responses[request_cursor] = response
                state.changed.set()

            state.response_handler = receive
            page.on("response", receive)
            try:
                await page.goto(f"https://www.douyin.com/user/{sec_user_id}",
                                wait_until="domcontentloaded", timeout=timeout * 1000)
            except BaseException:
                self.creator_pages.pop(sec_user_id, None)
                page.remove_listener("response", receive)
                raise

        deadline = asyncio.get_running_loop().time() + timeout
        scroll_attempts = 0
        while cursor not in state.responses:
            if state.page.is_closed() or urlsplit(state.page.url).path != f"/user/{sec_user_id}":
                self._clear_creator_pages()
                raise DataFetchError("抖音页签已切换或关闭，请重新开始发现")
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise DataFetchError("Creator browser page timed out before providing the requested posts")
            state.changed.clear()
            if cursor != "0" and scroll_attempts < 3:
                # Pagination is generated by the website's normal scrolling handler.
                viewport = await state.page.evaluate("() => ({x: innerWidth * 0.7, y: innerHeight * 0.7})")
                await state.page.mouse.move(viewport["x"], viewport["y"])
                await state.page.mouse.wheel(0, 1200)
                scroll_attempts += 1
            try:
                await asyncio.wait_for(state.changed.wait(), min(2, remaining))
            except asyncio.TimeoutError:
                pass
        response = state.responses.pop(cursor)
        return {"status": response.status, "body": await response.text()}

    async def close(self):
        # These are user/browser-owned tabs. Only release our listeners/state.
        self._clear_creator_pages()
