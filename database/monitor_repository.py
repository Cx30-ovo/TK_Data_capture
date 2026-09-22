# -*- coding: utf-8 -*-
"""Persistence helpers for the single-account Douyin monitor module."""

import time
from typing import Optional, Sequence

from sqlalchemy import func, select

from .db_session import get_monitor_session
from .models import (
    MonitorAlert,
    DouyinMonitorJob,
    DouyinMonitoredAccount,
    DouyinPost,
    DouyinPostSnapshot,
)


SNAPSHOT_STAGES: tuple[tuple[str, int], ...] = (
    ("1h", 1 * 60 * 60),
    ("6h", 6 * 60 * 60),
    ("24h", 24 * 60 * 60),
    ("72h", 72 * 60 * 60),
    ("7d", 7 * 24 * 60 * 60),
)

SNAPSHOT_ALLOWED_WINDOWS: dict[str, int] = {
    "1h": 30 * 60,
    "6h": 2 * 60 * 60,
    "24h": 6 * 60 * 60,
    "72h": 12 * 60 * 60,
    "7d": 24 * 60 * 60,
}

ALERT_STATUSES = {"unread", "read", "resolved", "ignored"}


def _now_seconds() -> int:
    return int(time.time())


class MonitorRepository:
    """CRUD and state transitions for monitor accounts, posts, jobs and snapshots."""

    async def upsert_monitored_account(
        self,
        sec_user_id: str,
        display_name: str = "",
        profile_url: str = "",
        platform: str = "dy",
        enabled: bool = True,
        discover_interval_minutes: int = 30,
    ) -> DouyinMonitoredAccount:
        now = _now_seconds()
        async with get_monitor_session() as session:
            stmt = select(DouyinMonitoredAccount).where(
                DouyinMonitoredAccount.platform == platform,
                DouyinMonitoredAccount.sec_user_id == sec_user_id,
            )
            account = (await session.execute(stmt)).scalar_one_or_none()
            if account is None:
                account = DouyinMonitoredAccount(
                    platform=platform,
                    sec_user_id=sec_user_id,
                    display_name=display_name,
                    profile_url=profile_url,
                    enabled=enabled,
                    discover_interval_minutes=discover_interval_minutes,
                    created_at=now,
                    updated_at=now,
                )
                session.add(account)
            else:
                account.display_name = display_name or account.display_name
                account.profile_url = profile_url or account.profile_url
                account.enabled = enabled
                account.discover_interval_minutes = discover_interval_minutes
                account.updated_at = now
            await session.flush()
            return account

    async def list_monitored_accounts(
        self,
        platform: str = "dy",
        include_disabled: bool = True,
    ) -> list[DouyinMonitoredAccount]:
        async with get_monitor_session() as session:
            stmt = select(DouyinMonitoredAccount).where(DouyinMonitoredAccount.platform == platform)
            if not include_disabled:
                stmt = stmt.where(DouyinMonitoredAccount.enabled.is_(True))
            stmt = stmt.order_by(DouyinMonitoredAccount.id.asc())
            return list((await session.execute(stmt)).scalars().all())

    async def get_monitored_account_by_id(
        self,
        account_id: int,
    ) -> Optional[DouyinMonitoredAccount]:
        async with get_monitor_session() as session:
            return await session.get(DouyinMonitoredAccount, account_id)

    async def update_monitored_account(
        self,
        account_id: int,
        sec_user_id: Optional[str] = None,
        display_name: Optional[str] = None,
        profile_url: Optional[str] = None,
        enabled: Optional[bool] = None,
        discover_interval_minutes: Optional[int] = None,
    ) -> Optional[DouyinMonitoredAccount]:
        now = _now_seconds()
        async with get_monitor_session() as session:
            account = await session.get(DouyinMonitoredAccount, account_id)
            if account is None:
                return None
            if sec_user_id is not None:
                account.sec_user_id = sec_user_id
            if display_name is not None:
                account.display_name = display_name
            if profile_url is not None:
                account.profile_url = profile_url
            if enabled is not None:
                account.enabled = enabled
            if discover_interval_minutes is not None:
                account.discover_interval_minutes = discover_interval_minutes
            account.updated_at = now
            await session.flush()
            return account

    async def delete_monitored_account(self, account_id: int) -> bool:
        async with get_monitor_session() as session:
            account = await session.get(DouyinMonitoredAccount, account_id)
            if account is None:
                return False
            await session.delete(account)
            await session.flush()
            return True

    async def get_monitored_account(
        self,
        sec_user_id: str,
        platform: str = "dy",
    ) -> Optional[DouyinMonitoredAccount]:
        async with get_monitor_session() as session:
            stmt = select(DouyinMonitoredAccount).where(
                DouyinMonitoredAccount.platform == platform,
                DouyinMonitoredAccount.sec_user_id == sec_user_id,
            )
            return (await session.execute(stmt)).scalar_one_or_none()

    async def get_enabled_monitored_account(
        self,
        platform: str = "dy",
    ) -> Optional[DouyinMonitoredAccount]:
        async with get_monitor_session() as session:
            stmt = (
                select(DouyinMonitoredAccount)
                .where(
                    DouyinMonitoredAccount.platform == platform,
                    DouyinMonitoredAccount.enabled.is_(True),
                )
                .order_by(DouyinMonitoredAccount.id.asc())
                .limit(1)
            )
            return (await session.execute(stmt)).scalar_one_or_none()

    async def update_account_discovered_at(
        self,
        account_id: int,
        discovered_at: Optional[int] = None,
    ) -> Optional[DouyinMonitoredAccount]:
        current_time = discovered_at or _now_seconds()
        async with get_monitor_session() as session:
            account = await session.get(DouyinMonitoredAccount, account_id)
            if account is None:
                return None
            account.last_discovered_at = current_time
            account.updated_at = current_time
            await session.flush()
            return account

    async def list_post_ids(
        self,
        sec_user_id: str,
        platform: str = "dy",
    ) -> set[str]:
        async with get_monitor_session() as session:
            stmt = select(DouyinPost.aweme_id).where(
                DouyinPost.platform == platform,
                DouyinPost.sec_user_id == sec_user_id,
            )
            return set((await session.execute(stmt)).scalars().all())

    async def list_posts(
        self,
        platform: str = "dy",
        sec_user_id: Optional[str] = None,
        limit: Optional[int] = 100,
    ) -> list[DouyinPost]:
        async with get_monitor_session() as session:
            stmt = select(DouyinPost).where(DouyinPost.platform == platform)
            if sec_user_id:
                stmt = stmt.where(DouyinPost.sec_user_id == sec_user_id)
            stmt = stmt.order_by(DouyinPost.create_time.desc())
            if limit is not None:
                stmt = stmt.limit(limit)
            return list((await session.execute(stmt)).scalars().all())

    async def get_post(self, aweme_id: str, platform: str = "dy") -> Optional[DouyinPost]:
        async with get_monitor_session() as session:
            stmt = select(DouyinPost).where(
                DouyinPost.platform == platform,
                DouyinPost.aweme_id == aweme_id,
            )
            return (await session.execute(stmt)).scalar_one_or_none()

    async def count_posts_since(
        self,
        since: int,
        platform: str = "dy",
        sec_user_id: Optional[str] = None,
    ) -> int:
        async with get_monitor_session() as session:
            stmt = select(func.count(DouyinPost.id)).where(
                DouyinPost.platform == platform,
                DouyinPost.first_seen_at >= since,
            )
            if sec_user_id:
                stmt = stmt.where(DouyinPost.sec_user_id == sec_user_id)
            return int((await session.execute(stmt)).scalar() or 0)

    async def count_posts(
        self,
        platform: str = "dy",
        sec_user_id: Optional[str] = None,
    ) -> int:
        """Return the complete number of collected posts for the selected scope."""
        async with get_monitor_session() as session:
            stmt = select(func.count(DouyinPost.id)).where(DouyinPost.platform == platform)
            if sec_user_id:
                stmt = stmt.where(DouyinPost.sec_user_id == sec_user_id)
            return int((await session.execute(stmt)).scalar() or 0)

    async def get_next_pending_job(
        self,
        platform: str = "dy",
        sec_user_id: Optional[str] = None,
    ) -> Optional[DouyinMonitorJob]:
        async with get_monitor_session() as session:
            stmt = (
                select(DouyinMonitorJob)
                .where(
                    DouyinMonitorJob.platform == platform,
                    DouyinMonitorJob.status == "pending",
                )
            )
            if sec_user_id:
                stmt = stmt.where(DouyinMonitorJob.sec_user_id == sec_user_id)
            stmt = stmt.order_by(DouyinMonitorJob.due_at.asc()).limit(1)
            return (await session.execute(stmt)).scalar_one_or_none()

    async def list_recent_abnormal_jobs(
        self,
        statuses: tuple[str, ...] = ("failed", "missed"),
        limit: int = 10,
        platform: str = "dy",
        sec_user_id: Optional[str] = None,
    ) -> list[dict]:
        async with get_monitor_session() as session:
            stmt = (
                select(DouyinMonitorJob, DouyinPost.title, DouyinPost.canonical_url, DouyinPost.create_time)
                .outerjoin(
                    DouyinPost,
                    (DouyinPost.platform == DouyinMonitorJob.platform)
                    & (DouyinPost.aweme_id == DouyinMonitorJob.aweme_id),
                )
                .where(
                    DouyinMonitorJob.platform == platform,
                    DouyinMonitorJob.status.in_(statuses),
                )
            )
            if sec_user_id:
                stmt = stmt.where(DouyinMonitorJob.sec_user_id == sec_user_id)
            stmt = stmt.order_by(DouyinMonitorJob.due_at.desc()).limit(limit)
            return [
                {
                    "id": job.id,
                    "aweme_id": job.aweme_id,
                    "title": title or job.aweme_id,
                    "canonical_url": canonical_url,
                    "create_time": create_time,
                    "stage": job.stage,
                    "due_at": job.due_at,
                    "status": job.status,
                    "miss_reason": job.miss_reason,
                    "last_error": job.last_error,
                }
                for job, title, canonical_url, create_time in (await session.execute(stmt)).all()
            ]

    async def list_jobs(
        self,
        status: Optional[str] = None,
        platform: str = "dy",
        sec_user_id: Optional[str] = None,
        limit: Optional[int] = 300,
    ) -> list[dict]:
        async with get_monitor_session() as session:
            stmt = (
                select(DouyinMonitorJob, DouyinPost.title, DouyinPost.canonical_url, DouyinPost.create_time)
                .outerjoin(
                    DouyinPost,
                    (DouyinPost.platform == DouyinMonitorJob.platform)
                    & (DouyinPost.aweme_id == DouyinMonitorJob.aweme_id),
                )
                .where(DouyinMonitorJob.platform == platform)
            )
            if status:
                stmt = stmt.where(DouyinMonitorJob.status == status)
            if sec_user_id:
                stmt = stmt.where(DouyinMonitorJob.sec_user_id == sec_user_id)
            stmt = stmt.order_by(DouyinMonitorJob.due_at.asc())
            if limit is not None:
                stmt = stmt.limit(limit)
            return [
                {
                    "id": job.id,
                    "aweme_id": job.aweme_id,
                    "title": title or job.aweme_id,
                    "canonical_url": canonical_url,
                    "create_time": create_time,
                    "stage": job.stage,
                    "due_at": job.due_at,
                    "status": job.status,
                    "attempts": job.attempts,
                    "last_error": job.last_error,
                    "miss_reason": job.miss_reason,
                    "created_at": job.created_at,
                    "started_at": job.started_at,
                    "finished_at": job.finished_at,
                }
                for job, title, canonical_url, create_time in (await session.execute(stmt)).all()
            ]

    async def retry_failed_job(self, job_id: int) -> Optional[DouyinMonitorJob]:
        now = _now_seconds()
        async with get_monitor_session() as session:
            job = await session.get(DouyinMonitorJob, job_id)
            if job is None:
                return None
            if job.status != "failed":
                raise ValueError(f"Only failed jobs can be retried; job {job_id} is {job.status}.")
            job.status = "pending"
            job.due_at = now
            job.started_at = None
            job.finished_at = None
            job.miss_reason = None
            job.attempts = 0
            await session.flush()
            return job

    async def retry_failed_jobs(self, job_ids: Optional[list[int]] = None) -> int:
        now = _now_seconds()
        async with get_monitor_session() as session:
            stmt = select(DouyinMonitorJob).where(DouyinMonitorJob.status == "failed")
            if job_ids:
                stmt = stmt.where(DouyinMonitorJob.id.in_(job_ids))
            jobs = list((await session.execute(stmt)).scalars().all())
            for job in jobs:
                job.status = "pending"
                job.due_at = now
                job.started_at = None
                job.finished_at = None
                job.miss_reason = None
                job.attempts = 0
            await session.flush()
            return len(jobs)

    async def create_alert(
        self,
        alert_type: str,
        severity: str,
        title: str,
        message: str,
        dedupe_key: str,
        platform: str = "dy",
        sec_user_id: str = "",
    ) -> Optional[MonitorAlert]:
        now = _now_seconds()
        effective_key = f"{sec_user_id}:{dedupe_key}" if sec_user_id else dedupe_key
        async with get_monitor_session() as session:
            existing = await session.execute(
                select(MonitorAlert).where(MonitorAlert.dedupe_key == effective_key)
            )
            if existing.scalar_one_or_none() is not None:
                return None
            alert = MonitorAlert(
                platform=platform,
                sec_user_id=sec_user_id,
                alert_type=alert_type,
                severity=severity,
                title=title,
                message=message,
                status="unread",
                dedupe_key=effective_key,
                created_at=now,
            )
            session.add(alert)
            await session.flush()
            return alert

    async def list_alerts(
        self,
        status: Optional[str] = None,
        limit: int = 200,
        platform: str = "dy",
        sec_user_id: Optional[str] = None,
    ) -> list[MonitorAlert]:
        async with get_monitor_session() as session:
            stmt = select(MonitorAlert).where(MonitorAlert.platform == platform)
            if status:
                stmt = stmt.where(MonitorAlert.status == status)
            if sec_user_id:
                stmt = stmt.where(MonitorAlert.sec_user_id == sec_user_id)
            stmt = stmt.order_by(MonitorAlert.created_at.desc()).limit(limit)
            return list((await session.execute(stmt)).scalars().all())

    async def count_unread_alerts(
        self,
        platform: str = "dy",
        sec_user_id: Optional[str] = None,
    ) -> int:
        async with get_monitor_session() as session:
            stmt = select(func.count(MonitorAlert.id)).where(
                MonitorAlert.platform == platform,
                MonitorAlert.status == "unread",
            )
            if sec_user_id:
                stmt = stmt.where(MonitorAlert.sec_user_id == sec_user_id)
            return int((await session.execute(stmt)).scalar() or 0)

    async def mark_alert_read(self, alert_id: int) -> Optional[MonitorAlert]:
        now = _now_seconds()
        async with get_monitor_session() as session:
            alert = await session.get(MonitorAlert, alert_id)
            if alert is None:
                return None
            alert.status = "read"
            alert.read_at = now
            await session.flush()
            return alert

    async def mark_all_alerts_read(
        self,
        platform: str = "dy",
        sec_user_id: Optional[str] = None,
    ) -> int:
        now = _now_seconds()
        async with get_monitor_session() as session:
            alerts = list((await session.execute(
                select(MonitorAlert).where(
                    MonitorAlert.platform == platform,
                    MonitorAlert.status == "unread",
                )
            )).scalars().all())
            if sec_user_id:
                alerts = [alert for alert in alerts if alert.sec_user_id == sec_user_id]
            for alert in alerts:
                alert.status = "read"
                alert.read_at = now
            await session.flush()
            return len(alerts)

    async def set_alerts_status(
        self,
        alert_ids: Sequence[int],
        status: str,
    ) -> int:
        if status not in ALERT_STATUSES:
            raise ValueError(f"Unsupported alert status: {status}")
        if not alert_ids:
            return 0

        now = _now_seconds()
        async with get_monitor_session() as session:
            alerts = list((await session.execute(
                select(MonitorAlert).where(MonitorAlert.id.in_(alert_ids))
            )).scalars().all())
            for alert in alerts:
                alert.status = status
                if status == "unread":
                    alert.read_at = None
                    alert.resolved_at = None
                elif status == "read":
                    alert.read_at = now
                    alert.resolved_at = None
                else:
                    alert.read_at = alert.read_at or now
                    alert.resolved_at = now
            await session.flush()
            return len(alerts)

    async def get_last_snapshot(
        self,
        platform: str = "dy",
        sec_user_id: Optional[str] = None,
    ) -> Optional[DouyinPostSnapshot]:
        async with get_monitor_session() as session:
            stmt = (
                select(DouyinPostSnapshot)
                .where(DouyinPostSnapshot.platform == platform)
            )
            if sec_user_id:
                stmt = stmt.join(
                    DouyinPost,
                    (DouyinPost.platform == DouyinPostSnapshot.platform)
                    & (DouyinPost.aweme_id == DouyinPostSnapshot.aweme_id),
                ).where(DouyinPost.sec_user_id == sec_user_id)
            stmt = stmt.order_by(DouyinPostSnapshot.captured_at.desc()).limit(1)
            return (await session.execute(stmt)).scalar_one_or_none()

    async def get_job_counts(
        self,
        platform: str = "dy",
        sec_user_id: Optional[str] = None,
    ) -> dict[str, int]:
        async with get_monitor_session() as session:
            stmt = (
                select(DouyinMonitorJob.status, func.count(DouyinMonitorJob.id))
                .where(DouyinMonitorJob.platform == platform)
                .group_by(DouyinMonitorJob.status)
            )
            if sec_user_id:
                stmt = stmt.where(DouyinMonitorJob.sec_user_id == sec_user_id)
            return {status: int(count) for status, count in (await session.execute(stmt)).all()}

    async def upsert_post(
        self,
        aweme_id: str,
        sec_user_id: str,
        title: str,
        desc: str,
        create_time: int,
        canonical_url: str,
        cover_url: str = "",
        platform: str = "dy",
        status: str = "active",
        source: str = "creator_monitor",
    ) -> tuple[DouyinPost, bool]:
        now = _now_seconds()
        async with get_monitor_session() as session:
            stmt = select(DouyinPost).where(
                DouyinPost.platform == platform,
                DouyinPost.aweme_id == aweme_id,
            )
            post = (await session.execute(stmt)).scalar_one_or_none()
            created = post is None
            if created:
                post = DouyinPost(
                    platform=platform,
                    aweme_id=aweme_id,
                    sec_user_id=sec_user_id,
                    title=title,
                    desc=desc,
                    create_time=int(create_time),
                    first_seen_at=now,
                    canonical_url=canonical_url,
                    cover_url=cover_url,
                    status=status,
                    source=source,
                    add_ts=now,
                    last_modify_ts=now,
                )
                session.add(post)
            else:
                post.sec_user_id = sec_user_id
                post.title = title
                post.desc = desc
                post.create_time = int(create_time)
                post.canonical_url = canonical_url
                if cover_url:
                    post.cover_url = cover_url
                post.status = status
                post.source = source
                post.last_modify_ts = now
            await session.flush()
            return post, created

    async def update_post_cover_url(self, aweme_id: str, cover_url: str, platform: str = "dy") -> Optional[DouyinPost]:
        """Persist a newly observed cover URL without overwriting it with an empty value."""
        if not cover_url:
            return None
        async with get_monitor_session() as session:
            stmt = select(DouyinPost).where(
                DouyinPost.platform == platform,
                DouyinPost.aweme_id == aweme_id,
            )
            post = (await session.execute(stmt)).scalar_one_or_none()
            if post is None:
                return None
            post.cover_url = cover_url
            post.last_modify_ts = _now_seconds()
            await session.flush()
            return post

    async def create_snapshot_jobs(
        self,
        post: DouyinPost,
        stages: Optional[Sequence[tuple[str, int]]] = None,
    ) -> list[DouyinMonitorJob]:
        created_jobs: list[DouyinMonitorJob] = []
        now = _now_seconds()
        stage_defs = stages or SNAPSHOT_STAGES
        async with get_monitor_session() as session:
            for stage, offset_seconds in stage_defs:
                dedupe_key = f"snapshot:{post.platform}:{post.aweme_id}:{stage}"
                existing = await session.execute(
                    select(DouyinMonitorJob).where(DouyinMonitorJob.dedupe_key == dedupe_key)
                )
                if existing.scalar_one_or_none() is not None:
                    continue
                job = DouyinMonitorJob(
                    job_type="snapshot",
                    platform=post.platform,
                    sec_user_id=post.sec_user_id,
                    dedupe_key=dedupe_key,
                    aweme_id=post.aweme_id,
                    stage=stage,
                    due_at=int(post.create_time) + offset_seconds,
                    status="pending",
                    attempts=0,
                    created_at=now,
                )
                session.add(job)
                created_jobs.append(job)
            await session.flush()
            return created_jobs

    async def mark_overdue_jobs_missed(self, now: Optional[int] = None) -> int:
        current_time = now or _now_seconds()
        missed_count = 0
        async with get_monitor_session() as session:
            stmt = select(DouyinMonitorJob).where(
                DouyinMonitorJob.job_type == "snapshot",
                DouyinMonitorJob.status == "pending",
                DouyinMonitorJob.due_at <= current_time,
            )
            jobs = list((await session.execute(stmt)).scalars().all())
            for job in jobs:
                allowed_window = SNAPSHOT_ALLOWED_WINDOWS.get(job.stage)
                if allowed_window is None or current_time <= job.due_at + allowed_window:
                    continue
                job.status = "missed"
                job.miss_reason = (
                    f"Stage {job.stage} missed its allowed execution window"
                )
                job.finished_at = current_time
                missed_count += 1
            await session.flush()
            return missed_count

    async def list_due_jobs(
        self,
        now: Optional[int] = None,
        limit: int = 50,
    ) -> list[DouyinMonitorJob]:
        current_time = now or _now_seconds()
        await self.mark_overdue_jobs_missed(current_time)
        async with get_monitor_session() as session:
            stmt = (
                select(DouyinMonitorJob)
                .where(
                    DouyinMonitorJob.job_type == "snapshot",
                    DouyinMonitorJob.status == "pending",
                    DouyinMonitorJob.due_at <= current_time,
                )
                .order_by(DouyinMonitorJob.due_at.asc())
                .limit(limit)
            )
            return list((await session.execute(stmt)).scalars().all())

    async def get_job(self, job_id: int) -> Optional[DouyinMonitorJob]:
        async with get_monitor_session() as session:
            return await session.get(DouyinMonitorJob, job_id)

    async def mark_job_running(self, job_id: int) -> Optional[DouyinMonitorJob]:
        now = _now_seconds()
        async with get_monitor_session() as session:
            job = await session.get(DouyinMonitorJob, job_id)
            if job is None or job.status not in ("pending",):
                return None
            job.status = "running"
            job.started_at = now
            job.attempts += 1
            await session.flush()
            return job

    async def mark_job_done(self, job_id: int) -> Optional[DouyinMonitorJob]:
        now = _now_seconds()
        async with get_monitor_session() as session:
            job = await session.get(DouyinMonitorJob, job_id)
            if job is None:
                return None
            job.status = "done"
            job.finished_at = now
            job.last_error = None
            await session.flush()
            return job

    async def mark_job_missed(self, job_id: int, reason: str) -> Optional[DouyinMonitorJob]:
        now = _now_seconds()
        async with get_monitor_session() as session:
            job = await session.get(DouyinMonitorJob, job_id)
            if job is None:
                return None
            job.status = "missed"
            job.miss_reason = reason
            job.finished_at = now
            await session.flush()
            return job

    async def mark_job_retry(
        self,
        job_id: int,
        error: str,
        retry_delay_seconds: int = 600,
        max_attempts: int = 3,
    ) -> Optional[DouyinMonitorJob]:
        now = _now_seconds()
        async with get_monitor_session() as session:
            job = await session.get(DouyinMonitorJob, job_id)
            if job is None:
                return None
            job.last_error = error
            if job.attempts >= max_attempts:
                job.status = "failed"
                job.finished_at = now
            else:
                job.status = "pending"
                job.due_at = now + max(1, retry_delay_seconds)
                job.started_at = None
            await session.flush()
            return job

    async def record_snapshot(
        self,
        job_id: int,
        liked_count: int = 0,
        collected_count: int = 0,
        comment_count: int = 0,
        share_count: int = 0,
        captured_at: Optional[int] = None,
    ) -> DouyinPostSnapshot:
        captured_at = captured_at if captured_at is not None else _now_seconds()
        async with get_monitor_session() as session:
            job = await session.get(DouyinMonitorJob, job_id)
            if job is None:
                raise ValueError(f"Monitor job not found: {job_id}")
            if job.status not in ("pending", "running"):
                raise ValueError(f"Monitor job {job_id} is not executable: {job.status}")

            post_stmt = select(DouyinPost).where(
                DouyinPost.platform == job.platform,
                DouyinPost.aweme_id == job.aweme_id,
            )
            post = (await session.execute(post_stmt)).scalar_one_or_none()
            if post is None:
                raise ValueError(f"Post not found for monitor job {job_id}")

            snapshot = DouyinPostSnapshot(
                platform=job.platform,
                aweme_id=job.aweme_id,
                stage=job.stage,
                due_at=job.due_at,
                captured_at=captured_at,
                actual_age_seconds=max(0, captured_at - int(post.create_time)),
                liked_count=int(liked_count or 0),
                collected_count=int(collected_count or 0),
                comment_count=int(comment_count or 0),
                share_count=int(share_count or 0),
                created_at=captured_at,
            )
            session.add(snapshot)
            job.status = "done"
            job.finished_at = captured_at
            job.last_error = None
            await session.flush()
            return snapshot

    async def record_first_seen_snapshot(
        self,
        aweme_id: str,
        liked_count: int = 0,
        collected_count: int = 0,
        comment_count: int = 0,
        share_count: int = 0,
        platform: str = "dy",
        captured_at: Optional[int] = None,
    ) -> DouyinPostSnapshot:
        """Store the first observed state without treating it as a scheduled stage."""
        observed_at = captured_at if captured_at is not None else _now_seconds()
        async with get_monitor_session() as session:
            post_stmt = select(DouyinPost).where(
                DouyinPost.platform == platform,
                DouyinPost.aweme_id == aweme_id,
            )
            post = (await session.execute(post_stmt)).scalar_one_or_none()
            if post is None:
                raise ValueError(f"Post not found for first-seen snapshot: {aweme_id}")

            snapshot = DouyinPostSnapshot(
                platform=platform,
                aweme_id=aweme_id,
                stage="first_seen",
                due_at=observed_at,
                captured_at=observed_at,
                actual_age_seconds=max(0, observed_at - int(post.create_time)),
                liked_count=int(liked_count or 0),
                collected_count=int(collected_count or 0),
                comment_count=int(comment_count or 0),
                share_count=int(share_count or 0),
                created_at=observed_at,
            )
            session.add(snapshot)
            await session.flush()
            return snapshot

    async def list_snapshots(
        self,
        aweme_id: Optional[str] = None,
        aweme_ids: Optional[Sequence[str]] = None,
        platform: str = "dy",
        sec_user_id: Optional[str] = None,
        limit: Optional[int] = 100,
    ) -> list[DouyinPostSnapshot]:
        async with get_monitor_session() as session:
            stmt = select(DouyinPostSnapshot).where(DouyinPostSnapshot.platform == platform)
            if sec_user_id:
                stmt = stmt.join(
                    DouyinPost,
                    (DouyinPost.platform == DouyinPostSnapshot.platform)
                    & (DouyinPost.aweme_id == DouyinPostSnapshot.aweme_id),
                ).where(DouyinPost.sec_user_id == sec_user_id)
            if aweme_id:
                stmt = stmt.where(DouyinPostSnapshot.aweme_id == aweme_id)
            if aweme_ids is not None:
                if not aweme_ids:
                    return []
                stmt = stmt.where(DouyinPostSnapshot.aweme_id.in_(aweme_ids))
            stmt = stmt.order_by(DouyinPostSnapshot.captured_at.desc())
            if limit is not None:
                stmt = stmt.limit(limit)
            return list((await session.execute(stmt)).scalars().all())


monitor_repository = MonitorRepository()
