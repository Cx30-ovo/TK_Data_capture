# -*- coding: utf-8 -*-
"""Business service linking the monitor repository with the Douyin crawler."""

import asyncio
import shutil
import time
import urllib.parse
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Optional

from playwright.async_api import async_playwright

import config
from database.monitor_repository import monitor_repository
from media_platform.douyin.core import DouYinCrawler
from tools.cdp_browser import CDPBrowserManager, safe_page_goto
from tools.douyin_browser_coordinator import DouyinTabLease, CollectionStoppedError
from tools.collection_errors import classify_collection_error

from .crawler_manager import crawler_manager
from .monitor_execution import MonitorExecution
from .browser_recovery import BrowserRecovery

RISK_CONTROL_BASE_COOLDOWN_SECONDS = 30 * 60
RISK_CONTROL_MAX_COOLDOWN_SECONDS = 6 * 60 * 60
DISCOVERY_RETRY_BASE_SECONDS = 2 * 60
DISCOVERY_RETRY_MAX_SECONDS = 30 * 60


class MonitorBrowserNetworkError(RuntimeError):
    """A recoverable browser-network problem that should not surface as HTTP 500."""


class MonitorHotRankError(RuntimeError):
    """A recoverable failure while loading Douyin's public hot ranking."""


class DouyinPostUnavailableError(RuntimeError):
    """The requested Douyin post no longer has a detail page and cannot be retried."""


class PartialDiscoveryError(RuntimeError):
    def __init__(self, cause, posts):
        super().__init__(str(cause))
        self.cause = cause
        self.posts = posts


def monitored_operation(kind):
    """Reject duplicate clicks, expose progress, and finalize even on errors."""
    def decorate(method):
        @wraps(method)
        async def run(self, *args, **kwargs):
            if self._paused:
                return {"status": "skipped", "reason": "监控已暂停，请先恢复监控", "error_code": "monitor_paused"}
            if self._lock.locked() or (self._execution and self._execution.active):
                return {"status": "skipped", "reason": "已有任务正在执行，请等待完成", "error_code": "browser_busy"}
            if self._recovery.pending:
                return {"status": "deferred", "reason": "专用浏览器等待自动恢复", "error_code": "browser_recovering",
                        "retry_after_seconds": self._recovery.snapshot()["retry_after_seconds"]}
            execution = self._execution = MonitorExecution(kind)
            try:
                result = await method(self, *args, **kwargs)
                if execution.stop_requested:
                    result = {**result, "status": "stopped", "reason": "已安全停止，已完成的数据保留"}
                if result.get("status") == "stopped":
                    state = "stopped"
                elif execution.error:
                    state = "partial" if result.get("created_posts", 0) or result.get("completed", 0) else "error"
                else:
                    state = {"ok": "completed", "stopped": "stopped", "deferred": "deferred", "skipped": "skipped"}.get(result.get("status"), result.get("status", "error"))
                execution.update(state=state, phase="finished", result=result)
                return result
            except CollectionStoppedError:
                result = {"status": "stopped", "reason": "已安全停止，已完成的数据保留"}
                execution.update(state="stopped", phase="finished", result=result)
                return result
            except asyncio.CancelledError:
                execution.update(state="stopped", phase="finished", result={"status": "stopped", "reason": "服务正在关闭"})
                raise
            except Exception as exc:
                failure = classify_collection_error(exc)
                cooldown = await self._handle_collection_failure(failure, kind, execution.sec_user_id)
                result = {"status": "blocked" if failure.error_code == "risk_control" else "error", "reason": failure.message,
                          **failure.as_dict(), "retry_after_seconds": cooldown}
                execution.update(state="error", phase="finished", error=failure.as_dict(), result=result)
                await crawler_manager.add_log(f"[Monitor] [{execution.account_name or '监控'}] [{failure.error_code}] {failure.message}", "warning")
                return result
            finally:
                execution.update(finished_at=time.time(), current_post="")
                if kind == "discovery" and execution.sec_user_id and execution.result is not None:
                    try:
                        await monitor_repository.record_account_discovery_result(
                            execution.sec_user_id, execution.result, int(execution.finished_at))
                    except Exception:
                        await crawler_manager.add_log("[Monitor] 发现结果摘要保存失败；作品和任务保存结果不受影响", "warning")
        return run
    return decorate


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def classify_job_error(job: dict) -> str:
    text = f"{job.get('last_error') or ''} {job.get('miss_reason') or ''}".lower()
    for code in ("risk_control", "login_required", "browser_disconnected", "network_timeout", "tab_changed", "browser_busy", "invalid_response"):
        if f"[{code}]" in text:
            return code
    if not text.strip():
        return "none"
    if job.get("status") == "skipped" and (
        "作品已删除" in text or "failed to get douyin detail for aweme_id=" in text
    ):
        return "post_deleted"
    if "argus" in text or "风控" in text or "blocked" in text:
        return "risk_control"
    if "login" in text or "登录" in text:
        return "login_required"
    if "browser" in text or "cdp" in text or "websocket" in text or "disconnected" in text:
        return "browser_disconnected"
    if "timeout" in text or "timed out" in text or "connection" in text:
        return "network_timeout"
    if "not found" in text or "不存在" in text:
        return "post_not_found"
    if "json" in text or "decode" in text:
        return "parse_error"
    return "unknown"


class DouyinMonitorFetcher:
    """Small crawler adapter used by the monitor service."""

    def __init__(self):
        self._playwright = None
        self._crawler: Optional[DouYinCrawler] = None
        self._client = None
        self._lease = None
        self.should_stop = lambda: False
        self.on_progress = lambda **values: None
        self.reset_collection_page = False

    async def __aenter__(self) -> "DouyinMonitorFetcher":
        self._lease = DouyinTabLease(should_stop=self.should_stop, on_wait=lambda: self.on_progress(phase="waiting_tab"))
        await self._lease.__aenter__()
        try:
            if self.should_stop():
                raise CollectionStoppedError("已请求停止")
            self.on_progress(phase="connecting")
            return await asyncio.wait_for(self._open_browser(), config.BROWSER_RECOVERY_TIMEOUT_SECONDS)
        except BaseException:
            await self.__aexit__(None, None, None)
            raise

    async def _open_browser(self) -> "DouyinMonitorFetcher":
        self._playwright = await async_playwright().start()
        self._crawler = DouYinCrawler()
        # Monitor recovery must stay in the existing managed profile: never
        # silently fall back to a new, unrelated Playwright login context.
        self._crawler.cdp_manager = CDPBrowserManager(profile_platform="dy")
        browser_context = await self._crawler.cdp_manager.launch_and_connect(
            self._playwright, None, None, headless=config.CDP_HEADLESS)
        self._crawler.browser_context = browser_context
        if self.reset_collection_page:
            from tools.douyin_collection_page import reset_collection_page
            await reset_collection_page(browser_context)
            self.reset_collection_page = False
        self._crawler.context_page = await self._crawler._get_or_create_context_page()
        try:
            await safe_page_goto(
                self._crawler.context_page,
                self._crawler.index_url,
                accepted_hosts=("douyin.com",),
            )
        except Exception as exc:
            message = str(exc)
            if "ERR_NETWORK_ACCESS_DENIED" in message:
                raise MonitorBrowserNetworkError(
                    "抖音专用浏览器的网络访问被拒绝，请检查代理软件或防火墙后重试。"
                ) from exc
            raise
        self._client = await self._crawler.create_douyin_client(None)
        if not await self._client.pong(browser_context=self._crawler.browser_context):
            raise RuntimeError("Douyin login required. Please run a normal crawler task first to refresh the login state.")
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        try:
            try:
                await self._close_browser()
            except Exception as cleanup_error:
                # A disconnected cleanup must not discard an already fetched page
                # or replace the original classified collection failure.
                await crawler_manager.add_log(f"[Monitor] 浏览器清理异常：{classify_collection_error(cleanup_error).message}", "warning")
        finally:
            if self._lease:
                await self._lease.__aexit__(exc_type, exc, tb)
                self._lease = None

    async def _close_browser(self):
        try:
            if self._client:
                await asyncio.wait_for(self._client.close_browser_pages(), 5)
        finally:
            try:
                if self._crawler and self._crawler.cdp_manager:
                    await asyncio.wait_for(self._crawler.cdp_manager.cleanup(), 5)
            finally:
                try:
                    if self._playwright:
                        await asyncio.wait_for(self._playwright.stop(), 5)
                finally:
                    self._crawler = None
                    self._client = None
                    self._playwright = None

    @staticmethod
    def _is_browser_disconnect_error(exc: Exception) -> bool:
        message = str(exc).lower()
        markers = (
            "browser has been closed",
            "target closed",
            "connection closed",
            "websocket",
            "cdp",
            "connection refused",
            "econnrefused",
            "disconnected",
        )
        return any(marker in message for marker in markers)

    async def _reconnect(self, reason: Exception) -> None:
        await crawler_manager.add_log(f"[Monitor] Browser reconnecting: {classify_collection_error(reason).message}", "warning")
        # Keep the operation's lease across reconnect; no other task may navigate.
        await self._close_browser()
        if self.should_stop():
            raise CollectionStoppedError("恢复浏览器前已请求停止")
        await asyncio.wait_for(self._open_browser(), config.BROWSER_RECOVERY_TIMEOUT_SECONDS)

    @staticmethod
    def _extract_cover_url(item: dict) -> str:
        """Return the best available static cover URL for a video or image post."""
        def first_url(payload: Any) -> str:
            if isinstance(payload, str):
                return payload.strip()
            if isinstance(payload, (list, tuple)):
                for value in reversed(payload):
                    if url := first_url(value):
                        return url
                return ""
            if not isinstance(payload, dict):
                return ""
            for key in ("url_list", "download_url_list", "urls", "url", "uri"):
                if url := first_url(payload.get(key)):
                    return url
            return ""

        video = item.get("video") or {}
        for key in (
            "raw_cover",
            "origin_cover",
            "cover",
            "dynamic_cover",
            "animated_cover",
            "ai_dynamic_cover",
        ):
            if url := first_url(video.get(key)):
                return url

        images = item.get("images") or (item.get("image_post_info") or {}).get("images") or []
        if images:
            first_image = images[0] or {}
            for key in (
                "origin_url",
                "display_image",
                "owner_watermark_image",
                "download_url",
                "url",
                "url_list",
            ):
                if url := first_url(first_image.get(key)):
                    return url
        return ""

    @staticmethod
    def _normalize_post(item: dict, sec_user_id: str) -> dict:
        aweme_id = str(item.get("aweme_id") or "")
        desc = item.get("desc") or ""
        statistics = item.get("statistics") or {}
        return {
            "platform": "dy",
            "aweme_id": aweme_id,
            "sec_user_id": sec_user_id,
            "title": desc,
            "desc": desc,
            "create_time": _to_int(item.get("create_time")),
            "canonical_url": f"https://www.douyin.com/video/{aweme_id}",
            "cover_url": DouyinMonitorFetcher._extract_cover_url(item),
            "status": "active",
            "source": "creator_monitor",
            "liked_count": _to_int(statistics.get("digg_count")),
            "collected_count": _to_int(statistics.get("collect_count")),
            "comment_count": _to_int(statistics.get("comment_count")),
            "share_count": _to_int(statistics.get("share_count")),
        }

    async def fetch_latest_posts(
        self,
        sec_user_id: str,
        known_ids: set[str],
        max_pages: int = 3,
        published_since: Optional[int] = None,
        stop_on_known: bool = False,
    ) -> list[dict]:
        try:
            return await self._fetch_latest_posts_once(
                sec_user_id, known_ids, max_pages, published_since, stop_on_known
            )
        except PartialDiscoveryError:
            raise
        except Exception as exc:
            if not self._is_browser_disconnect_error(exc):
                raise
            await self._reconnect(exc)
            return await self._fetch_latest_posts_once(
                sec_user_id, known_ids, max_pages, published_since, stop_on_known
            )

    async def _fetch_latest_posts_once(
        self,
        sec_user_id: str,
        known_ids: set[str],
        max_pages: int = 3,
        published_since: Optional[int] = None,
        stop_on_known: bool = False,
    ) -> list[dict]:
        posts: list[dict] = []
        max_cursor = ""
        pages = 0

        while pages < max_pages:
            if self.should_stop():
                break
            self.on_progress(phase="scanning", pages=pages, scanned=len(posts))
            try:
                response = await asyncio.wait_for(
                    self._client.get_user_aweme_posts(sec_user_id, max_cursor), config.BROWSER_RECOVERY_TIMEOUT_SECONDS)
            except Exception as exc:
                if posts:
                    raise PartialDiscoveryError(exc, posts) from exc
                raise
            aweme_list = response.get("aweme_list") or []
            if not aweme_list:
                break

            page_create_times: list[int] = []
            page_has_known = False
            for item in aweme_list:
                aweme_id = str(item.get("aweme_id") or "")
                if not aweme_id:
                    continue
                normalized = self._normalize_post(item, sec_user_id)
                normalized["is_known"] = aweme_id in known_ids
                # Pinned posts precede the chronological feed and are not a
                # boundary for newly published works further down the list.
                is_pinned = _to_int(item.get("is_top")) > 0
                page_has_known = page_has_known or (normalized["is_known"] and not is_pinned)
                posts.append(normalized)
                if normalized["create_time"] > 0 and not is_pinned:
                    page_create_times.append(normalized["create_time"])

            pages += 1
            self.on_progress(pages=pages, scanned=len(posts))
            if stop_on_known and page_has_known:
                break
            if published_since is not None and page_create_times and max(page_create_times) < published_since:
                break
            if not response.get("has_more"):
                break

            next_cursor = response.get("max_cursor")
            if not next_cursor or next_cursor == max_cursor:
                break
            max_cursor = next_cursor

        return posts

    async def fetch_metrics(self, aweme_id: str) -> dict:
        try:
            return await self._fetch_metrics_once(aweme_id)
        except Exception as exc:
            if not self._is_browser_disconnect_error(exc):
                raise
            await self._reconnect(exc)
            return await self._fetch_metrics_once(aweme_id)

    async def _fetch_metrics_once(self, aweme_id: str) -> dict:
        detail = await asyncio.wait_for(self._client.get_video_by_id(aweme_id), config.BROWSER_RECOVERY_TIMEOUT_SECONDS)
        if not detail:
            raise DouyinPostUnavailableError(f"Failed to get Douyin detail for aweme_id={aweme_id}")
        if str(detail.get("aweme_id") or "") != str(aweme_id):
            raise ValueError("Snapshot response does not match the requested post ID")
        statistics = detail.get("statistics") or {}
        if any(key not in statistics for key in ("digg_count", "collect_count", "comment_count", "share_count")):
            raise ValueError("Snapshot response is missing required interaction metrics")
        return {
            "liked_count": _to_int(statistics.get("digg_count")),
            "collected_count": _to_int(statistics.get("collect_count")),
            "comment_count": _to_int(statistics.get("comment_count")),
            "share_count": _to_int(statistics.get("share_count")),
            "cover_url": self._extract_cover_url(detail),
        }

    async def fetch_hot_rank(self) -> list[dict]:
        try:
            return await self._fetch_hot_rank_once()
        except Exception as exc:
            if not self._is_browser_disconnect_error(exc):
                raise
            await self._reconnect(exc)
            return await self._fetch_hot_rank_once()

    async def _fetch_hot_rank_once(self) -> list[dict]:
        response = await asyncio.wait_for(self._client.get_hot_search_list(), config.BROWSER_RECOVERY_TIMEOUT_SECONDS)
        payload = response.get("data") or {}
        if isinstance(payload, list):
            payload = next((item for item in payload if isinstance(item, dict) and item.get("word_list")), {})
        word_list = payload.get("word_list") if isinstance(payload, dict) else None
        if not word_list:
            word_list = response.get("word_list") or []

        result: list[dict] = []
        regular_rank = 0
        for item in word_list:
            if not isinstance(item, dict):
                continue
            word = str(item.get("word") or item.get("sentence") or "").strip()
            if not word:
                continue
            is_pinned = item.get("is_n1") is True
            if not is_pinned:
                regular_rank += 1
            raw_label = item.get("label_name") or item.get("tag_name") or item.get("word_type") or ""
            label = str(raw_label).strip()
            if label.isdigit():
                label = ""
            result.append({
                "rank": None if is_pinned else regular_rank,
                "is_pinned": is_pinned,
                "word": word,
                "hot_value": _to_int(item.get("hot_value") or item.get("hot_score")),
                "video_count": _to_int(item.get("video_count") or item.get("discuss_video_count")),
                "event_time": _to_int(item.get("event_time")),
                "sentence_id": str(item.get("sentence_id") or ""),
                "label": label,
                "search_url": f"https://www.douyin.com/search/{urllib.parse.quote(word, safe='')}",
            })
        return result


class MonitorService:
    """Coordinates incremental discovery and due snapshot execution."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None
        self._hot_rank_cache: Optional[dict] = None
        self._hot_rank_cached_at = 0.0
        self._risk_control_failures = 0
        self._risk_control_until = 0.0
        self._execution = None
        self._paused = False
        self._discovery_retries = {}
        self._recovery = BrowserRecovery(config.ENABLE_BROWSER_AUTO_RECOVERY)
        self._last_browser_check = 0.0

    def execution_status(self):
        return {"paused": self._paused, "crawler_running": self._crawler_is_busy(), "retry_after_seconds": self._risk_control_cooldown_remaining(),
                "execution": self._execution.snapshot() if self._execution else None, "recovery": self._recovery.snapshot()}

    def request_safe_stop(self, run_id=None):
        execution = self._execution
        if run_id is not None and (not execution or execution.run_id != run_id):
            return {"status": "stale", "reason": "任务已变化，请刷新后重试"}
        self._paused = True
        if execution and execution.active:
            execution.update(stop_requested=True, state="stopping")
            return {"status": "stopping", "run_id": execution.run_id}
        return {"status": "paused"}

    def resume_monitoring(self):
        if self._execution and self._execution.active:
            return {"status": "busy", "reason": "当前任务正在停止，请等待保存完成"}
        self._paused = False
        if self._recovery.state == "login_required":
            self._recovery.recovered()
        return {"status": "ok", "retry_after_seconds": self._risk_control_cooldown_remaining()}

    async def _handle_collection_failure(self, failure, kind, sec_user_id=""):
        if failure.error_code == "risk_control":
            return await self._start_risk_control_cooldown(failure.message)
        if failure.error_code == "login_required":
            self._paused = True
            self._recovery.wait_for_login(failure)
            return 0
        was_pending = self._recovery.pending
        scheduled = self._recovery.observe(failure)
        if scheduled and not was_pending:
            await crawler_manager.add_log("[自恢复] 检测到浏览器或采集页异常，将自动重连；已保存的数据保留", "warning")
        if failure.error_code in ("tab_changed", "browser_disconnected"):
            if not scheduled:
                self._paused = True
            return self._recovery.snapshot()["retry_after_seconds"]
        if kind == "discovery" and failure.error_code in ("network_timeout", "invalid_response"):
            return await self._defer_discovery_retry(sec_user_id, failure)
        return 0

    async def _check_browser_health(self):
        if not self._recovery.enabled or self._paused or self._crawler_is_busy() or self._lock.locked():
            return
        if self._recovery.pending or self._risk_control_cooldown_remaining():
            return
        if time.time() - self._last_browser_check < 60:
            return
        self._last_browser_check = time.time()
        manager = CDPBrowserManager(profile_platform="dy")
        port = manager._read_recorded_port()
        if port and not await manager._test_cdp_connection(port, log_warning=False, timeout=1):
            await self._handle_collection_failure(classify_collection_error(RuntimeError("CDP disconnected")), "health")

    async def _recover_browser_if_due(self):
        recovery = self._recovery
        if not recovery.pending:
            return
        if self._paused or self._crawler_is_busy() or self._lock.locked() or self._risk_control_cooldown_remaining():
            return
        if recovery.snapshot()["retry_after_seconds"]:
            return
        async with self._lock:
            recovery.begin()
            await crawler_manager.add_log(f"[自恢复] 第 {recovery.attempts} 次恢复专用 Chrome 和后台采集页", "info")
            try:
                fetcher = DouyinMonitorFetcher()
                fetcher.should_stop = lambda: self._paused
                fetcher.reset_collection_page = recovery.reset_page
                async def prepare():
                    async with fetcher:
                        pass
                await asyncio.wait_for(prepare(), config.BROWSER_RECOVERY_TIMEOUT_SECONDS)
                # A user pause arriving during recovery must remain in force.
                recovery.recovered()
                self._discovery_retries = {account:retry for account,retry in self._discovery_retries.items()
                                           if retry["failure"].error_code != "network_timeout"}
                await crawler_manager.add_log("[自恢复] 浏览器已恢复；监控将在未暂停时继续执行待办任务", "success")
            except CollectionStoppedError:
                recovery.state = "waiting"
            except asyncio.CancelledError:
                recovery.state = "waiting"
                raise
            except Exception as exc:
                failure = classify_collection_error(exc)
                if failure.error_code == "login_required":
                    self._paused = True
                    recovery.wait_for_login(failure)
                    await crawler_manager.add_log("[自恢复] 浏览器已连接，但登录已失效；请在专用 Chrome 登录后恢复监控", "warning")
                elif failure.error_code == "risk_control":
                    await self._start_risk_control_cooldown(failure.message)
                    recovery.failed(failure)
                else:
                    delay = recovery.failed(failure)
                    await crawler_manager.add_log(f"[自恢复] {failure.message}；{delay} 秒后重试", "warning")

    def _should_stop(self):
        return bool(self._execution and self._execution.stop_requested)

    def _progress(self, **values):
        if self._execution and self._execution.active:
            self._execution.update(**values)

    def _configure_fetcher(self, fetcher):
        if isinstance(fetcher, DouyinMonitorFetcher):
            fetcher.should_stop = self._should_stop
            fetcher.on_progress = self._progress

    @property
    def is_running(self) -> bool:
        return bool(self._task and not self._task.done())

    @staticmethod
    def _is_risk_control_error(exc: Exception) -> bool:
        text = str(exc).lower()
        return any(token in text for token in ("argus", "uifid", "blocked", "风控"))

    def _risk_control_cooldown_remaining(self) -> int:
        remaining = int(self._risk_control_until - time.time())
        if remaining <= 0:
            self._risk_control_until = 0.0
            return 0
        return remaining

    async def _start_risk_control_cooldown(self, reason: str) -> int:
        self._risk_control_failures += 1
        cooldown = min(
            RISK_CONTROL_BASE_COOLDOWN_SECONDS * (2 ** (self._risk_control_failures - 1)),
            RISK_CONTROL_MAX_COOLDOWN_SECONDS,
        )
        self._risk_control_until = time.time() + cooldown
        account_name = self._execution.account_name if self._execution and self._execution.active else "抖音"
        await crawler_manager.add_log(
            f"[Monitor] [{account_name or '监控'}] 触发风控，请稍后重试；发现与快照暂停 {cooldown // 60} 分钟",
            "warning",
        )
        return cooldown

    def _clear_risk_control_cooldown(self) -> None:
        self._risk_control_failures = 0
        self._risk_control_until = 0.0

    def _discovery_retry_remaining(self, sec_user_id: str) -> int:
        retry = self._discovery_retries.get(sec_user_id)
        remaining = retry["until"] - time.time() if retry else 0
        return max(1, int(remaining)) if remaining > 0 else 0

    async def _defer_discovery_retry(self, sec_user_id: str, failure) -> int:
        if not sec_user_id:
            return 0
        attempts = self._discovery_retries.get(sec_user_id, {}).get("attempts", 0) + 1
        delay = min(DISCOVERY_RETRY_BASE_SECONDS * 2 ** min(attempts - 1, 4), DISCOVERY_RETRY_MAX_SECONDS)
        self._discovery_retries[sec_user_id] = {"attempts": attempts, "until": time.time() + delay, "failure": failure}
        account_name = self._execution.account_name if self._execution else sec_user_id
        await crawler_manager.add_log(
            f"[Monitor] [{account_name}] [{failure.error_code}] 发现将在 {delay // 60} 分钟后重试；其他账号与快照不受此重试间隔影响",
            "warning",
        )
        return delay

    async def _resolve_account(self, account_id: Optional[int] = None, all_accounts: bool = False):
        if all_accounts:
            return None
        if account_id is not None:
            return await monitor_repository.get_monitored_account_by_id(account_id)
        return await monitor_repository.get_enabled_monitored_account()

    async def start(self) -> None:
        if not self.is_running:
            reconciled = await monitor_repository.reconcile_deleted_post_jobs()
            if reconciled:
                await crawler_manager.add_log(
                    f"[Monitor] Archived {reconciled} snapshot jobs for deleted posts",
                    "info",
                )
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self._check_browser_health()
                await self._recover_browser_if_due()
                await self._run_cycle()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                failure = classify_collection_error(exc)
                if failure.error_code == "risk_control":
                    await self._start_risk_control_cooldown(failure.message)
                await self._create_alert(
                    alert_type="loop_error",
                    severity="error",
                    title="监控循环异常",
                    message=failure.message,
                    dedupe_key=f"loop_error:{datetime.now().strftime('%Y-%m-%d')}",
                )
                await crawler_manager.add_log(f"[Monitor] [{failure.error_code}] {failure.message}", "warning")
            await asyncio.sleep(15 if self._recovery.pending else 60)

    async def _run_cycle(self) -> None:
        if self._paused or self._recovery.pending:
            return
        if self._crawler_is_busy():
            return
        if self._risk_control_cooldown_remaining():
            return

        missed_count = await monitor_repository.mark_overdue_jobs_missed()
        if missed_count > 0:
            await self._create_alert(
                alert_type="missed_jobs",
                severity="warning",
                title="有快照任务错过执行窗口",
                message=f"本轮有 {missed_count} 个快照任务被标记为 missed。",
                dedupe_key=f"missed_jobs:{datetime.now().strftime('%Y-%m-%d')}",
            )

        await self.run_due_snapshots()
        if self._paused or self._recovery.pending or self._risk_control_cooldown_remaining():
            return

        accounts = await monitor_repository.list_monitored_accounts(include_disabled=False)
        now = int(time.time())
        for account in accounts:
            if self._paused or self._recovery.pending or self._risk_control_cooldown_remaining():
                break
            interval_seconds = max(1, account.discover_interval_minutes) * 60
            last_discovered_at = int(account.last_discovered_at or 0)
            if now - last_discovered_at < interval_seconds:
                continue
            if self._discovery_retry_remaining(account.sec_user_id):
                continue
            await crawler_manager.add_log(
                f"[Monitor] Multi-account discovery due for {account.display_name or account.sec_user_id}",
                "info",
            )
            await self.discover_account(sec_user_id=account.sec_user_id)

    def _crawler_is_busy(self) -> bool:
        return bool(crawler_manager.process and crawler_manager.process.poll() is None)

    @monitored_operation("discovery")
    async def discover_account(
        self,
        sec_user_id: Optional[str] = None,
        fetcher=None,
        max_pages: Optional[int] = None,
        backfill_covers: bool = False,
        new_post_window_days: int = 7,
        latest_only: bool = False,
    ) -> dict:
        async with self._lock:
            cooldown_remaining = self._risk_control_cooldown_remaining()
            if cooldown_remaining:
                return {"status": "deferred", "reason": "risk_control_cooldown", "retry_after_seconds": cooldown_remaining}
            if self._crawler_is_busy():
                return {"status": "skipped", "reason": "crawler already running"}

            account = (
                await monitor_repository.get_monitored_account(sec_user_id)
                if sec_user_id
                else await monitor_repository.get_enabled_monitored_account()
            )
            if account is None:
                return {"status": "skipped", "reason": "no enabled monitored account"}
            if not getattr(account, "enabled", True):
                return {"status": "skipped", "reason": "该账号已停止发现，请先恢复账号监控。", "error_code": "account_paused"}
            account_name = account.display_name or account.sec_user_id
            self._progress(account_name=account_name, sec_user_id=account.sec_user_id)
            retry_remaining = self._discovery_retry_remaining(account.sec_user_id)
            if retry_remaining:
                failure = self._discovery_retries[account.sec_user_id]["failure"]
                return {"status": "deferred", "reason": "发现任务等待重试", **failure.as_dict(),
                        "retry_after_seconds": retry_remaining}

            known_ids = await monitor_repository.list_post_ids(account.sec_user_id, account.platform)
            missing_cover_ids = (
                await monitor_repository.list_post_ids_missing_cover(account.sec_user_id, account.platform)
                if backfill_covers
                else set()
            )
            if latest_only and not known_ids:
                page_limit = 1
            elif max_pages is not None:
                page_limit = max_pages
            elif backfill_covers:
                # Douyin usually returns about 18 posts per page. Manual discovery
                # scans the full known range so legacy rows can receive covers.
                page_limit = min(50, max(3, (len(known_ids) + 17) // 18 + 2))
            else:
                page_limit = 1 if not known_ids else 3
            owns_fetcher = fetcher is None
            if owns_fetcher:
                fetcher = DouyinMonitorFetcher()
            self._configure_fetcher(fetcher)
            await crawler_manager.add_log(
                f"[Monitor] [{account_name}] Discovering new posts for {account.sec_user_id}, known={len(known_ids)}, "
                f"max_pages={page_limit}, mode={'latest_only' if latest_only else 'scheduled'}",
                "info",
            )

            new_post_cutoff = int(time.time()) - max(1, new_post_window_days) * 24 * 60 * 60
            discovery_error = None
            async with fetcher as active_fetcher:
                try:
                    posts = await active_fetcher.fetch_latest_posts(
                        sec_user_id=account.sec_user_id,
                        known_ids=known_ids,
                        max_pages=page_limit,
                        published_since=new_post_cutoff,
                        stop_on_known=latest_only or not backfill_covers,
                    )
                except PartialDiscoveryError as exc:
                    posts = exc.posts
                    discovery_error = exc.cause
                if not discovery_error and not self._should_stop():
                    self._clear_risk_control_cooldown()
                posts = list({item["aweme_id"]: item for item in posts}.values())
                fetched_count = len(posts)
                self._progress(scanned=fetched_count)
                skipped_historical = sum(
                    1 for item in posts
                    if item["aweme_id"] not in known_ids
                    and (_to_int(item.get("create_time")) <= 0 or _to_int(item.get("create_time")) < new_post_cutoff)
                )
                if latest_only:
                    posts = [
                        item for item in posts
                        if item["aweme_id"] not in known_ids
                        and _to_int(item.get("create_time")) >= new_post_cutoff
                    ]
                else:
                    posts = [
                        item for item in posts
                        if item["aweme_id"] in known_ids or _to_int(item.get("create_time")) >= new_post_cutoff
                    ]
                if backfill_covers:
                    for item in posts:
                        if self._should_stop() or discovery_error:
                            break
                        if item["aweme_id"] not in missing_cover_ids:
                            continue
                        if item.get("cover_url"):
                            continue
                        try:
                            metrics = await active_fetcher.fetch_metrics(item["aweme_id"])
                        except Exception as exc:
                            await crawler_manager.add_log(
                                f"[Monitor] [{account_name}] Cover backfill skipped for {item['aweme_id']}: {classify_collection_error(exc).message}",
                                "warning",
                            )
                            if classify_collection_error(exc).error_code in ("risk_control", "login_required", "browser_disconnected", "tab_changed"):
                                discovery_error = exc
                                break
                            continue
                        if metrics.get("cover_url"):
                            item["cover_url"] = metrics["cover_url"]

            created_posts = 0
            created_jobs = 0
            updated_covers = 0
            existing_processed = 0
            self._progress(phase="saving")
            for item in posts:
                post, created = await monitor_repository.upsert_post(
                    aweme_id=item["aweme_id"],
                    sec_user_id=item["sec_user_id"],
                    title=item.get("title", ""),
                    desc=item.get("desc", ""),
                    create_time=item["create_time"],
                    canonical_url=item["canonical_url"],
                    cover_url=item.get("cover_url", ""),
                    platform=item.get("platform", "dy"),
                    status=item.get("status", "active"),
                    source=item.get("source", "creator_monitor"),
                )
                if item["aweme_id"] in missing_cover_ids and item.get("cover_url"):
                    updated_covers += 1
                if created:
                    created_posts += 1
                    await monitor_repository.record_first_seen_snapshot(
                        aweme_id=post.aweme_id,
                        platform=post.platform,
                        liked_count=item.get("liked_count", 0),
                        collected_count=item.get("collected_count", 0),
                        comment_count=item.get("comment_count", 0),
                        share_count=item.get("share_count", 0),
                        captured_at=post.first_seen_at,
                    )
                    created_jobs += len(await monitor_repository.create_snapshot_jobs(post))
                else:
                    existing_processed += 1
                self._progress(saved=created_posts + existing_processed, completed=created_posts)

            # A stopped/partial scan must not claim the full discovery interval.
            if not discovery_error and not self._should_stop():
                await monitor_repository.update_account_discovered_at(account.id)
                self._discovery_retries.pop(account.sec_user_id, None)
                self._recovery.successful_request()
            if created_posts > 0:
                await self._create_alert(
                    alert_type="new_posts",
                    severity="info",
                    title="发现新作品",
                    message=f"发现 {created_posts} 篇新作品，生成 {created_jobs} 个快照任务。",
                    dedupe_key=f"new_posts:{int(time.time())}",
                    sec_user_id=account.sec_user_id,
                )
            await crawler_manager.add_log(
                f"[Monitor] [{account_name}] Discovery result: fetched={fetched_count}, existing={existing_processed}, "
                f"skipped_historical={skipped_historical}, new_posts={created_posts}, "
                f"new_jobs={created_jobs}, covers={updated_covers}",
                "success" if created_posts else "info",
            )
            result = {
                "status": "ok",
                "account_id": account.id,
                "fetched": fetched_count,
                "existing": existing_processed,
                "skipped_historical": skipped_historical,
                "created_posts": created_posts,
                "created_jobs": created_jobs,
                "updated_covers": updated_covers,
            }
            if discovery_error:
                failure = classify_collection_error(discovery_error)
                cooldown = 0
                cooldown = await self._handle_collection_failure(failure, "discovery", account.sec_user_id)
                self._progress(error=failure.as_dict())
                await crawler_manager.add_log(f"[Monitor] [{account_name}] [{failure.error_code}] {failure.message}；已保存部分数据", "warning")
                result.update(status="partial", reason=failure.message, **failure.as_dict(), retry_after_seconds=cooldown)
            return result

    async def get_hot_rank(self, force: bool = False, fetcher=None) -> dict:
        cache_ttl_seconds = 60
        now = time.time()
        if (
            not force
            and self._hot_rank_cache is not None
            and now - self._hot_rank_cached_at < cache_ttl_seconds
        ):
            return {**self._hot_rank_cache, "cached": True}

        async with self._lock:
            now = time.time()
            if self._recovery.pending or self._paused:
                message = "监控已暂停，请恢复监控后刷新热榜。" if self._paused else "浏览器正在自动恢复，请稍后刷新热榜。"
                if self._hot_rank_cache is not None:
                    return {**self._hot_rank_cache, "cached": True, "stale": True, "warning": message}
                raise MonitorHotRankError(message)
            if (
                not force
                and self._hot_rank_cache is not None
                and now - self._hot_rank_cached_at < cache_ttl_seconds
            ):
                return {**self._hot_rank_cache, "cached": True}
            if self._crawler_is_busy():
                if self._hot_rank_cache is not None:
                    return {
                        **self._hot_rank_cache,
                        "cached": True,
                        "stale": True,
                        "warning": "采集任务正在运行，当前显示最近一次热榜数据。",
                    }
                raise MonitorHotRankError("采集任务正在运行，请稍后刷新热榜。")
            if self._risk_control_cooldown_remaining():
                if self._hot_rank_cache is not None:
                    return {**self._hot_rank_cache, "cached": True, "stale": True, "warning": "风控冷却中，显示上次热榜数据。"}
                raise MonitorHotRankError("触发风控，请稍后重试")

            owns_fetcher = fetcher is None
            if owns_fetcher:
                fetcher = DouyinMonitorFetcher()
            try:
                async with fetcher as active_fetcher:
                    items = await active_fetcher.fetch_hot_rank()
            except MonitorBrowserNetworkError:
                raise
            except Exception as exc:
                failure = classify_collection_error(exc)
                await self._handle_collection_failure(failure, "hot_rank")
                if self._hot_rank_cache is not None:
                    return {
                        **self._hot_rank_cache,
                        "cached": True,
                        "stale": True,
                        "warning": "实时热榜刷新失败，当前显示最近一次成功数据。",
                    }
                raise MonitorHotRankError(failure.message) from exc

            if not items:
                raise MonitorHotRankError("抖音热榜暂时没有返回可用数据，请稍后重试。")
            result = {
                "generated_at": datetime.now().astimezone().isoformat(),
                "source": "douyin_hot_search",
                "cached": False,
                "stale": False,
                "items": items,
            }
            self._hot_rank_cache = result
            self._hot_rank_cached_at = time.time()
            self._recovery.successful_request()
            return result

    @monitored_operation("snapshots")
    async def run_due_snapshots(
        self,
        limit: int = 50,
        fetcher=None,
        now: Optional[int] = None,
    ) -> dict:
        async with self._lock:
            cooldown_remaining = self._risk_control_cooldown_remaining()
            if cooldown_remaining:
                return {"status": "deferred", "reason": "risk_control_cooldown", "retry_after_seconds": cooldown_remaining}
            if self._crawler_is_busy():
                return {"status": "skipped", "reason": "crawler already running"}

            due_jobs = await monitor_repository.list_due_jobs(now=now, limit=limit)
            self._progress(total=len(due_jobs))
            if not due_jobs:
                return {"status": "ok", "completed": 0, "retried": 0, "failed": 0, "skipped": 0, "deleted_posts": 0}

            account_names = {}
            for job in due_jobs:
                key = job.sec_user_id or "unassigned"
                if key not in account_names:
                    account = await monitor_repository.get_monitored_account(job.sec_user_id) if job.sec_user_id else None
                    account_names[key] = (account.display_name or account.sec_user_id) if account else job.sec_user_id or "未归属账号"
            self._progress(account_name=next(iter(account_names.values())) if len(account_names) == 1 else "多账号快照")

            await crawler_manager.add_log(
                f"[Monitor] [{self._execution.account_name}] Running {len(due_jobs)} due snapshot jobs",
                "info",
            )

            owns_fetcher = fetcher is None
            if owns_fetcher:
                fetcher = DouyinMonitorFetcher()
            self._configure_fetcher(fetcher)

            completed = 0
            retried = 0
            failed = 0
            skipped = 0
            deleted_posts = 0
            account_results: dict[str, dict[str, int]] = {}
            batch_failure = None
            async with fetcher as active_fetcher:
                for index, job in enumerate(due_jobs):
                    if self._should_stop():
                        break
                    current_account = await monitor_repository.get_monitored_account(job.sec_user_id) if job.sec_user_id else None
                    if current_account and getattr(current_account, "snapshots_paused", False):
                        # Keep the original schedule; resume never fabricates a missed snapshot.
                        skipped += 1
                        self._progress(processed=index + 1, skipped=skipped)
                        continue
                    account_name = account_names[job.sec_user_id or "unassigned"]
                    self._progress(phase="collecting", account_name=account_name, sec_user_id=job.sec_user_id, current_post=job.aweme_id)
                    running_job = await monitor_repository.mark_job_running(job.id)
                    if running_job is None:
                        self._progress(processed=index + 1)
                        continue
                    try:
                        metrics = await active_fetcher.fetch_metrics(job.aweme_id)
                        if metrics.get("cover_url"):
                            await monitor_repository.update_post_cover_url(
                                aweme_id=job.aweme_id,
                                cover_url=metrics["cover_url"],
                                platform=job.platform,
                            )
                        await monitor_repository.record_snapshot(
                            job_id=job.id,
                            liked_count=metrics.get("liked_count", 0),
                            collected_count=metrics.get("collected_count", 0),
                            comment_count=metrics.get("comment_count", 0),
                            share_count=metrics.get("share_count", 0),
                            captured_at=now,
                        )
                        self._clear_risk_control_cooldown()
                        self._recovery.successful_request()
                        completed += 1
                        result = account_results.setdefault(job.sec_user_id or "unassigned", {"completed": 0, "retried": 0, "failed": 0})
                        result["completed"] += 1
                    except DouyinPostUnavailableError as exc:
                        skipped_jobs = await monitor_repository.mark_post_deleted_and_skip_jobs(
                            aweme_id=job.aweme_id,
                            platform=job.platform,
                            reason=str(exc),
                        )
                        skipped += skipped_jobs
                        deleted_posts += 1
                        await crawler_manager.add_log(
                            f"[Monitor] [{account_name}] Post {job.aweme_id} was deleted; "
                            f"terminated {skipped_jobs} snapshot jobs",
                            "warning",
                        )
                    except Exception as exc:
                        failure = classify_collection_error(exc)
                        self._progress(error=failure.as_dict())
                        await crawler_manager.add_log(f"[Monitor] [{account_name}] [{failure.error_code}] {failure.message}", "warning")
                        risk_cooldown = await self._handle_collection_failure(failure, "snapshots", job.sec_user_id)
                        retry_job = await monitor_repository.mark_job_retry(
                            job_id=job.id,
                            error=f"[{failure.error_code}] {failure.message}",
                            retry_delay_seconds=risk_cooldown or config.RISK_CONTROL_RETRY_DELAY_SECONDS,
                        )
                        if retry_job and retry_job.status == "failed":
                            failed += 1
                            result = account_results.setdefault(job.sec_user_id or "unassigned", {"completed": 0, "retried": 0, "failed": 0})
                            result["failed"] += 1
                        else:
                            retried += 1
                            result = account_results.setdefault(job.sec_user_id or "unassigned", {"completed": 0, "retried": 0, "failed": 0})
                            result["retried"] += 1
                        if failure.error_code in ("risk_control", "login_required", "tab_changed", "browser_disconnected", "network_timeout"):
                            batch_failure = failure
                            self._progress(processed=index + 1, completed=completed, retried=retried, failed=failed, skipped=skipped)
                            break
                    self._progress(processed=index + 1, completed=completed, retried=retried, failed=failed, skipped=skipped)

            await crawler_manager.add_log(
                f"[Monitor] [快照批次] Snapshot cycle result: completed={completed}, retried={retried}, "
                f"failed={failed}, skipped={skipped}, deleted_posts={deleted_posts}",
                "success" if completed and not retried and not failed else "info",
            )
            for sec_user_id, result in account_results.items():
                await crawler_manager.add_log(
                    f"[Monitor] [{account_names[sec_user_id]}] Snapshot result: completed={result['completed']}, "
                    f"retried={result['retried']}, failed={result['failed']}",
                    "success" if result["completed"] and not result["retried"] and not result["failed"] else "info",
                )
            if retried > 0 or failed > 0:
                for sec_user_id, result in account_results.items():
                    if result["retried"] == 0 and result["failed"] == 0:
                        continue
                    severity = "error" if result["failed"] > 0 else "warning"
                    await self._create_alert(
                        alert_type="snapshot_errors",
                        severity=severity,
                        title="快照执行异常",
                        message=f"本轮完成 {result['completed']} 个，重试 {result['retried']} 个，失败 {result['failed']} 个。",
                        dedupe_key=f"snapshot_errors:{sec_user_id}:{int(time.time() // 3600)}",
                        sec_user_id=sec_user_id if sec_user_id != "unassigned" else "",
                    )
            result = {
                "status": "partial" if retried or failed else "ok",
                "completed": completed,
                "retried": retried,
                "failed": failed,
                "skipped": skipped,
                "deleted_posts": deleted_posts,
            }
            if retried or failed:
                result.update(reason=batch_failure.message if batch_failure else "部分任务未完成，已安排重试",
                              error_code=batch_failure.error_code if batch_failure else None,
                              retry_after_seconds=max(self._risk_control_cooldown_remaining(), self._recovery.snapshot()["retry_after_seconds"]))
            return result

    async def _create_alert(
        self,
        alert_type: str,
        severity: str,
        title: str,
        message: str,
        dedupe_key: str,
        sec_user_id: str = "",
    ) -> None:
        await monitor_repository.create_alert(
            alert_type=alert_type,
            severity=severity,
            title=title,
            message=message,
            dedupe_key=dedupe_key,
            sec_user_id=sec_user_id,
        )

    async def ensure_browser_ready(self) -> dict:
        """Start or reuse the dedicated browser when the backend starts."""
        async with self._lock, DouyinTabLease():
            if self._crawler_is_busy():
                return {"status": "skipped", "reason": "crawler already running"}
            async with async_playwright() as playwright:
                manager = CDPBrowserManager(profile_platform="dy")
                try:
                    browser_context = await manager.launch_and_connect(
                        playwright,
                        None,
                        None,
                        headless=config.CDP_HEADLESS,
                    )
                    crawler = DouYinCrawler()
                    crawler.browser_context = browser_context
                    page = await crawler._get_or_create_context_page(bootstrap=True)
                    await safe_page_goto(page, crawler.index_url, accepted_hosts=("douyin.com",))
                    if not config.CDP_HEADLESS:
                        await page.bring_to_front()
                finally:
                    await manager.cleanup()
        await crawler_manager.add_log("[Monitor] Dedicated browser is ready", "success")
        return {"status": "ok"}

    async def list_alerts(
        self,
        status: Optional[str] = None,
        limit: int = 200,
        account_id: Optional[int] = None,
        all_accounts: bool = False,
    ) -> dict:
        account = await self._resolve_account(account_id, all_accounts=all_accounts) if account_id is not None or all_accounts else None
        sec_user_id = account.sec_user_id if account else None
        alerts = await monitor_repository.list_alerts(status=status, limit=limit, sec_user_id=sec_user_id)
        unread = await monitor_repository.count_unread_alerts(sec_user_id=sec_user_id)
        return {
            "alerts": [
                {
                    "id": alert.id,
                    "alert_type": alert.alert_type,
                    "sec_user_id": alert.sec_user_id,
                    "severity": alert.severity,
                    "title": alert.title,
                    "message": alert.message,
                    "status": alert.status,
                    "created_at": alert.created_at,
                    "read_at": alert.read_at,
                }
                for alert in alerts
            ],
            "unread": unread,
        }

    async def mark_alert_read(self, alert_id: int) -> dict:
        alert = await monitor_repository.mark_alert_read(alert_id)
        if alert is None:
            raise ValueError(f"Alert not found: {alert_id}")
        return {"id": alert.id, "status": alert.status, "read_at": alert.read_at}

    async def mark_all_alerts_read(self, account_id: Optional[int] = None, all_accounts: bool = False) -> dict:
        account = await self._resolve_account(account_id, all_accounts=all_accounts) if account_id is not None or all_accounts else None
        count = await monitor_repository.mark_all_alerts_read(
            sec_user_id=account.sec_user_id if account else None,
        )
        return {"updated": count}

    async def update_alerts_status(self, alert_ids: list[int], status: str) -> dict:
        count = await monitor_repository.set_alerts_status(alert_ids=alert_ids, status=status)
        await crawler_manager.add_log(
            f"[Monitor] Updated {count} alerts to status={status}",
            "info",
        )
        return {"updated": count, "status": status}

    async def get_health_data(self, account_id: Optional[int] = None, all_accounts: bool = False) -> dict:
        now = int(time.time())
        checks: list[dict] = []
        try:
            account = await self._resolve_account(account_id, all_accounts=all_accounts)
            sec_user_id = account.sec_user_id if account else None
            job_counts = await monitor_repository.get_job_counts(sec_user_id=sec_user_id)
            last_snapshot = await monitor_repository.get_last_snapshot(sec_user_id=sec_user_id)
            next_job = await monitor_repository.get_next_pending_job(sec_user_id=sec_user_id)
            unread_alerts = await monitor_repository.count_unread_alerts(sec_user_id=sec_user_id)
            checks.append({"key": "database", "status": "ok", "value": "connected", "detail": ""})
        except Exception as exc:
            return {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "overall_status": "error",
                "checks": [{"key": "database", "status": "error", "value": "failed", "detail": str(exc)}],
                "metrics": {},
                "system_config": {},
            }

        browser_ok, browser_port = await CDPBrowserManager(profile_platform="dy").probe_existing_browser()
        checks.append({
            "key": "browser",
            "status": "ok" if browser_ok else "warning",
            "value": str(browser_port or "-"),
            "detail": "" if browser_ok else "No reusable browser is currently available.",
        })
        checks.append({
            "key": "monitor_loop",
            "status": "ok" if self.is_running else "error",
            "value": "running" if self.is_running else "stopped",
            "detail": "",
        })
        checks.append({
            "key": "account",
            "status": "ok" if account and account.enabled else "warning",
            "value": account.sec_user_id if account else "-",
            "detail": "" if account and account.enabled else "No enabled monitored account.",
        })

        freshness_status = "warning"
        freshness_value = "-"
        if account and account.last_discovered_at:
            age_seconds = max(0, now - int(account.last_discovered_at))
            max_age = max(1, account.discover_interval_minutes) * 60 * 2 + 120
            freshness_status = "ok" if age_seconds <= max_age else "warning"
            freshness_value = f"{age_seconds}s"
        checks.append({
            "key": "discovery",
            "status": freshness_status,
            "value": freshness_value,
            "detail": "" if freshness_status == "ok" else "Discovery has not completed recently.",
        })

        db_path = Path(config.SQLITE_DB_PATH)
        db_size = db_path.stat().st_size if db_path.exists() else 0
        disk = shutil.disk_usage(db_path.parent)
        disk_status = "ok" if disk.free > 1024 ** 3 else "warning"
        checks.append({
            "key": "disk",
            "status": disk_status,
            "value": f"{disk.free / (1024 ** 3):.1f} GB",
            "detail": "" if disk_status == "ok" else "Low disk space.",
        })

        backup_dir = Path(__file__).parent.parent.parent / "output" / "backups"
        backups = sorted(backup_dir.glob("sqlite_tables_*.db"), key=lambda path: path.stat().st_mtime, reverse=True) if backup_dir.exists() else []
        latest_backup_at = int(backups[0].stat().st_mtime) if backups else None
        backup_status = "ok"
        if not config.ENABLE_AUTO_BACKUP or not latest_backup_at:
            backup_status = "warning"
        elif now - latest_backup_at > max(1, int(config.BACKUP_INTERVAL_HOURS)) * 3600 * 2:
            backup_status = "warning"
        checks.append({
            "key": "backup",
            "status": backup_status,
            "value": str(len(backups)),
            "detail": "" if backup_status == "ok" else "No recent SQLite backup found.",
        })

        status_rank = {"ok": 0, "warning": 1, "error": 2}
        overall_status = max((check["status"] for check in checks), key=lambda value: status_rank[value])
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "overall_status": overall_status,
            "checks": checks,
            "metrics": {
                "jobs": job_counts,
                "unread_alerts": unread_alerts,
                "db_size_bytes": db_size,
                "disk_free_bytes": disk.free,
                "last_snapshot_at": last_snapshot.captured_at if last_snapshot else None,
                "next_snapshot_at": next_job.due_at if next_job else None,
                "last_backup_at": latest_backup_at,
                "backup_count": len(backups),
            },
            "system_config": {
                "auto_backup": bool(config.ENABLE_AUTO_BACKUP),
                "backup_interval_hours": int(config.BACKUP_INTERVAL_HOURS),
                "backup_retention_days": int(config.BACKUP_RETENTION_DAYS),
                "log_retention_days": int(config.LOG_RETENTION_DAYS),
                "start_browser_on_service_start": bool(config.START_BROWSER_ON_SERVICE_START),
                "cdp_debug_port": int(config.CDP_DEBUG_PORT),
                "maintenance_check_interval_seconds": int(config.MAINTENANCE_CHECK_INTERVAL_SECONDS),
            },
        }

    async def get_dashboard_data(self, limit: Optional[int] = None, account_id: Optional[int] = None, all_accounts: bool = False) -> dict:
        """Return the data needed by the WebUI monitoring dashboard."""
        account = await self._resolve_account(account_id, all_accounts=all_accounts)
        sec_user_id = account.sec_user_id if account else None
        posts = await monitor_repository.list_posts(limit=limit, sec_user_id=sec_user_id)
        post_count = await monitor_repository.count_posts(sec_user_id=sec_user_id)
        snapshots = await monitor_repository.list_snapshots(
            aweme_ids=[post.aweme_id for post in posts],
            limit=None,
            sec_user_id=sec_user_id,
        )
        job_counts = await monitor_repository.get_job_counts(sec_user_id=sec_user_id)

        snapshots_by_post: dict[str, list[dict]] = {}
        for snapshot in sorted(snapshots, key=lambda item: item.captured_at):
            snapshots_by_post.setdefault(snapshot.aweme_id, []).append({
                "stage": snapshot.stage,
                "due_at": snapshot.due_at,
                "captured_at": snapshot.captured_at,
                "actual_age_seconds": snapshot.actual_age_seconds,
                "liked_count": snapshot.liked_count,
                "collected_count": snapshot.collected_count,
                "comment_count": snapshot.comment_count,
                "share_count": snapshot.share_count,
            })

        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "account": {
                "id": account.id,
                "sec_user_id": account.sec_user_id,
                "display_name": account.display_name or account.sec_user_id,
                "profile_url": account.profile_url,
                "enabled": account.enabled,
                "discover_interval_minutes": account.discover_interval_minutes,
                "last_discovered_at": account.last_discovered_at,
            } if account else None,
            "counts": {
                "posts": post_count,
                "snapshots": len(snapshots),
                "jobs": job_counts,
            },
            "posts": [
                {
                    "aweme_id": post.aweme_id,
                    "title": post.title,
                    "desc": post.desc,
                    "create_time": post.create_time,
                    "first_seen_at": post.first_seen_at,
                    "canonical_url": post.canonical_url,
                    "cover_url": post.cover_url,
                    "status": post.status,
                    "snapshots": snapshots_by_post.get(post.aweme_id, []),
                }
                for post in posts
            ],
        }

    async def get_account_comparison(self, limit: int = 100) -> dict:
        accounts = await monitor_repository.list_monitored_accounts()
        result = []
        for account in accounts:
            posts = await monitor_repository.list_posts(limit=limit, sec_user_id=account.sec_user_id)
            snapshots = await monitor_repository.list_snapshots(limit=100000, sec_user_id=account.sec_user_id)
            job_counts = await monitor_repository.get_job_counts(sec_user_id=account.sec_user_id)
            latest_by_post = {}
            for snapshot in snapshots:
                current = latest_by_post.get(snapshot.aweme_id)
                if current is None or snapshot.captured_at > current.captured_at:
                    latest_by_post[snapshot.aweme_id] = snapshot
            interactions = [
                (latest_by_post[post.aweme_id].liked_count
                 + latest_by_post[post.aweme_id].collected_count
                 + latest_by_post[post.aweme_id].comment_count
                 + latest_by_post[post.aweme_id].share_count)
                for post in posts if post.aweme_id in latest_by_post
            ]
            sorted_interactions = sorted(interactions)
            count = len(sorted_interactions)
            median_value = 0 if count == 0 else (
                sorted_interactions[count // 2]
                if count % 2
                else (sorted_interactions[count // 2 - 1] + sorted_interactions[count // 2]) / 2
            )
            average_value = sum(sorted_interactions) / count if count else 0
            burst_threshold = max(median_value * 2, 1)
            result.append({
                "id": account.id,
                "display_name": account.display_name or account.sec_user_id,
                "sec_user_id": account.sec_user_id,
                "enabled": account.enabled,
                "profile_url": account.profile_url,
                "last_discovered_at": account.last_discovered_at,
                "posts": len(posts),
                "snapshots": len(snapshots),
                "total_interaction": sum(sorted_interactions),
                "average_interaction": round(average_value, 2),
                "median_interaction": round(median_value, 2),
                "burst_rate": round(sum(1 for value in sorted_interactions if value >= burst_threshold) / count * 100, 2) if count else 0,
                "zero_rate": round(sum(1 for value in sorted_interactions if value == 0) / count * 100, 2) if count else 0,
                "jobs": job_counts,
            })
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "accounts": result,
        }

    async def get_overview_data(self, account_id: Optional[int] = None, all_accounts: bool = False) -> dict:
        """Return the operational overview shown on the first WebUI tab."""
        now = int(time.time())
        account = await self._resolve_account(account_id, all_accounts=all_accounts)
        sec_user_id = account.sec_user_id if account else None
        job_counts = await monitor_repository.get_job_counts(sec_user_id=sec_user_id)
        next_job = await monitor_repository.get_next_pending_job(sec_user_id=sec_user_id)
        next_job_post = (
            await monitor_repository.get_post(next_job.aweme_id)
            if next_job else None
        )
        start_of_day = int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
        today_new_posts = await monitor_repository.count_posts_since(start_of_day, sec_user_id=sec_user_id)
        abnormal_jobs = await monitor_repository.list_recent_abnormal_jobs(limit=10, sec_user_id=sec_user_id)

        next_discovery_at = None
        if account and account.last_discovered_at:
            next_discovery_at = account.last_discovered_at + max(1, account.discover_interval_minutes) * 60

        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "now": now,
            "loop_running": self.is_running,
            "account": {
                "id": account.id,
                "sec_user_id": account.sec_user_id,
                "display_name": account.display_name or account.sec_user_id,
                "profile_url": account.profile_url,
                "enabled": account.enabled,
                "discover_interval_minutes": account.discover_interval_minutes,
                "last_discovered_at": account.last_discovered_at,
            } if account else None,
            "next_discovery_at": next_discovery_at,
            "next_snapshot": {
                "id": next_job.id,
                "aweme_id": next_job.aweme_id,
                "title": next_job_post.title if next_job_post else next_job.aweme_id,
                "stage": next_job.stage,
                "due_at": next_job.due_at,
            } if next_job else None,
            "today_new_posts": today_new_posts,
            "jobs": job_counts,
            "abnormal_total": int(job_counts.get("failed", 0)),
            "recent_abnormal_jobs": abnormal_jobs,
        }

    async def list_jobs(self, status: Optional[str] = None, limit: Optional[int] = None, account_id: Optional[int] = None, all_accounts: bool = False) -> dict:
        account = await self._resolve_account(account_id, all_accounts=all_accounts)
        sec_user_id = account.sec_user_id if account else None
        normalized_status = str(status or "").strip().lower()
        statuses = ("failed",) if normalized_status == "abnormal" else None
        exact_status = normalized_status if normalized_status and normalized_status not in {"all", "abnormal"} else None
        jobs = await monitor_repository.list_jobs(
            status=exact_status,
            statuses=statuses,
            limit=limit,
            sec_user_id=sec_user_id,
        )
        for job in jobs:
            job["error_category"] = classify_job_error(job)
        status_counts = await monitor_repository.get_job_counts(sec_user_id=sec_user_id)
        total_count = sum(status_counts.values())
        if normalized_status == "abnormal":
            filtered_count = int(status_counts.get("failed", 0))
        elif exact_status:
            filtered_count = int(status_counts.get(exact_status, 0))
        else:
            filtered_count = total_count
        return {
            "jobs": jobs,
            "count": filtered_count,
            "returned_count": len(jobs),
            "total_count": total_count,
            "status_counts": status_counts,
        }

    async def retry_job(self, job_id: int) -> dict:
        job = await monitor_repository.retry_failed_job(job_id)
        if job is None:
            raise ValueError(f"Monitor job not found: {job_id}")
        await crawler_manager.add_log(f"[Monitor] Job {job_id} manually retried", "info")
        return {
            "id": job.id,
            "aweme_id": job.aweme_id,
            "stage": job.stage,
            "status": job.status,
            "due_at": job.due_at,
            "attempts": job.attempts,
        }

    async def retry_failed_jobs(
        self,
        job_ids: Optional[list[int]] = None,
        account_id: Optional[int] = None,
    ) -> dict:
        account = await monitor_repository.get_monitored_account_by_id(account_id) if account_id is not None else None
        if account_id is not None and account is None:
            raise ValueError(f"Monitored account not found: {account_id}")
        count = await monitor_repository.retry_failed_jobs(
            job_ids=job_ids,
            sec_user_id=account.sec_user_id if account else None,
        )
        await crawler_manager.add_log(f"[Monitor] Manually retried {count} failed jobs", "info")
        return {"updated": count}


monitor_service = MonitorService()
