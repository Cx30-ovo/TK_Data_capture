# -*- coding: utf-8 -*-
"""Business service linking the monitor repository with the Douyin crawler."""

import asyncio
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from playwright.async_api import async_playwright

import config
from database.monitor_repository import monitor_repository
from media_platform.douyin.core import DouYinCrawler
from tools.cdp_browser import CDPBrowserManager

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
                await self._create_alert(
                    alert_type="loop_error",
                    severity="error",
                    title="监控循环异常",
                    message=str(exc),
                    dedupe_key=f"loop_error:{datetime.now().strftime('%Y-%m-%d')}",
                )
                await crawler_manager.add_log(f"[Monitor] Loop error: {exc}", "error")
            await asyncio.sleep(60)

    async def _run_cycle(self) -> None:
        if self._crawler_is_busy():
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
            if created_posts > 0:
                await self._create_alert(
                    alert_type="new_posts",
                    severity="info",
                    title="发现新作品",
                    message=f"发现 {created_posts} 篇新作品，生成 {created_jobs} 个快照任务。",
                    dedupe_key=f"new_posts:{int(time.time())}",
                )
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
            if retried > 0 or failed > 0:
                severity = "error" if failed > 0 else "warning"
                await self._create_alert(
                    alert_type="snapshot_errors",
                    severity=severity,
                    title="快照执行异常",
                    message=f"本轮完成 {completed} 个，重试 {retried} 个，失败 {failed} 个。",
                    dedupe_key=f"snapshot_errors:{int(time.time() // 3600)}",
                )
            return {"status": "ok", "completed": completed, "retried": retried, "failed": failed}

    async def _create_alert(
        self,
        alert_type: str,
        severity: str,
        title: str,
        message: str,
        dedupe_key: str,
    ) -> None:
        await monitor_repository.create_alert(
            alert_type=alert_type,
            severity=severity,
            title=title,
            message=message,
            dedupe_key=dedupe_key,
        )

    async def list_alerts(self, status: Optional[str] = None, limit: int = 200) -> dict:
        alerts = await monitor_repository.list_alerts(status=status, limit=limit)
        unread = await monitor_repository.count_unread_alerts()
        return {
            "alerts": [
                {
                    "id": alert.id,
                    "alert_type": alert.alert_type,
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

    async def mark_all_alerts_read(self) -> dict:
        count = await monitor_repository.mark_all_alerts_read()
        return {"updated": count}

    async def get_health_data(self) -> dict:
        now = int(time.time())
        checks: list[dict] = []
        try:
            job_counts = await monitor_repository.get_job_counts()
            last_snapshot = await monitor_repository.get_last_snapshot()
            next_job = await monitor_repository.get_next_pending_job()
            account = await monitor_repository.get_enabled_monitored_account()
            unread_alerts = await monitor_repository.count_unread_alerts()
            checks.append({"key": "database", "status": "ok", "value": "connected", "detail": ""})
        except Exception as exc:
            return {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "overall_status": "error",
                "checks": [{"key": "database", "status": "error", "value": "failed", "detail": str(exc)}],
                "metrics": {},
            }

        browser_ok, browser_port = await CDPBrowserManager().probe_existing_browser()
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
            },
        }

    async def get_dashboard_data(self, limit: int = 100) -> dict:
        """Return the data needed by the WebUI monitoring dashboard."""
        account = await monitor_repository.get_enabled_monitored_account()
        posts = await monitor_repository.list_posts(limit=limit)
        snapshots = await monitor_repository.list_snapshots(limit=1000)
        job_counts = await monitor_repository.get_job_counts()

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
                "profile_url": account.profile_url,
                "enabled": account.enabled,
                "discover_interval_minutes": account.discover_interval_minutes,
                "last_discovered_at": account.last_discovered_at,
            } if account else None,
            "counts": {
                "posts": len(posts),
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
                    "status": post.status,
                    "snapshots": snapshots_by_post.get(post.aweme_id, []),
                }
                for post in posts
            ],
        }

    async def get_overview_data(self) -> dict:
        """Return the operational overview shown on the first WebUI tab."""
        now = int(time.time())
        account = await monitor_repository.get_enabled_monitored_account()
        job_counts = await monitor_repository.get_job_counts()
        next_job = await monitor_repository.get_next_pending_job()
        next_job_post = (
            await monitor_repository.get_post(next_job.aweme_id)
            if next_job else None
        )
        start_of_day = int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
        today_new_posts = await monitor_repository.count_posts_since(start_of_day)
        abnormal_jobs = await monitor_repository.list_recent_abnormal_jobs(limit=10)

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
            "abnormal_total": int(job_counts.get("failed", 0)) + int(job_counts.get("missed", 0)),
            "recent_abnormal_jobs": abnormal_jobs,
        }

    async def list_jobs(self, status: Optional[str] = None, limit: int = 300) -> dict:
        jobs = await monitor_repository.list_jobs(status=status, limit=limit)
        return {"jobs": jobs, "count": len(jobs)}

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


monitor_service = MonitorService()
