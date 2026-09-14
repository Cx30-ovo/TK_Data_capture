# -*- coding: utf-8 -*-
"""Business service linking the monitor repository with the Douyin crawler."""

import asyncio
import time
from typing import Any, Optional

from playwright.async_api import async_playwright

import config
from database.monitor_repository import monitor_repository
from media_platform.douyin.core import DouYinCrawler

from .crawler_manager import crawler_manager


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class DouyinMonitorFetcher:
    """Small crawler adapter used by the monitor service."""

    def __init__(self):
        self._playwright = None
        self._crawler: Optional[DouYinCrawler] = None
        self._client = None

    async def __aenter__(self) -> "DouyinMonitorFetcher":
        self._playwright = await async_playwright().start()
        self._crawler = DouYinCrawler()
        browser_context = await self._crawler.launch_browser_with_cdp(
            self._playwright,
            None,
            None,
            headless=config.CDP_HEADLESS,
        )
        self._crawler.browser_context = browser_context
        self._crawler.context_page = await self._crawler._get_or_create_context_page()
        await self._crawler.context_page.goto(self._crawler.index_url)
        self._client = await self._crawler.create_douyin_client(None)
        if not await self._client.pong(browser_context=self._crawler.browser_context):
            raise RuntimeError("Douyin login required. Please run a normal crawler task first to refresh the login state.")
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._crawler and self._crawler.cdp_manager:
            await self._crawler.cdp_manager.cleanup()
        if self._playwright:
            await self._playwright.stop()
        self._crawler = None
        self._client = None
        self._playwright = None

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
    ) -> list[dict]:
        posts: list[dict] = []
        max_cursor = ""
        pages = 0

        while pages < max_pages:
            response = await self._client.get_user_aweme_posts(sec_user_id, max_cursor)
            aweme_list = response.get("aweme_list") or []
            if not aweme_list:
                break

            for item in aweme_list:
                aweme_id = str(item.get("aweme_id") or "")
                if not aweme_id:
                    continue
                if aweme_id in known_ids:
                    continue
                posts.append(self._normalize_post(item, sec_user_id))

            pages += 1
            if not response.get("has_more"):
                break

            next_cursor = response.get("max_cursor")
            if not next_cursor or next_cursor == max_cursor:
                break
            max_cursor = next_cursor

        return posts

    async def fetch_metrics(self, aweme_id: str) -> dict:
        detail = await self._client.get_video_by_id(aweme_id)
        if not detail:
            raise RuntimeError(f"Failed to get Douyin detail for aweme_id={aweme_id}")
        statistics = detail.get("statistics") or {}
        return {
            "liked_count": _to_int(statistics.get("digg_count")),
            "collected_count": _to_int(statistics.get("collect_count")),
            "comment_count": _to_int(statistics.get("comment_count")),
            "share_count": _to_int(statistics.get("share_count")),
        }


class MonitorService:
    """Coordinates incremental discovery and due snapshot execution."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None

    @property
    def is_running(self) -> bool:
        return bool(self._task and not self._task.done())

    async def start(self) -> None:
        if not self.is_running:
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
                await self._run_cycle()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await crawler_manager.add_log(f"[Monitor] Loop error: {exc}", "error")
            await asyncio.sleep(60)

    async def _run_cycle(self) -> None:
        if self._crawler_is_busy():
            return

        await self.run_due_snapshots()

        account = await monitor_repository.get_enabled_monitored_account()
        if account is None:
            return
        now = int(time.time())
        interval_seconds = max(1, account.discover_interval_minutes) * 60
        last_discovered_at = int(account.last_discovered_at or 0)
        if now - last_discovered_at >= interval_seconds:
            await self.discover_account(sec_user_id=account.sec_user_id)

    def _crawler_is_busy(self) -> bool:
        return bool(crawler_manager.process and crawler_manager.process.poll() is None)

    async def discover_account(
        self,
        sec_user_id: Optional[str] = None,
        fetcher=None,
        max_pages: Optional[int] = None,
    ) -> dict:
        async with self._lock:
            if self._crawler_is_busy():
                return {"status": "skipped", "reason": "crawler already running"}

            account = (
                await monitor_repository.get_monitored_account(sec_user_id)
                if sec_user_id
                else await monitor_repository.get_enabled_monitored_account()
            )
            if account is None:
                return {"status": "skipped", "reason": "no enabled monitored account"}

            known_ids = await monitor_repository.list_post_ids(account.sec_user_id, account.platform)
            page_limit = max_pages if max_pages is not None else (1 if not known_ids else 3)
            owns_fetcher = fetcher is None
            if owns_fetcher:
                fetcher = DouyinMonitorFetcher()
            await crawler_manager.add_log(
                f"[Monitor] Discovering new posts for {account.sec_user_id}, known={len(known_ids)}, pages={page_limit}",
                "info",
            )

            async with fetcher as active_fetcher:
                posts = await active_fetcher.fetch_latest_posts(
                    sec_user_id=account.sec_user_id,
                    known_ids=known_ids,
                    max_pages=page_limit,
                )

            created_posts = 0
            created_jobs = 0
            for item in posts:
                post, created = await monitor_repository.upsert_post(
                    aweme_id=item["aweme_id"],
                    sec_user_id=item["sec_user_id"],
                    title=item.get("title", ""),
                    desc=item.get("desc", ""),
                    create_time=item["create_time"],
                    canonical_url=item["canonical_url"],
                    platform=item.get("platform", "dy"),
                    status=item.get("status", "active"),
                    source=item.get("source", "creator_monitor"),
                )
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

            await monitor_repository.update_account_discovered_at(account.id)
            await crawler_manager.add_log(
                f"[Monitor] Discovery result: fetched={len(posts)}, new_posts={created_posts}, new_jobs={created_jobs}",
                "success" if created_posts else "info",
            )
            return {
                "status": "ok",
                "account_id": account.id,
                "fetched": len(posts),
                "created_posts": created_posts,
                "created_jobs": created_jobs,
            }

    async def run_due_snapshots(
        self,
        limit: int = 50,
        fetcher=None,
        now: Optional[int] = None,
    ) -> dict:
        async with self._lock:
            if self._crawler_is_busy():
                return {"status": "skipped", "reason": "crawler already running"}

            due_jobs = await monitor_repository.list_due_jobs(now=now, limit=limit)
            if not due_jobs:
                return {"status": "ok", "completed": 0, "retried": 0, "failed": 0}

            await crawler_manager.add_log(
                f"[Monitor] Running {len(due_jobs)} due snapshot jobs",
                "info",
            )

            owns_fetcher = fetcher is None
            if owns_fetcher:
                fetcher = DouyinMonitorFetcher()

            completed = 0
            retried = 0
            failed = 0
            async with fetcher as active_fetcher:
                for job in due_jobs:
                    running_job = await monitor_repository.mark_job_running(job.id)
                    if running_job is None:
                        continue
                    try:
                        metrics = await active_fetcher.fetch_metrics(job.aweme_id)
                        await monitor_repository.record_snapshot(
                            job_id=job.id,
                            liked_count=metrics.get("liked_count", 0),
                            collected_count=metrics.get("collected_count", 0),
                            comment_count=metrics.get("comment_count", 0),
                            share_count=metrics.get("share_count", 0),
                            captured_at=now,
                        )
                        completed += 1
                    except Exception as exc:
                        retry_job = await monitor_repository.mark_job_retry(
                            job_id=job.id,
                            error=str(exc),
                            retry_delay_seconds=config.RISK_CONTROL_RETRY_DELAY_SECONDS,
                        )
                        if retry_job and retry_job.status == "failed":
                            failed += 1
                        else:
                            retried += 1

            await crawler_manager.add_log(
                f"[Monitor] Snapshot cycle result: completed={completed}, retried={retried}, failed={failed}",
                "success" if completed and not retried and not failed else "info",
            )
            return {"status": "ok", "completed": completed, "retried": retried, "failed": failed}


monitor_service = MonitorService()
