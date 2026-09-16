import pytest

from database import db_session
from database.monitor_repository import monitor_repository
from api.services.monitor_service import DouyinMonitorFetcher, MonitorService
from api.services.report_service import ReportService
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

    async def fetch_latest_posts(self, sec_user_id, known_ids, max_pages=3):
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


@pytest.fixture
def isolated_monitor_db(tmp_path, monkeypatch):
    db_path = tmp_path / "monitor.db"
    monkeypatch.setitem(db_session.sqlite_db_config, "db_path", str(db_path))
    db_session._engines.pop("sqlite", None)
    yield
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
    )
    assert created is True
    assert post.id is not None

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
        metrics={"aweme_service_1": {"liked_count": 100, "collected_count": 20, "comment_count": 10, "share_count": 5}},
    )

    service = MonitorService()
    result = await service.discover_account(sec_user_id=account.sec_user_id, fetcher=fetcher, max_pages=1)
    assert result["created_posts"] == 2
    assert result["created_jobs"] == 10
    first_seen_snapshots = await monitor_repository.list_snapshots(limit=10)
    assert len([item for item in first_seen_snapshots if item.stage == "first_seen"]) == 2

    second_result = await service.discover_account(sec_user_id=account.sec_user_id, fetcher=fetcher, max_pages=1)
    assert second_result["created_posts"] == 0
    assert second_result["created_jobs"] == 0

    snapshot_result = await service.run_due_snapshots(limit=10, fetcher=fetcher, now=BASE_TIME + 3600)
    assert snapshot_result["completed"] == 2

    post_ids = await monitor_repository.list_post_ids(account.sec_user_id)
    assert post_ids == {"aweme_service_1", "aweme_service_2"}


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
async def test_monitor_discovery_scans_past_known_pinned_post():
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

    assert [post["aweme_id"] for post in posts] == ["new_post"]


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
    assert "抖音监控日报" in report["content"]
    assert len(service.list_reports()) == 1
    assert service.delete_report(report["filename"]) is True
    assert service.list_reports() == []
