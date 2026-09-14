# -*- coding: utf-8 -*-
"""Persistence helpers for the single-account Douyin monitor module."""

import time
from typing import Optional, Sequence

from sqlalchemy import func, select

from .db_session import get_monitor_session
from .models import (
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


def _now_seconds() -> int:
    return int(time.time())


class MonitorRepository:
    """CRUD and state transitions for monitor accounts, posts, jobs and snapshots."""

    async def upsert_monitored_account(
        self,
        sec_user_id: str,
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
                    profile_url=profile_url,
                    enabled=enabled,
                    discover_interval_minutes=discover_interval_minutes,
                    created_at=now,
                    updated_at=now,
                )
                session.add(account)
            else:
                account.profile_url = profile_url or account.profile_url
                account.enabled = enabled
                account.discover_interval_minutes = discover_interval_minutes
                account.updated_at = now
            await session.flush()
            return account

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

    async def get_job_counts(self, platform: str = "dy") -> dict[str, int]:
        async with get_monitor_session() as session:
            stmt = (
                select(DouyinMonitorJob.status, func.count(DouyinMonitorJob.id))
                .where(DouyinMonitorJob.platform == platform)
                .group_by(DouyinMonitorJob.status)
            )
            return {status: int(count) for status, count in (await session.execute(stmt)).all()}

    async def upsert_post(
        self,
        aweme_id: str,
        sec_user_id: str,
        title: str,
        desc: str,
        create_time: int,
        canonical_url: str,
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
                post.status = status
                post.source = source
                post.last_modify_ts = now
            await session.flush()
            return post, created

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
        platform: str = "dy",
        limit: int = 100,
    ) -> list[DouyinPostSnapshot]:
        async with get_monitor_session() as session:
            stmt = select(DouyinPostSnapshot).where(DouyinPostSnapshot.platform == platform)
            if aweme_id:
                stmt = stmt.where(DouyinPostSnapshot.aweme_id == aweme_id)
            stmt = stmt.order_by(DouyinPostSnapshot.captured_at.desc()).limit(limit)
            return list((await session.execute(stmt)).scalars().all())


monitor_repository = MonitorRepository()
