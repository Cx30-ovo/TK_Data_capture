"""Account controls use temporary SQLite and simulated fetchers, never real Chrome."""

import json
import sqlite3
import time
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from pydantic import ValidationError

from api.routers.monitor import router
from api.schemas.monitor import MonitorAccountConfigRequest
from api.services.monitor_service import MonitorService
from database import db_session
from database.monitor_repository import monitor_repository as repo


@pytest_asyncio.fixture
async def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setitem(db_session.sqlite_db_config, "db_path", str(tmp_path / "monitor.db"))
    monkeypatch.setattr(db_session, "_engines", {})
    await db_session.create_tables("sqlite")
    yield
    for engine in db_session._engines.values():
        await engine.dispose()


@pytest_asyncio.fixture
async def client(isolated_db):
    app = FastAPI()
    app.include_router(router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.parametrize("value", [
    "", "123", "https://www.douyin.com/jingxuan/search/name",
    "https://www.douyin.com/video/123456789", "https://evil.example/user/MS4wAccount",
    "https://www.douyin.com.evil.example/user/MS4wAccount", "not an account",
    "https://www.douyin.com/user/MS4wAccount/extra",
])
def test_invalid_account_urls_are_rejected(value):
    with pytest.raises(ValidationError):
        MonitorAccountConfigRequest(sec_user_id=value)


def test_profile_normalization_and_mismatch():
    parsed = MonitorAccountConfigRequest(sec_user_id=" https://www.douyin.com/user/MS4wAccount?from_tab=main ")
    assert parsed.sec_user_id == "MS4wAccount"
    assert parsed.profile_url == "https://www.douyin.com/user/MS4wAccount"
    with pytest.raises(ValidationError):
        MonitorAccountConfigRequest(sec_user_id="MS4wAccount", profile_url="https://www.douyin.com/user/anotherAccount")


@pytest.mark.asyncio
async def test_duplicate_creation_and_identity_replacement_return_conflicts(client):
    created = await client.post("/monitor/accounts", json={"sec_user_id": "MS4wAccount", "display_name": "原账号"})
    assert created.status_code == 200
    identity = created.json()["id"]
    duplicate = await client.post("/monitor/accounts", json={"sec_user_id": "MS4wAccount", "display_name": "不应覆盖"})
    assert duplicate.status_code == 409
    for payload in ({"sec_user_id": "anotherAccount"}, {"profile_url": "https://www.douyin.com/user/anotherAccount"}):
        changed = await client.put(f"/monitor/accounts/{identity}", json=payload)
        assert changed.status_code == 409
    account = await repo.get_monitored_account_by_id(identity)
    assert account.display_name == "原账号" and account.sec_user_id == "MS4wAccount"
    assert (await client.put(f"/monitor/accounts/{identity}", json={"display_name": "新名称"})).status_code == 200


@pytest.mark.asyncio
async def test_batch_intervals_are_atomic_and_preserve_modes(client):
    first = await repo.upsert_monitored_account("accountFirst", snapshots_paused=True)
    second = await repo.upsert_monitored_account("accountSecond", enabled=False)
    bad = await client.put("/monitor/accounts/batch/interval", json={"account_ids": [first.id, 999], "discover_interval_minutes": 60})
    assert bad.status_code == 409
    assert (await repo.get_monitored_account_by_id(first.id)).discover_interval_minutes == 30
    good = await client.put("/monitor/accounts/batch/interval", json={"account_ids": [first.id, second.id, first.id], "discover_interval_minutes": 60})
    assert good.status_code == 200 and good.json()["updated"] == 2
    assert (await repo.get_monitored_account_by_id(first.id)).snapshots_paused
    assert not (await repo.get_monitored_account_by_id(second.id)).enabled
    invalid = await client.put("/monitor/accounts/batch/interval", json={"account_ids": [], "discover_interval_minutes": 0})
    assert invalid.status_code == 422


async def seed_job(identity, *, age=3600, enabled=True, paused=False):
    account = await repo.upsert_monitored_account(identity, enabled=enabled, snapshots_paused=paused)
    post, _ = await repo.upsert_post(identity + "Post", identity, "测试作品", "", int(time.time()) - age,
                                   "https://www.douyin.com/video/123456789")
    jobs = await repo.create_snapshot_jobs(post, stages=(("1h", 3600),))
    return account, post, jobs[0]


@pytest.mark.asyncio
async def test_pause_preserves_deadline_and_resuming_applies_original_window(isolated_db):
    account, _, job = await seed_job("pausedAccount", age=7200, paused=True)
    original_due = job.due_at
    assert await repo.list_due_jobs() == []
    assert (await repo.get_job(job.id)).status == "pending"
    await repo.update_monitored_account(account.id, enabled=True)
    assert await repo.list_due_jobs() == []
    resumed = await repo.get_job(job.id)
    assert resumed.status == "missed" and resumed.due_at == original_due


@pytest.mark.asyncio
async def test_discovery_only_stop_continues_existing_snapshots(isolated_db):
    account, _, job = await seed_job("discoveryOffAccount", enabled=False)
    assert [item.id for item in await repo.list_due_jobs()] == [job.id]
    service = MonitorService()
    service._crawler_is_busy = lambda: False
    fetcher = AsyncMock()
    result = await service.discover_account(account.sec_user_id, fetcher=fetcher)
    assert result["error_code"] == "account_paused"
    fetcher.__aenter__.assert_not_awaited()


@pytest.mark.asyncio
async def test_runtime_updates_do_not_change_configuration_version(client, monkeypatch):
    account, _, _ = await seed_job("summaryAccount")
    original_version = account.updated_at
    await repo.update_account_discovered_at(account.id, discovered_at=original_version + 100)
    await repo.record_account_discovery_result(account.sec_user_id, {"status": "partial", "created_posts": 2, "created_jobs": 10}, original_version + 110)
    result = (await client.get("/monitor/accounts")).json()["accounts"][0]
    assert result["updated_at"] == original_version
    assert result["today_new_posts"] == 1 and result["due_jobs"] == 1
    assert result["last_discovery_result"]["status"] == "partial"
    # A new service instance reads the saved result; it is not tied to execution memory.
    restored = await repo.get_monitored_account_by_id(account.id)
    assert json.loads(restored.last_discovery_result)["created_posts"] == 2


@pytest.mark.asyncio
async def test_deleting_account_retains_posts_and_terminates_pending_jobs(client):
    account, post, job = await seed_job("deletedAccount")
    assert (await client.delete(f"/monitor/accounts/{account.id}")).status_code == 200
    assert await repo.get_post(post.aweme_id) is not None
    assert (await repo.get_job(job.id)).status == "skipped"
    assert await repo.list_due_jobs() == []


@pytest.mark.asyncio
async def test_pause_between_snapshot_requests_keeps_remaining_job_pending(isolated_db, monkeypatch):
    first, _, first_job = await seed_job("firstAccount")
    second, _, second_job = await seed_job("secondAccount")
    service = MonitorService()
    service._crawler_is_busy = lambda: False
    calls = []

    class Fetcher:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def fetch_metrics(self, aweme_id):
            calls.append(aweme_id)
            await repo.update_monitored_account(second.id, snapshots_paused=True)
            return {"liked_count": 10, "collected_count": 1, "comment_count": 2, "share_count": 3}

    result = await service.run_due_snapshots(fetcher=Fetcher())
    assert result["completed"] == 1 and len(calls) == 1
    assert (await repo.get_job(first_job.id)).status == "done"
    assert (await repo.get_job(second_job.id)).status == "pending"


@pytest.mark.asyncio
async def test_discovery_result_is_saved_on_partial_failure(isolated_db, monkeypatch):
    account = await repo.upsert_monitored_account("failureAccount")
    monkeypatch.setattr("api.services.monitor_service.crawler_manager.add_log", AsyncMock())
    service = MonitorService()
    service._crawler_is_busy = lambda: False

    class Fetcher:
        async def __aenter__(self):
            raise RuntimeError("network timeout")

        async def __aexit__(self, *args):
            return None

    result = await service.discover_account(account.sec_user_id, fetcher=Fetcher())
    saved = await repo.get_monitored_account_by_id(account.id)
    assert result["error_code"] == "network_timeout"
    assert json.loads(saved.last_discovery_result)["error_code"] == "network_timeout"


@pytest.mark.asyncio
async def test_legacy_account_migration_keeps_discovery_disabled(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute("""CREATE TABLE douyin_monitored_accounts (
            id INTEGER PRIMARY KEY, platform VARCHAR(32), sec_user_id VARCHAR(255), display_name VARCHAR(255),
            profile_url TEXT, enabled BOOLEAN, discover_interval_minutes INTEGER,
            last_discovered_at BIGINT, created_at BIGINT, updated_at BIGINT)""")
        connection.execute("INSERT INTO douyin_monitored_accounts VALUES (1, 'dy', 'legacyAccount', '旧账号', '', 0, 30, NULL, 100, 100)")
    monkeypatch.setitem(db_session.sqlite_db_config, "db_path", str(path))
    monkeypatch.setattr(db_session, "_engines", {})
    try:
        await db_session.create_tables("sqlite")
        legacy = await repo.get_monitored_account_by_id(1)
        assert not legacy.enabled and not legacy.snapshots_paused
        assert legacy.updated_at == 100 and legacy.last_discovery_result is None
    finally:
        for engine in db_session._engines.values():
            await engine.dispose()
