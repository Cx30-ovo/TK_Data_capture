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
from tools.cdp_browser import CDPBrowserManager, safe_page_goto

from .crawler_manager import crawler_manager


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def classify_job_error(job: dict) -> str:
    text = f"{job.get('last_error') or ''} {job.get('miss_reason') or ''}".lower()
    if not text.strip():
        return "none"
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
        await safe_page_goto(
            self._crawler.context_page,
            self._crawler.index_url,
            accepted_hosts=("douyin.com",),
        )
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
        await crawler_manager.add_log(f"[Monitor] Browser disconnected, reconnecting: {reason}", "warning")
        await self.__aexit__(type(reason), reason, reason.__traceback__)
        await self.__aenter__()

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
    ) -> list[dict]:
        try:
            return await self._fetch_latest_posts_once(sec_user_id, known_ids, max_pages)
        except Exception as exc:
            if not self._is_browser_disconnect_error(exc):
                raise
            await self._reconnect(exc)
            return await self._fetch_latest_posts_once(sec_user_id, known_ids, max_pages)

    async def _fetch_latest_posts_once(
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
                normalized = self._normalize_post(item, sec_user_id)
                normalized["is_known"] = aweme_id in known_ids
                posts.append(normalized)

            pages += 1
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
        detail = await self._client.get_video_by_id(aweme_id)
        if not detail:
            raise RuntimeError(f"Failed to get Douyin detail for aweme_id={aweme_id}")
        statistics = detail.get("statistics") or {}
        return {
            "liked_count": _to_int(statistics.get("digg_count")),
            "collected_count": _to_int(statistics.get("collect_count")),
            "comment_count": _to_int(statistics.get("comment_count")),
            "share_count": _to_int(statistics.get("share_count")),
            "cover_url": self._extract_cover_url(detail),
        }


class MonitorService:
    """Coordinates incremental discovery and due snapshot execution."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None

    @property
    def is_running(self) -> bool:
        return bool(self._task and not self._task.done())

    async def _resolve_account(self, account_id: Optional[int] = None, all_accounts: bool = False):
        if all_accounts:
            return None
        if account_id is not None:
            return await monitor_repository.get_monitored_account_by_id(account_id)
        return await monitor_repository.get_enabled_monitored_account()

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

        accounts = await monitor_repository.list_monitored_accounts(include_disabled=False)
        now = int(time.time())
        for account in accounts:
            interval_seconds = max(1, account.discover_interval_minutes) * 60
            last_discovered_at = int(account.last_discovered_at or 0)
            if now - last_discovered_at < interval_seconds:
                continue
            await crawler_manager.add_log(
                f"[Monitor] Multi-account discovery due for {account.display_name or account.sec_user_id}",
                "info",
            )
            await self.discover_account(sec_user_id=account.sec_user_id)

    def _crawler_is_busy(self) -> bool:
        return bool(crawler_manager.process and crawler_manager.process.poll() is None)

    async def discover_account(
        self,
        sec_user_id: Optional[str] = None,
        fetcher=None,
        max_pages: Optional[int] = None,
        backfill_covers: bool = False,
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
            if max_pages is not None:
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
                if backfill_covers:
                    for item in posts:
                        if item.get("cover_url"):
                            continue
                        try:
                            metrics = await active_fetcher.fetch_metrics(item["aweme_id"])
                        except Exception as exc:
                            await crawler_manager.add_log(
                                f"[Monitor] Cover backfill skipped for {item['aweme_id']}: {exc}",
                                "warning",
                            )
                            continue
                        if metrics.get("cover_url"):
                            item["cover_url"] = metrics["cover_url"]

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
                    cover_url=item.get("cover_url", ""),
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
                    sec_user_id=account.sec_user_id,
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
                "updated_covers": sum(1 for item in posts if item.get("cover_url")),
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
            account_results: dict[str, dict[str, int]] = {}
            async with fetcher as active_fetcher:
                for job in due_jobs:
                    running_job = await monitor_repository.mark_job_running(job.id)
                    if running_job is None:
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
                        completed += 1
                        result = account_results.setdefault(job.sec_user_id or "unassigned", {"completed": 0, "retried": 0, "failed": 0})
                        result["completed"] += 1
                    except Exception as exc:
                        retry_job = await monitor_repository.mark_job_retry(
                            job_id=job.id,
                            error=str(exc),
                            retry_delay_seconds=config.RISK_CONTROL_RETRY_DELAY_SECONDS,
                        )
                        if retry_job and retry_job.status == "failed":
                            failed += 1
                            result = account_results.setdefault(job.sec_user_id or "unassigned", {"completed": 0, "retried": 0, "failed": 0})
                            result["failed"] += 1
                        else:
                            retried += 1
                            result = account_results.setdefault(job.sec_user_id or "unassigned", {"completed": 0, "retried": 0, "failed": 0})
                            result["retried"] += 1

            await crawler_manager.add_log(
                f"[Monitor] Snapshot cycle result: completed={completed}, retried={retried}, failed={failed}",
                "success" if completed and not retried and not failed else "info",
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
            return {"status": "ok", "completed": completed, "retried": retried, "failed": failed}

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
        if self._crawler_is_busy():
            return {"status": "skipped", "reason": "crawler already running"}

        async with async_playwright() as playwright:
            manager = CDPBrowserManager()
            browser_context = await manager.launch_and_connect(
                playwright,
                None,
                None,
                headless=config.CDP_HEADLESS,
            )
            crawler = DouYinCrawler()
            crawler.browser_context = browser_context
            page = await crawler._get_or_create_context_page()
            await safe_page_goto(page, crawler.index_url, accepted_hosts=("douyin.com",))
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
            "abnormal_total": int(job_counts.get("failed", 0)) + int(job_counts.get("missed", 0)),
            "recent_abnormal_jobs": abnormal_jobs,
        }

    async def list_jobs(self, status: Optional[str] = None, limit: Optional[int] = None, account_id: Optional[int] = None, all_accounts: bool = False) -> dict:
        account = await self._resolve_account(account_id, all_accounts=all_accounts)
        jobs = await monitor_repository.list_jobs(
            status=status,
            limit=limit,
            sec_user_id=account.sec_user_id if account else None,
        )
        for job in jobs:
            job["error_category"] = classify_job_error(job)
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

    async def retry_failed_jobs(self, job_ids: Optional[list[int]] = None) -> dict:
        count = await monitor_repository.retry_failed_jobs(job_ids=job_ids)
        await crawler_manager.add_log(f"[Monitor] Manually retried {count} failed jobs", "info")
        return {"updated": count}


monitor_service = MonitorService()
