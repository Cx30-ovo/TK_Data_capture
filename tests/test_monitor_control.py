"""Offline tests for tab coordination, classified failures, and safe stopping."""

import asyncio
import sys
import time
from contextvars import Context
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.services import monitor_service as module
from api.services.monitor_service import DouyinMonitorFetcher, MonitorService, PartialDiscoveryError
from tools.collection_errors import classify_collection_error
from tools.douyin_browser_coordinator import CollectionStoppedError, DouyinBrowserBusyError, DouyinTabLease


@pytest.mark.asyncio
async def test_tab_lock_serializes_independent_clients_and_releases(tmp_path):
    path = tmp_path / "tab.lock"
    acquired = asyncio.Event()
    waiting = asyncio.Event()

    async def other_client():
        async with DouyinTabLease(path, on_wait=waiting.set):
            acquired.set()

    async with DouyinTabLease(path):
        other = asyncio.create_task(other_client(), context=Context())
        await asyncio.wait_for(waiting.wait(), 2)
        assert not acquired.is_set()
        # Nested operations/child detail tasks inherit the held lease.
        async with DouyinTabLease(path, timeout=0):
            pass
    await asyncio.wait_for(other, 2)
    assert acquired.is_set()


@pytest.mark.asyncio
async def test_tab_lock_serializes_real_child_process(tmp_path):
    path = tmp_path / "tab.lock"
    script = Path(__file__).parent / "helpers" / "tab_lease_probe.py"

    async def probe():
        proc = await asyncio.create_subprocess_exec(sys.executable, str(script), str(path), stdout=asyncio.subprocess.PIPE)
        output, _ = await asyncio.wait_for(proc.communicate(), 10)
        return proc.returncode, output.decode().strip()

    async with DouyinTabLease(path):
        assert await probe() == (2, "busy")
    assert await probe() == (0, "acquired")


@pytest.mark.asyncio
async def test_stop_and_cancellation_while_waiting_release_handle(tmp_path):
    path = tmp_path / "tab.lock"
    stop = asyncio.Event()
    waiting = asyncio.Event()

    async def waiter():
        async with DouyinTabLease(path, should_stop=stop.is_set, on_wait=waiting.set):
            pytest.fail("The holder still owns the tab")

    async with DouyinTabLease(path):
        task = asyncio.create_task(waiter(), context=Context())
        await asyncio.wait_for(waiting.wait(), 2)
        stop.set()
        with pytest.raises(CollectionStoppedError):
            await task
        stop.clear()
        waiting.clear()
        task = asyncio.create_task(waiter(), context=Context())
        await asyncio.wait_for(waiting.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    async with DouyinTabLease(path, timeout=0):
        pass


@pytest.mark.parametrize("error,code", [
    (RuntimeError("Blocked by ArgusSecurityPlugin Uifid Not Found"), "risk_control"),
    (RuntimeError("Douyin login required"), "login_required"),
    (TimeoutError(), "network_timeout"),
    (RuntimeError("Target closed"), "browser_disconnected"),
    (RuntimeError("抖音页签已切换，分页状态失效"), "tab_changed"),
    (module.DouyinPostUnavailableError("gone"), "post_deleted"),
    (ValueError("missing required metrics"), "invalid_response"),
    (DouyinBrowserBusyError("busy"), "browser_busy"),
    (CollectionStoppedError("stop"), "user_stop"),
])
def test_errors_have_stable_codes_and_actionable_messages(error, code):
    failure = classify_collection_error(error)
    assert failure.error_code == code
    assert failure.message and failure.action
    secret_error = RuntimeError("unknown: https://example.com?cookie=private")
    assert "private" not in str(classify_collection_error(secret_error).as_dict())


class FakeFetcher:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def account():
    return SimpleNamespace(id=1, sec_user_id="account-one", display_name="测试账号", platform="dy")


def post(i):
    return {"aweme_id": str(i), "sec_user_id": "account-one", "create_time": int(time.time()),
            "canonical_url": f"https://www.douyin.com/video/{i}", "title": "测试"}


@pytest.fixture
def repository():
    """Every repository call is mocked: no production DB access is possible."""
    from unittest.mock import MagicMock
    repo = MagicMock()
    repo.get_monitored_account = AsyncMock(return_value=account())
    repo.list_post_ids = AsyncMock(return_value=set())
    repo.update_account_discovered_at = AsyncMock()
    repo.record_first_seen_snapshot = AsyncMock()
    repo.create_snapshot_jobs = AsyncMock(return_value=[object()] * 5)
    repo.create_alert = AsyncMock()
    repo.record_snapshot = AsyncMock()
    repo.mark_job_retry = AsyncMock(return_value=SimpleNamespace(status="pending"))
    repo.mark_overdue_jobs_missed = AsyncMock(return_value=0)
    repo.upsert_post = AsyncMock(side_effect=lambda **kw: (SimpleNamespace(**kw, first_seen_at=int(time.time())), True))
    with patch.object(module, "monitor_repository", repo), patch.object(module.crawler_manager, "add_log", AsyncMock()):
        yield repo


@pytest.mark.asyncio
async def test_discovery_stop_preserves_current_page_and_rejects_duplicate(repository):
    service = MonitorService()
    service._crawler_is_busy = lambda: False
    entered, finish = asyncio.Event(), asyncio.Event()
    fetcher = FakeFetcher()

    async def fetch(**kw):
        entered.set()
        await finish.wait()
        return [post(1), post(2)]

    fetcher.fetch_latest_posts = fetch
    task = asyncio.create_task(service.discover_account("account-one", fetcher=fetcher))
    await entered.wait()
    run_id = service.execution_status()["execution"]["run_id"]
    duplicate = await service.discover_account("account-one", fetcher=fetcher)
    assert duplicate["error_code"] == "browser_busy"
    assert service.request_safe_stop("stale-id")["status"] == "stale"
    assert not service._paused
    assert service.request_safe_stop(run_id)["status"] == "stopping"
    finish.set()
    result = await task
    assert result["status"] == "stopped"
    assert result["created_posts"] == 2 and result["created_jobs"] == 10
    assert repository.upsert_post.await_count == 2
    repository.update_account_discovered_at.assert_not_awaited()
    assert service.execution_status()["execution"]["saved"] == 2
    await service._run_cycle()
    repository.mark_overdue_jobs_missed.assert_not_awaited()
    assert service.resume_monitoring()["status"] == "ok"


@pytest.mark.asyncio
async def test_partial_discovery_saves_posts_before_risk_cooldown(repository):
    service = MonitorService()
    service._crawler_is_busy = lambda: False
    fetcher = FakeFetcher()
    fetcher.fetch_latest_posts = AsyncMock(side_effect=PartialDiscoveryError(RuntimeError("Blocked by Argus"), [post(1)]))
    result = await service.discover_account("account-one", fetcher=fetcher)
    assert result["status"] == "partial" and result["created_posts"] == 1
    assert result["error_code"] == "risk_control"
    assert service._risk_control_failures == 1
    assert service.execution_status()["execution"]["state"] == "partial"
    repository.update_account_discovered_at.assert_not_awaited()


@pytest.mark.asyncio
async def test_snapshot_stop_finishes_current_job_and_leaves_rest_unstarted(repository):
    service = MonitorService()
    service._crawler_is_busy = lambda: False
    jobs = [SimpleNamespace(id=i, aweme_id=str(i), sec_user_id="account-one", platform="dy") for i in range(1, 4)]
    repository.list_due_jobs = AsyncMock(return_value=jobs)
    repository.mark_job_running = AsyncMock(return_value=jobs[0])
    fetcher = FakeFetcher()
    entered, finish = asyncio.Event(), asyncio.Event()

    async def metrics(aweme_id):
        entered.set()
        await finish.wait()
        return {"liked_count": 12}

    fetcher.fetch_metrics = AsyncMock(side_effect=metrics)
    task = asyncio.create_task(service.run_due_snapshots(fetcher=fetcher))
    await entered.wait()
    execution = service.execution_status()["execution"]
    assert execution["total"] == 3 and execution["current_post"] == "1"
    service.request_safe_stop(execution["run_id"])
    assert service.resume_monitoring()["status"] == "busy"
    finish.set()
    result = await task
    assert result["status"] == "stopped" and result["completed"] == 1
    repository.mark_job_running.assert_awaited_once_with(1)
    repository.record_snapshot.assert_awaited_once()
    repository.mark_job_retry.assert_not_awaited()
    assert service.execution_status()["execution"]["processed"] == 1


@pytest.mark.asyncio
async def test_login_failure_is_not_500_and_requires_manual_resume(repository):
    service = MonitorService()
    service._crawler_is_busy = lambda: False
    fetcher = FakeFetcher()
    fetcher.fetch_latest_posts = AsyncMock(side_effect=RuntimeError("Douyin login required"))
    result = await service.discover_account("account-one", fetcher=fetcher)
    assert result["status"] == "error" and result["error_code"] == "login_required"
    assert service.execution_status()["paused"]
    repository.upsert_post.assert_not_awaited()


@pytest.mark.asyncio
async def test_fetcher_stops_at_page_boundary_and_retains_partial_failure():
    fetcher = DouyinMonitorFetcher()
    stop = False

    async def response(*args):
        nonlocal stop
        stop = True
        return {"aweme_list": [{"aweme_id": "1", "create_time": int(time.time())}], "has_more": True, "max_cursor": "10"}

    fetcher._client = SimpleNamespace(get_user_aweme_posts=AsyncMock(side_effect=response))
    fetcher.should_stop = lambda: stop
    posts = await fetcher.fetch_latest_posts("account-one", set())
    assert len(posts) == 1
    fetcher._client.get_user_aweme_posts.assert_awaited_once()
    stop = False
    fetcher._client.get_user_aweme_posts = AsyncMock(side_effect=[
        {"aweme_list": [{"aweme_id": "1"}], "has_more": True, "max_cursor": "10"}, RuntimeError("Target closed"),
    ])
    fetcher._reconnect = AsyncMock()
    with pytest.raises(PartialDiscoveryError) as error:
        await fetcher.fetch_latest_posts("account-one", set())
    assert len(error.value.posts) == 1
    fetcher._reconnect.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_browser_entry_releases_lease_and_cleans_resources(tmp_path, monkeypatch):
    path = tmp_path / "tab.lock"
    original = DouyinTabLease
    monkeypatch.setattr(module, "DouyinTabLease", lambda **kw: original(path, **kw))
    fetcher = DouyinMonitorFetcher()
    fetcher._open_browser = AsyncMock(side_effect=RuntimeError("login required"))
    fetcher._close_browser = AsyncMock()
    with pytest.raises(RuntimeError, match="login required"):
        await fetcher.__aenter__()
    fetcher._close_browser.assert_awaited_once()
    async with DouyinTabLease(path, timeout=0):
        pass


@pytest.mark.asyncio
async def test_cleanup_error_does_not_discard_partial_data(tmp_path, monkeypatch):
    original = DouyinTabLease
    path = tmp_path / "tab.lock"
    monkeypatch.setattr(module, "DouyinTabLease", lambda **kw: original(path, **kw))
    fetcher = DouyinMonitorFetcher()
    fetcher._open_browser = AsyncMock(return_value=fetcher)
    fetcher._close_browser = AsyncMock(side_effect=RuntimeError("Target closed"))
    with patch.object(module.crawler_manager, "add_log", AsyncMock()):
        async with fetcher:
            posts = [post(1)]
    assert len(posts) == 1
    async with DouyinTabLease(path, timeout=0):
        pass


@pytest.mark.asyncio
async def test_control_api_progress_stop_and_stale_run_are_consistent(monkeypatch):
    import httpx
    from fastapi import FastAPI
    from api.routers import monitor as routes
    from api.services.monitor_execution import MonitorExecution

    service = MonitorService()
    service._crawler_is_busy = lambda: False
    service._execution = MonitorExecution("discovery")
    monkeypatch.setattr(routes, "monitor_service", service)
    app = FastAPI()
    app.include_router(routes.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        state = await client.get("/monitor/execution")
        assert state.status_code == 200
        run_id = state.json()["execution"]["run_id"]
        stale = await client.post("/monitor/execution/stop", params={"run_id": "old"})
        assert stale.status_code == 409 and not service._paused
        stop = await client.post("/monitor/execution/stop", params={"run_id": run_id})
        assert stop.status_code == 200 and stop.json()["status"] == "stopping"
        assert (await client.post("/monitor/execution/resume")).status_code == 409
        service._execution.update(finished_at=time.time(), state="stopped")
        assert (await client.post("/monitor/execution/resume")).status_code == 200


@pytest.mark.asyncio
async def test_risk_batch_defers_only_current_job_without_touching_remaining(repository):
    service = MonitorService()
    service._crawler_is_busy = lambda: False
    jobs = [SimpleNamespace(id=i, aweme_id=str(i), sec_user_id="account-one", platform="dy") for i in (1, 2)]
    repository.list_due_jobs = AsyncMock(return_value=jobs)
    repository.mark_job_running = AsyncMock(return_value=jobs[0])
    fetcher = FakeFetcher()
    fetcher.fetch_metrics = AsyncMock(side_effect=RuntimeError("Blocked by Argus"))
    result = await service.run_due_snapshots(fetcher=fetcher)
    assert result["error_code"] == "risk_control" and result["retried"] == 1
    assert service._risk_control_failures == 1
    repository.mark_job_running.assert_awaited_once_with(1)
    repository.mark_job_retry.assert_awaited_once()
    assert repository.mark_job_retry.await_args.kwargs["retry_delay_seconds"] == 1800
    assert module.classify_job_error({"last_error": "[tab_changed] 页签切换"}) == "tab_changed"


@pytest.mark.asyncio
async def test_hot_rank_respects_shared_risk_cooldown_without_new_requests():
    service = MonitorService()
    service._crawler_is_busy = lambda: False
    service._risk_control_until = time.time() + 1800
    fetcher = FakeFetcher()
    fetcher.fetch_hot_rank = AsyncMock(return_value=[])
    with pytest.raises(module.MonitorHotRankError, match="风控"):
        await service.get_hot_rank(force=True, fetcher=fetcher)
    fetcher.fetch_hot_rank.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("backfill", [False, True])
async def test_scheduled_discovery_stops_at_known_posts_except_cover_backfill(repository, backfill):
    service = MonitorService()
    service._crawler_is_busy = lambda: False
    repository.list_post_ids.return_value = {"known"}
    repository.list_post_ids_missing_cover = AsyncMock(return_value=set())
    fetcher = DouyinMonitorFetcher()
    fetcher._client = SimpleNamespace(get_user_aweme_posts=AsyncMock(side_effect=[
        {"aweme_list": [post(1), {**post("known"), "is_top": 0}], "has_more": True, "max_cursor": "10"},
        {"aweme_list": [post(2)], "has_more": False},
    ]))
    fetcher._open_browser = AsyncMock(return_value=fetcher)
    fetcher._close_browser = AsyncMock()
    result = await service.discover_account("account-one", fetcher=fetcher, backfill_covers=backfill)
    assert result["status"] == "ok"
    assert fetcher._client.get_user_aweme_posts.await_count == (2 if backfill else 1)
    assert result["fetched"] == (3 if backfill else 2)


@pytest.mark.asyncio
async def test_known_pinned_post_does_not_hide_new_posts_on_next_page():
    fetcher = DouyinMonitorFetcher()
    fetcher._client = SimpleNamespace(get_user_aweme_posts=AsyncMock(side_effect=[
        {"aweme_list": [{**post("pinned"), "is_top": 1, "create_time": 1}], "has_more": True, "max_cursor": "10"},
        {"aweme_list": [post(1), post("known")], "has_more": True, "max_cursor": "20"},
    ]))
    posts = await fetcher.fetch_latest_posts("account-one", {"pinned", "known"},
                                             published_since=int(time.time()) - 86400, stop_on_known=True)
    assert [item["aweme_id"] for item in posts] == ["pinned", "1", "known"]
    assert fetcher._client.get_user_aweme_posts.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("partial", [False, True])
async def test_discovery_timeout_backoff_preserves_data_and_resets_on_success(repository, partial):
    service = MonitorService()
    service._crawler_is_busy = lambda: False
    fetcher = FakeFetcher()
    cause = TimeoutError("page timed out")
    fetcher.fetch_latest_posts = AsyncMock(side_effect=PartialDiscoveryError(cause, [post(1)]) if partial else cause)
    for delay in (120, 240, 480, 960, 1800, 1800):
        result = await service.discover_account("account-one", fetcher=fetcher)
        assert result["status"] == ("partial" if partial else "error")
        assert result["error_code"] == "network_timeout"
        assert result["retry_after_seconds"] == delay
        assert not service._paused and service._risk_control_until == 0
        repository.update_account_discovered_at.assert_not_awaited()
        calls = fetcher.fetch_latest_posts.await_count
        deferred = await service.discover_account("account-one", fetcher=fetcher)
        assert deferred["status"] == "deferred"
        assert 0 < deferred["retry_after_seconds"] <= delay
        assert fetcher.fetch_latest_posts.await_count == calls
        service._discovery_retries["account-one"]["until"] = time.time() - 1
    assert repository.upsert_post.await_count == (6 if partial else 0)
    fetcher.fetch_latest_posts.side_effect = None
    fetcher.fetch_latest_posts.return_value = []
    assert (await service.discover_account("account-one", fetcher=fetcher))["status"] == "ok"
    assert "account-one" not in service._discovery_retries
    repository.update_account_discovered_at.assert_awaited_once_with(1)
    fetcher.fetch_latest_posts.side_effect = cause
    assert (await service.discover_account("account-one", fetcher=fetcher))["retry_after_seconds"] == 120


@pytest.mark.asyncio
async def test_account_backoff_does_not_stop_other_accounts_or_snapshot_cycles(repository):
    service = MonitorService()
    service._crawler_is_busy = lambda: False
    first = account()
    first.last_discovered_at, first.discover_interval_minutes = 0, 5
    second = SimpleNamespace(sec_user_id="account-two", display_name="另一账号", last_discovered_at=0,
                             discover_interval_minutes=5)
    repository.list_monitored_accounts = AsyncMock(return_value=[first, second])
    service.run_due_snapshots = AsyncMock()
    service.discover_account = AsyncMock()
    await service._defer_discovery_retry(first.sec_user_id, classify_collection_error(TimeoutError()))
    await service._run_cycle()
    service.run_due_snapshots.assert_awaited_once()
    service.discover_account.assert_awaited_once_with(sec_user_id="account-two")
    service._discovery_retries[first.sec_user_id]["until"] = time.time() - 1
    service.discover_account.reset_mock()
    await service._run_cycle()
    assert service.discover_account.await_count == 2
