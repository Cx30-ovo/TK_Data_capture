import os
import sqlite3
import time

import pytest

import config

from database import db_session
from database.monitor_repository import monitor_repository
from api.services.monitor_service import (
    DouyinMonitorFetcher,
    DouyinPostUnavailableError,
    MonitorService,
    classify_job_error,
)
from api.services.report_service import ReportService
from api.services.analytics_service import AnalyticsService
from api.services.maintenance_service import MaintenanceService
from media_platform.douyin.core import DouYinCrawler


BASE_TIME = 1_800_000_000


class FakeFetcher:
    def __init__(self, posts, metrics=None):
        self.posts = posts
        self.metrics = metrics or {}
        self.last_known_ids = set()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def fetch_latest_posts(
        self, sec_user_id, known_ids, max_pages=3, published_since=None, stop_on_known=False
    ):
        self.last_known_ids = set(known_ids)
        return [post for post in self.posts if post["aweme_id"] not in known_ids]

    async def fetch_metrics(self, aweme_id):
        return self.metrics.get(aweme_id, {
            "liked_count": 1,
            "collected_count": 2,
            "comment_count": 3,
            "share_count": 4,
        })


class FakePage:
    def __init__(self, name=""):
        self.name = name

    async def evaluate(self, script):
        if "window.name = 'MediaCrawler'" in script:
            self.name = "MediaCrawler"
        return self.name


class FakeBrowserContext:
    def __init__(self, pages):
        self.pages = pages
        self.created = []

    async def new_page(self):
        page = FakePage()
        self.pages.append(page)
        self.created.append(page)
        return page


@pytest.mark.asyncio
async def test_monitor_fetcher_raises_unavailable_error_when_detail_is_missing():
    class MissingDetailClient:
        async def get_video_by_id(self, aweme_id):
            return None

    fetcher = DouyinMonitorFetcher()
    fetcher._client = MissingDetailClient()

    with pytest.raises(DouyinPostUnavailableError, match="missing_detail_post"):
        await fetcher._fetch_metrics_once("missing_detail_post")


@pytest.fixture
def isolated_monitor_db(tmp_path, monkeypatch):
    db_path = tmp_path / "monitor.db"
    monkeypatch.setitem(db_session.sqlite_db_config, "db_path", str(db_path))
    db_session._engines.pop("sqlite", None)
    yield
    db_session._engines.pop("sqlite", None)


@pytest.mark.asyncio
async def test_monitor_schema_migration_adds_cover_url(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy-monitor.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE douyin_posts ("
            "id INTEGER PRIMARY KEY, platform VARCHAR(32), aweme_id VARCHAR(128)"
            ")"
        )
    monkeypatch.setitem(db_session.sqlite_db_config, "db_path", str(db_path))
    db_session._engines.pop("sqlite", None)

    await db_session.create_tables("sqlite")

    with sqlite3.connect(db_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(douyin_posts)")}
    assert "cover_url" in columns
    db_session._engines.pop("sqlite", None)


@pytest.mark.asyncio
async def test_monitor_repository_flow(isolated_monitor_db):
    await db_session.create_tables("sqlite")

    account = await monitor_repository.upsert_monitored_account(
        sec_user_id="sec_user_1",
        profile_url="https://www.douyin.com/user/sec_user_1",
    )
    assert account.id is not None

    post, created = await monitor_repository.upsert_post(
        aweme_id="aweme_1",
        sec_user_id="sec_user_1",
        title="title",
        desc="body",
        create_time=BASE_TIME,
        canonical_url="https://www.douyin.com/video/aweme_1",
        cover_url="https://example.com/cover-1.jpg",
    )
    assert created is True
    assert post.id is not None
    assert post.cover_url == "https://example.com/cover-1.jpg"

    same_post, created_again = await monitor_repository.upsert_post(
        aweme_id="aweme_1",
        sec_user_id="sec_user_1",
        title="title updated",
        desc="body updated",
        create_time=BASE_TIME,
        canonical_url="https://www.douyin.com/video/aweme_1",
    )
    assert created_again is False
    assert same_post.id == post.id
    assert same_post.title == "title updated"
    assert same_post.cover_url == "https://example.com/cover-1.jpg"

    jobs = await monitor_repository.create_snapshot_jobs(post)
    assert [job.stage for job in jobs] == ["1h", "6h", "24h", "72h", "7d"]

    duplicate_jobs = await monitor_repository.create_snapshot_jobs(post)
    assert duplicate_jobs == []

    due_jobs = await monitor_repository.list_due_jobs(now=BASE_TIME + 3600)
    assert len(due_jobs) == 1
    assert due_jobs[0].stage == "1h"

    snapshot = await monitor_repository.record_snapshot(
        job_id=due_jobs[0].id,
        liked_count=10,
        collected_count=2,
        comment_count=3,
        share_count=4,
        captured_at=BASE_TIME + 3710,
    )
    assert snapshot.actual_age_seconds == 3710
    assert snapshot.liked_count == 10

    finished_job = await monitor_repository.get_job(due_jobs[0].id)
    assert finished_job.status == "done"

    historical_post, _ = await monitor_repository.upsert_post(
        aweme_id="aweme_old",
        sec_user_id="sec_user_1",
        title="old",
        desc="old body",
        create_time=BASE_TIME - 100_000,
        canonical_url="https://www.douyin.com/video/aweme_old",
    )
    historical_jobs = await monitor_repository.create_snapshot_jobs(historical_post)
    await monitor_repository.list_due_jobs(now=BASE_TIME)
    old_job = await monitor_repository.get_job(historical_jobs[0].id)
    assert old_job.status == "missed"
    assert old_job.miss_reason

    with pytest.raises(ValueError):
        await monitor_repository.record_snapshot(
            job_id=historical_jobs[0].id,
            liked_count=999,
            captured_at=BASE_TIME,
        )


@pytest.mark.asyncio
async def test_monitor_service_discovery_and_snapshot_flow(isolated_monitor_db):
    await db_session.create_tables("sqlite")
    account = await monitor_repository.upsert_monitored_account(
        sec_user_id="sec_service_user",
        profile_url="https://www.douyin.com/user/sec_service_user",
    )
    fetcher = FakeFetcher(
        posts=[
            {
                "platform": "dy",
                "aweme_id": "aweme_service_1",
                "sec_user_id": "sec_service_user",
                "title": "post one",
                "desc": "post one",
                "create_time": BASE_TIME,
                "canonical_url": "https://www.douyin.com/video/aweme_service_1",
                "cover_url": "https://example.com/service-cover.jpg",
                "liked_count": 11,
                "collected_count": 3,
                "comment_count": 2,
                "share_count": 1,
            },
            {
                "platform": "dy",
                "aweme_id": "aweme_service_2",
                "sec_user_id": "sec_service_user",
                "title": "post two",
                "desc": "post two",
                "create_time": BASE_TIME,
                "canonical_url": "https://www.douyin.com/video/aweme_service_2",
                "liked_count": 22,
                "collected_count": 4,
                "comment_count": 5,
                "share_count": 6,
            },
        ],
        metrics={"aweme_service_1": {"liked_count": 100, "collected_count": 20, "comment_count": 10, "share_count": 5, "cover_url": "https://example.com/refreshed-cover.jpg"}},
    )

    service = MonitorService()
    result = await service.discover_account(sec_user_id=account.sec_user_id, fetcher=fetcher, max_pages=1)
    assert result["created_posts"] == 2
    assert result["created_jobs"] == 10
    stored_post = await monitor_repository.get_post("aweme_service_1")
    assert stored_post.cover_url == "https://example.com/service-cover.jpg"
    first_seen_snapshots = await monitor_repository.list_snapshots(limit=10)
    assert len([item for item in first_seen_snapshots if item.stage == "first_seen"]) == 2

    second_result = await service.discover_account(sec_user_id=account.sec_user_id, fetcher=fetcher, max_pages=1)
    assert second_result["created_posts"] == 0
    assert second_result["created_jobs"] == 0

    snapshot_result = await service.run_due_snapshots(limit=10, fetcher=fetcher, now=BASE_TIME + 3600)
    assert snapshot_result["completed"] == 2
    refreshed_post = await monitor_repository.get_post("aweme_service_1")
    assert refreshed_post.cover_url == "https://example.com/refreshed-cover.jpg"

    post_ids = await monitor_repository.list_post_ids(account.sec_user_id)
    assert post_ids == {"aweme_service_1", "aweme_service_2"}


def test_monitor_fetcher_extracts_video_and_image_post_covers():
    video_post = {
        "aweme_id": "video-cover",
        "video": {"raw_cover": {"url_list": ["", "https://example.com/video-cover.jpg"]}},
    }
    image_post = {
        "aweme_id": "image-cover",
        "images": [{"origin_url": {"url_list": ["https://example.com/image-cover.jpg"]}}],
    }
    alternate_video_post = {
        "aweme_id": "alternate-video-cover",
        "video": {"animated_cover": {"url": "https://example.com/animated-cover.jpg"}},
    }
    alternate_image_post = {
        "aweme_id": "alternate-image-cover",
        "image_post_info": {
            "images": [{"display_image": {"url_list": ["https://example.com/display-image.jpg"]}}]
        },
    }

    assert DouyinMonitorFetcher._normalize_post(video_post, "sec")['cover_url'] == "https://example.com/video-cover.jpg"
    assert DouyinMonitorFetcher._normalize_post(image_post, "sec")['cover_url'] == "https://example.com/image-cover.jpg"
    assert DouyinMonitorFetcher._normalize_post(alternate_video_post, "sec")['cover_url'] == "https://example.com/animated-cover.jpg"
    assert DouyinMonitorFetcher._normalize_post(alternate_image_post, "sec")['cover_url'] == "https://example.com/display-image.jpg"


@pytest.mark.asyncio
async def test_manual_discovery_backfills_missing_cover_from_detail(isolated_monitor_db):
    await db_session.create_tables("sqlite")
    now = int(time.time())
    account = await monitor_repository.upsert_monitored_account(sec_user_id="cover_backfill_user")
    await monitor_repository.upsert_post(
        aweme_id="cover_backfill_post",
        sec_user_id=account.sec_user_id,
        title="cover backfill",
        desc="cover backfill",
        create_time=now - 10 * 86400,
        canonical_url="https://www.douyin.com/video/cover_backfill_post",
    )

    class ExistingAwareFakeFetcher(FakeFetcher):
        async def fetch_latest_posts(
            self, sec_user_id, known_ids, max_pages=3, published_since=None, stop_on_known=False
        ):
            self.last_known_ids = set(known_ids)
            return list(self.posts)

    fetcher = ExistingAwareFakeFetcher(
        posts=[
            {
                "platform": "dy",
                "aweme_id": "cover_backfill_post",
                "sec_user_id": account.sec_user_id,
                "title": "cover backfill",
                "desc": "cover backfill",
                "create_time": now - 10 * 86400,
                "canonical_url": "https://www.douyin.com/video/cover_backfill_post",
            },
            {
                "platform": "dy",
                "aweme_id": "new_recent_post",
                "sec_user_id": account.sec_user_id,
                "title": "must be collected",
                "desc": "must be collected",
                "create_time": now - 3600,
                "canonical_url": "https://www.douyin.com/video/new_recent_post",
                "cover_url": "https://example.com/recent-cover.jpg",
                "liked_count": 10,
                "collected_count": 2,
                "comment_count": 3,
                "share_count": 4,
            },
            {
                "platform": "dy",
                "aweme_id": "uncollected_history_post",
                "sec_user_id": account.sec_user_id,
                "title": "must be skipped",
                "desc": "must be skipped",
                "create_time": now - 8 * 86400,
                "canonical_url": "https://www.douyin.com/video/uncollected_history_post",
                "cover_url": "https://example.com/history-cover.jpg",
            },
        ],
        metrics={"cover_backfill_post": {
            "liked_count": 1,
            "collected_count": 2,
            "comment_count": 3,
            "share_count": 4,
            "cover_url": "https://example.com/detail-cover.jpg",
        }},
    )

    result = await MonitorService().discover_account(
        sec_user_id=account.sec_user_id,
        fetcher=fetcher,
        backfill_covers=True,
        new_post_window_days=7,
    )

    stored_post = await monitor_repository.get_post("cover_backfill_post")
    assert stored_post.cover_url == "https://example.com/detail-cover.jpg"
    assert result["updated_covers"] == 1
    assert result["created_posts"] == 1
    assert result["created_jobs"] == 5
    assert result["skipped_historical"] == 1
    assert await monitor_repository.get_post("new_recent_post") is not None
    assert await monitor_repository.get_post("uncollected_history_post") is None


@pytest.mark.asyncio
async def test_manual_latest_discovery_only_creates_recent_unknown_posts(isolated_monitor_db):
    await db_session.create_tables("sqlite")
    now = int(time.time())
    account = await monitor_repository.upsert_monitored_account(sec_user_id="latest_only_user")
    await monitor_repository.upsert_post(
        aweme_id="known_boundary",
        sec_user_id=account.sec_user_id,
        title="original title",
        desc="original title",
        create_time=now - 86400,
        canonical_url="https://www.douyin.com/video/known_boundary",
    )

    class LatestFakeFetcher(FakeFetcher):
        async def fetch_latest_posts(
            self, sec_user_id, known_ids, max_pages=3, published_since=None, stop_on_known=False
        ):
            self.last_known_ids = set(known_ids)
            return list(self.posts)

    fetcher = LatestFakeFetcher(posts=[
        {
            "platform": "dy", "aweme_id": "recent_new", "sec_user_id": account.sec_user_id,
            "title": "recent", "desc": "recent", "create_time": now - 600,
            "canonical_url": "https://www.douyin.com/video/recent_new",
        },
        {
            "platform": "dy", "aweme_id": "known_boundary", "sec_user_id": account.sec_user_id,
            "title": "must not overwrite", "desc": "must not overwrite", "create_time": now - 86400,
            "canonical_url": "https://www.douyin.com/video/known_boundary",
        },
        {
            "platform": "dy", "aweme_id": "historical_unknown", "sec_user_id": account.sec_user_id,
            "title": "history", "desc": "history", "create_time": now - 8 * 86400,
            "canonical_url": "https://www.douyin.com/video/historical_unknown",
        },
    ])

    result = await MonitorService().discover_account(
        sec_user_id=account.sec_user_id,
        fetcher=fetcher,
        max_pages=10,
        new_post_window_days=7,
        latest_only=True,
    )

    assert result["created_posts"] == 1
    assert result["created_jobs"] == 5
    assert result["skipped_historical"] == 1
    assert (await monitor_repository.get_post("known_boundary")).title == "original title"
    assert await monitor_repository.get_post("recent_new") is not None
    assert await monitor_repository.get_post("historical_unknown") is None


@pytest.mark.asyncio
async def test_douyin_reuses_marked_context_page():
    crawler = DouYinCrawler()
    marked_page = FakePage("MediaCrawler")
    crawler.browser_context = FakeBrowserContext([FakePage("other"), marked_page])

    page = await crawler._get_or_create_context_page()
    assert page is marked_page

    blank_page = FakePage()
    crawler.browser_context = FakeBrowserContext([blank_page])
    page = await crawler._get_or_create_context_page()
    assert page is blank_page
    assert blank_page.name == "MediaCrawler"


class FakeDouyinClient:
    def __init__(self, pages):
        self.pages = pages
        self.calls = 0

    async def get_user_aweme_posts(self, sec_user_id, max_cursor=""):
        page = self.pages[self.calls]
        self.calls += 1
        return page


@pytest.mark.asyncio
async def test_monitor_discovery_refreshes_known_post_and_scans_past_it():
    fetcher = DouyinMonitorFetcher()
    fetcher._client = FakeDouyinClient([
        {
            "aweme_list": [
                {"aweme_id": "known_pinned", "desc": "old pinned", "create_time": BASE_TIME - 1000},
                {"aweme_id": "new_post", "desc": "new post", "create_time": BASE_TIME},
            ],
            "has_more": 0,
            "max_cursor": "",
        }
    ])

    posts = await fetcher.fetch_latest_posts(
        sec_user_id="sec_user_1",
        known_ids={"known_pinned"},
        max_pages=1,
    )

    assert [post["aweme_id"] for post in posts] == ["known_pinned", "new_post"]
    assert [post["is_known"] for post in posts] == [True, False]


@pytest.mark.asyncio
async def test_monitor_discovery_stops_after_first_page_entirely_before_cutoff():
    fetcher = DouyinMonitorFetcher()
    fetcher._client = FakeDouyinClient([
        {
            "aweme_list": [{"aweme_id": "recent", "desc": "recent", "create_time": BASE_TIME}],
            "has_more": 1,
            "max_cursor": "1",
        },
        {
            "aweme_list": [{"aweme_id": "old", "desc": "old", "create_time": BASE_TIME - 8 * 86400}],
            "has_more": 1,
            "max_cursor": "2",
        },
        {
            "aweme_list": [{"aweme_id": "older", "desc": "older", "create_time": BASE_TIME - 9 * 86400}],
            "has_more": 0,
            "max_cursor": "",
        },
    ])

    posts = await fetcher.fetch_latest_posts(
        sec_user_id="sec_user_1",
        known_ids=set(),
        max_pages=10,
        published_since=BASE_TIME - 7 * 86400,
    )

    assert fetcher._client.calls == 2
    assert [post["aweme_id"] for post in posts] == ["recent", "old"]


@pytest.mark.asyncio
async def test_monitor_discovery_stops_after_page_containing_known_post():
    fetcher = DouyinMonitorFetcher()
    fetcher._client = FakeDouyinClient([
        {
            "aweme_list": [{"aweme_id": "new_1", "desc": "new", "create_time": BASE_TIME}],
            "has_more": 1,
            "max_cursor": "1",
        },
        {
            "aweme_list": [
                {"aweme_id": "new_2", "desc": "new", "create_time": BASE_TIME - 10},
                {"aweme_id": "known", "desc": "known", "create_time": BASE_TIME - 20},
            ],
            "has_more": 1,
            "max_cursor": "2",
        },
        {
            "aweme_list": [{"aweme_id": "should_not_scan", "desc": "old", "create_time": BASE_TIME - 30}],
            "has_more": 0,
            "max_cursor": "",
        },
    ])

    posts = await fetcher.fetch_latest_posts(
        sec_user_id="sec_user_1",
        known_ids={"known"},
        max_pages=10,
        stop_on_known=True,
    )

    assert fetcher._client.calls == 2
    assert [post["aweme_id"] for post in posts] == ["new_1", "new_2", "known"]


@pytest.mark.asyncio
async def test_failed_job_can_be_manually_retried(isolated_monitor_db):
    await db_session.create_tables("sqlite")
    await monitor_repository.upsert_monitored_account(sec_user_id="retry_user")
    post, _ = await monitor_repository.upsert_post(
        aweme_id="retry_post",
        sec_user_id="retry_user",
        title="retry",
        desc="retry",
        create_time=BASE_TIME,
        canonical_url="https://www.douyin.com/video/retry_post",
    )
    jobs = await monitor_repository.create_snapshot_jobs(post)
    job = jobs[0]

    await monitor_repository.mark_job_running(job.id)
    failed = await monitor_repository.mark_job_retry(
        job.id,
        error="blocked",
        retry_delay_seconds=600,
        max_attempts=1,
    )
    assert failed.status == "failed"

    retried = await monitor_repository.retry_failed_job(job.id)
    assert retried is not None
    assert retried.status == "pending"
    assert retried.started_at is None
    assert retried.miss_reason is None

    pending_jobs = await monitor_repository.list_jobs(status="pending")
    assert any(item["id"] == job.id for item in pending_jobs)

    with pytest.raises(ValueError):
        await monitor_repository.retry_failed_job(jobs[1].id)


@pytest.mark.asyncio
async def test_deleted_post_terminates_all_unfinished_snapshot_jobs(isolated_monitor_db):
    await db_session.create_tables("sqlite")
    await monitor_repository.upsert_monitored_account(sec_user_id="deleted_user")
    post, _ = await monitor_repository.upsert_post(
        aweme_id="deleted_post",
        sec_user_id="deleted_user",
        title="deleted",
        desc="deleted",
        create_time=BASE_TIME,
        canonical_url="https://www.douyin.com/video/deleted_post",
    )
    jobs = await monitor_repository.create_snapshot_jobs(post)
    await monitor_repository.mark_job_done(jobs[0].id)
    await monitor_repository.mark_job_running(jobs[1].id)
    await monitor_repository.mark_job_retry(
        jobs[1].id,
        error="Failed to get Douyin detail for aweme_id=deleted_post",
        max_attempts=1,
    )
    await monitor_repository.mark_job_running(jobs[2].id)

    skipped = await monitor_repository.mark_post_deleted_and_skip_jobs(
        aweme_id="deleted_post",
        reason="Failed to get Douyin detail for aweme_id=deleted_post",
    )

    assert skipped == 4
    stored_post = await monitor_repository.get_post("deleted_post")
    assert stored_post.status == "deleted"
    stored_jobs = await monitor_repository.list_jobs(limit=None)
    statuses = {item["id"]: item["status"] for item in stored_jobs}
    assert statuses[jobs[0].id] == "done"
    assert all(statuses[job.id] == "skipped" for job in jobs[1:])
    skipped_job = next(item for item in stored_jobs if item["id"] == jobs[1].id)
    assert skipped_job["miss_reason"] == "作品已删除，后续快照已终止。"
    assert classify_job_error(skipped_job) == "post_deleted"


@pytest.mark.asyncio
async def test_due_snapshot_marks_deleted_post_skipped_without_retry(isolated_monitor_db):
    await db_session.create_tables("sqlite")
    await monitor_repository.upsert_monitored_account(
        sec_user_id="deleted_snapshot_user",
        display_name="删除测试账号",
    )
    post, _ = await monitor_repository.upsert_post(
        aweme_id="deleted_snapshot_post",
        sec_user_id="deleted_snapshot_user",
        title="deleted snapshot",
        desc="deleted snapshot",
        create_time=BASE_TIME,
        canonical_url="https://www.douyin.com/video/deleted_snapshot_post",
    )
    await monitor_repository.create_snapshot_jobs(post)

    class DeletedPostFetcher(FakeFetcher):
        async def fetch_metrics(self, aweme_id):
            raise DouyinPostUnavailableError(
                f"Failed to get Douyin detail for aweme_id={aweme_id}"
            )

    result = await MonitorService().run_due_snapshots(
        limit=10,
        fetcher=DeletedPostFetcher(posts=[]),
        now=BASE_TIME + 3600,
    )

    assert result == {
        "status": "ok",
        "completed": 0,
        "retried": 0,
        "failed": 0,
        "skipped": 5,
        "deleted_posts": 1,
    }
    stored_post = await monitor_repository.get_post("deleted_snapshot_post")
    assert stored_post.status == "deleted"
    counts = await monitor_repository.get_job_counts()
    assert counts == {"skipped": 5}
    assert await monitor_repository.list_alerts() == []


@pytest.mark.asyncio
async def test_reconcile_archives_legacy_deleted_post_failures(isolated_monitor_db):
    await db_session.create_tables("sqlite")
    await monitor_repository.upsert_monitored_account(sec_user_id="legacy_deleted_user")
    post, _ = await monitor_repository.upsert_post(
        aweme_id="legacy_deleted_post",
        sec_user_id="legacy_deleted_user",
        title="legacy deleted",
        desc="legacy deleted",
        create_time=BASE_TIME,
        canonical_url="https://www.douyin.com/video/legacy_deleted_post",
    )
    jobs = await monitor_repository.create_snapshot_jobs(post)
    await monitor_repository.mark_job_running(jobs[0].id)
    await monitor_repository.mark_job_retry(
        jobs[0].id,
        error="Failed to get Douyin detail for aweme_id=legacy_deleted_post",
        max_attempts=1,
    )

    reconciled = await monitor_repository.reconcile_deleted_post_jobs()

    assert reconciled == 5
    assert (await monitor_repository.get_post("legacy_deleted_post")).status == "deleted"
    assert await monitor_repository.get_job_counts() == {"skipped": 5}
    assert await monitor_repository.reconcile_deleted_post_jobs() == 0


@pytest.mark.asyncio
async def test_failed_jobs_can_be_batch_retried_and_classified(isolated_monitor_db):
    await db_session.create_tables("sqlite")
    await monitor_repository.upsert_monitored_account(sec_user_id="batch_retry_user")
    post, _ = await monitor_repository.upsert_post(
        aweme_id="batch_retry_post",
        sec_user_id="batch_retry_user",
        title="batch retry",
        desc="batch retry",
        create_time=BASE_TIME,
        canonical_url="https://www.douyin.com/video/batch_retry_post",
    )
    jobs = await monitor_repository.create_snapshot_jobs(post)

    for job in jobs[:2]:
        await monitor_repository.mark_job_running(job.id)
        await monitor_repository.mark_job_retry(
            job.id,
            error="blocked by risk control",
            retry_delay_seconds=600,
            max_attempts=1,
        )

    failed_jobs = await monitor_repository.list_jobs(status="failed")
    assert len(failed_jobs) == 2
    assert classify_job_error(failed_jobs[0]) == "risk_control"
    abnormal_jobs = await monitor_repository.list_jobs(statuses=("failed", "missed"))
    assert {item["id"] for item in abnormal_jobs} == {jobs[0].id, jobs[1].id}

    service_result = await MonitorService().list_jobs(status="abnormal", all_accounts=True)
    assert service_result["count"] == 2
    assert service_result["returned_count"] == 2
    assert service_result["total_count"] == len(jobs)
    assert service_result["status_counts"]["failed"] == 2

    limited_pending = await MonitorService().list_jobs(status="pending", limit=1, all_accounts=True)
    assert limited_pending["count"] == 3
    assert limited_pending["returned_count"] == 1
    assert limited_pending["jobs"][0]["status"] == "pending"

    updated = await monitor_repository.retry_failed_jobs([jobs[0].id])
    assert updated == 1
    first = await monitor_repository.get_job(jobs[0].id)
    second = await monitor_repository.get_job(jobs[1].id)
    assert first.status == "pending"
    assert first.attempts == 0
    assert second.status == "failed"

    updated = await monitor_repository.retry_failed_jobs()
    assert updated == 1
    second = await monitor_repository.get_job(jobs[1].id)
    assert second.status == "pending"
    assert second.attempts == 0


@pytest.mark.asyncio
async def test_alerts_are_deduplicated_and_can_be_marked_read(isolated_monitor_db):
    await db_session.create_tables("sqlite")

    created = await monitor_repository.create_alert(
        alert_type="test",
        severity="warning",
        title="test alert",
        message="test message",
        dedupe_key="test-alert-key",
    )
    duplicate = await monitor_repository.create_alert(
        alert_type="test",
        severity="warning",
        title="test alert",
        message="test message",
        dedupe_key="test-alert-key",
    )

    assert created is not None
    assert duplicate is None
    assert await monitor_repository.count_unread_alerts() == 1

    alerts = await monitor_repository.list_alerts(status="unread")
    assert len(alerts) == 1

    await monitor_repository.mark_alert_read(created.id)
    assert await monitor_repository.count_unread_alerts() == 0

    updated = await monitor_repository.set_alerts_status([created.id], "ignored")
    assert updated == 1
    ignored_alerts = await monitor_repository.list_alerts(status="ignored")
    assert len(ignored_alerts) == 1
    assert ignored_alerts[0].resolved_at is not None

    await monitor_repository.set_alerts_status([created.id], "resolved")
    resolved_alerts = await monitor_repository.list_alerts(status="resolved")
    assert len(resolved_alerts) == 1


@pytest.mark.asyncio
async def test_multiple_accounts_keep_posts_jobs_and_alerts_isolated(isolated_monitor_db):
    await db_session.create_tables("sqlite")

    account_a = await monitor_repository.upsert_monitored_account(
        sec_user_id="account_a",
        display_name="账号 A",
        profile_url="https://www.douyin.com/user/account_a",
    )
    account_b = await monitor_repository.upsert_monitored_account(
        sec_user_id="account_b",
        display_name="账号 B",
        profile_url="https://www.douyin.com/user/account_b",
    )
    accounts = await monitor_repository.list_monitored_accounts()
    assert [account.sec_user_id for account in accounts] == ["account_a", "account_b"]

    updated = await monitor_repository.update_monitored_account(
        account_b.id,
        display_name="账号 B2",
        discover_interval_minutes=60,
        enabled=False,
    )
    assert updated is not None
    assert updated.display_name == "账号 B2"
    assert updated.discover_interval_minutes == 60
    assert updated.enabled is False

    post_a, _ = await monitor_repository.upsert_post(
        aweme_id="multi_post_a",
        sec_user_id=account_a.sec_user_id,
        title="A",
        desc="A",
        create_time=BASE_TIME,
        canonical_url="https://www.douyin.com/video/multi_post_a",
    )
    post_b, _ = await monitor_repository.upsert_post(
        aweme_id="multi_post_b",
        sec_user_id=account_b.sec_user_id,
        title="B",
        desc="B",
        create_time=BASE_TIME,
        canonical_url="https://www.douyin.com/video/multi_post_b",
    )
    jobs_a = await monitor_repository.create_snapshot_jobs(post_a)
    jobs_b = await monitor_repository.create_snapshot_jobs(post_b)
    assert all(job.sec_user_id == account_a.sec_user_id for job in jobs_a)
    assert all(job.sec_user_id == account_b.sec_user_id for job in jobs_b)

    jobs_for_a = await monitor_repository.list_jobs(sec_user_id=account_a.sec_user_id)
    jobs_for_b = await monitor_repository.list_jobs(sec_user_id=account_b.sec_user_id)
    assert len(jobs_for_a) == 5
    assert len(jobs_for_b) == 5
    assert {job["aweme_id"] for job in jobs_for_a} == {"multi_post_a"}
    assert {job["aweme_id"] for job in jobs_for_b} == {"multi_post_b"}

    alert_a = await monitor_repository.create_alert(
        alert_type="test",
        severity="warning",
        title="same alert",
        message="A",
        dedupe_key="shared-key",
        sec_user_id=account_a.sec_user_id,
    )
    alert_b = await monitor_repository.create_alert(
        alert_type="test",
        severity="warning",
        title="same alert",
        message="B",
        dedupe_key="shared-key",
        sec_user_id=account_b.sec_user_id,
    )
    assert alert_a is not None
    assert alert_b is not None
    alerts_a = await monitor_repository.list_alerts(sec_user_id=account_a.sec_user_id)
    alerts_b = await monitor_repository.list_alerts(sec_user_id=account_b.sec_user_id)
    assert [alert.message for alert in alerts_a] == ["A"]
    assert [alert.message for alert in alerts_b] == ["B"]

    assert await monitor_repository.delete_monitored_account(account_b.id) is True
    assert await monitor_repository.get_monitored_account_by_id(account_b.id) is None
    assert await monitor_repository.get_post(post_b.aweme_id) is not None


@pytest.mark.asyncio
async def test_monitor_exports_and_daily_report(isolated_monitor_db, tmp_path):
    await db_session.create_tables("sqlite")
    await monitor_repository.upsert_monitored_account(sec_user_id="export_user")
    post, _ = await monitor_repository.upsert_post(
        aweme_id="export_post",
        sec_user_id="export_user",
        title="export title",
        desc="export body",
        create_time=BASE_TIME,
        canonical_url="https://www.douyin.com/video/export_post",
    )
    await monitor_repository.record_first_seen_snapshot(
        aweme_id=post.aweme_id,
        liked_count=1,
        collected_count=2,
        comment_count=3,
        share_count=4,
        captured_at=BASE_TIME + 60,
    )

    service = ReportService(output_root=tmp_path)
    csv_path = await service.export_posts(file_format="csv")
    xlsx_path = await service.export_posts(file_format="xlsx")
    snapshot_path = await service.export_post_snapshots(post.aweme_id, file_format="csv")
    report = await service.generate_report(period="daily")

    assert csv_path.exists()
    assert xlsx_path.exists()
    assert snapshot_path.exists()
    multi_path = await service.export_snapshots([post.aweme_id], file_format="xlsx")
    assert multi_path.exists()
    assert "抖音监控日报" in report["content"]
    assert len(service.list_reports()) == 1
    assert service.delete_report(report["filename"]) is True
    assert service.delete_report(report["filename"]) is False
    assert service.list_reports() == []


@pytest.mark.asyncio
async def test_analytics_stage_delta_rates_and_leaderboard(isolated_monitor_db):
    await db_session.create_tables("sqlite")
    await monitor_repository.upsert_monitored_account(sec_user_id="analytics_user")
    post, _ = await monitor_repository.upsert_post(
        aweme_id="analytics_post",
        sec_user_id="analytics_user",
        title="analytics title",
        desc="analytics body",
        create_time=BASE_TIME,
        canonical_url="https://www.douyin.com/video/analytics_post",
    )
    await monitor_repository.record_first_seen_snapshot(
        aweme_id=post.aweme_id,
        liked_count=10,
        collected_count=1,
        comment_count=2,
        share_count=0,
        captured_at=BASE_TIME + 60,
    )
    jobs = await monitor_repository.create_snapshot_jobs(post)
    first_hour_job = next(job for job in jobs if job.stage == "1h")
    await monitor_repository.record_snapshot(
        job_id=first_hour_job.id,
        liked_count=110,
        collected_count=11,
        comment_count=12,
        share_count=8,
        captured_at=BASE_TIME + 3660,
    )

    data = await AnalyticsService().get_data()
    stage_delta = next(item for item in data["stage_deltas"] if item["stage"] == "1h")
    assert stage_delta["liked_count"] == 100
    assert stage_delta["collected_count"] == 10
    assert data["leaderboard"]["likes"][0]["aweme_id"] == post.aweme_id
    assert data["heatmap"]
    assert any(item["aweme_id"] == post.aweme_id for item in data["engagement_rates"])


@pytest.mark.asyncio
async def test_maintenance_backup_and_log_cleanup(tmp_path, monkeypatch):
    db_path = tmp_path / "source.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("create table sample (id integer primary key, value text)")
        connection.execute("insert into sample (value) values ('ok')")
        connection.commit()

    monkeypatch.setattr(config, "ENABLE_AUTO_BACKUP", True)
    monkeypatch.setattr(config, "BACKUP_INTERVAL_HOURS", 1)
    monkeypatch.setattr(config, "BACKUP_RETENTION_DAYS", 14)
    monkeypatch.setattr(config, "LOG_RETENTION_DAYS", 1)

    service = MaintenanceService()
    service.output_root = tmp_path / "output"
    service.backup_dir = service.output_root / "backups"
    service.db_path = db_path

    first = await service.run_once()
    assert first["backup"]
    backup_path = service.backup_dir / f"sqlite_tables_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    assert list(service.backup_dir.glob("sqlite_tables_*.db"))

    old_log = service.output_root / "crawler.log.1"
    old_log.write_text("old", encoding="utf-8")
    old_time = time.time() - 3 * 24 * 3600
    os.utime(old_log, (old_time, old_time))

    second = await service.run_once()
    assert second["removed_logs"] == 1
    assert not old_log.exists()
