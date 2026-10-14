"""Recovery faults are simulated without Chrome or production database access."""

import asyncio
import time
from contextvars import Context
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.services import monitor_service as module
from api.services.browser_recovery import BrowserRecovery
from api.services.monitor_service import DouyinMonitorFetcher, MonitorService
from tools.collection_errors import classify_collection_error
from tools.douyin_browser_coordinator import DouyinTabLease


def failure(message="CDP disconnected"):
    return classify_collection_error(RuntimeError(message))


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setattr(module.crawler_manager, "add_log", AsyncMock())
    # Unexpected DB access must fail instead of opening the user's database.
    monkeypatch.setattr(module, "monitor_repository", SimpleNamespace())
    result = MonitorService()
    result._crawler_is_busy = lambda: False
    return result


class FakeFetcher:
    def __init__(self, error=None, entered=None, finish=None):
        self.error, self.entered, self.finish = error, entered, finish
        self.calls = 0

    async def __aenter__(self):
        self.calls += 1
        if self.entered:
            self.entered.set()
        if self.finish:
            await self.finish.wait()
        if self.error:
            raise self.error
        return self

    async def __aexit__(self, *args):
        return False


def schedule(service):
    service._recovery.observe(failure())
    service._recovery.retry_at = 0


def test_timeout_streak_requires_three_and_resets_after_success():
    recovery = BrowserRecovery()
    timeout = classify_collection_error(TimeoutError())
    assert not recovery.observe(timeout)
    assert not recovery.observe(timeout)
    recovery.successful_request()
    assert not recovery.observe(timeout)
    assert not recovery.observe(timeout)
    assert recovery.observe(timeout)
    assert recovery.reset_page and recovery.pending
    assert recovery.snapshot()["retry_after_seconds"] <= 15


def test_repeated_signals_preserve_backoff_and_failure_delays(monkeypatch):
    monkeypatch.setattr("api.services.browser_recovery.time.time", lambda: 1000)
    recovery = BrowserRecovery()
    recovery.observe(failure())
    for delay in (15, 30, 60, 120, 900, 900):
        recovery.begin()
        assert recovery.failed(failure()) == delay
        retry_at = recovery.retry_at
        recovery.observe(failure())
        assert recovery.retry_at == retry_at
    assert recovery.snapshot()["attempts"] == 6


@pytest.mark.asyncio
@pytest.mark.parametrize("message", ["CDP disconnected", "抖音页签已切换"])
async def test_browser_fault_defers_operations_without_permanent_pause(service, message):
    await service._handle_collection_failure(failure(message), "discovery", "one")
    assert service._recovery.pending and not service._paused
    result = await service.discover_account("one")
    assert result["status"] == "deferred" and result["error_code"] == "browser_recovering"
    assert service._execution is None
    # Pending recovery must not touch jobs or mark them missed.
    await service._run_cycle()


@pytest.mark.asyncio
async def test_recovery_success_resumes_cycle_and_preserves_retry_state(service, monkeypatch):
    fetcher = FakeFetcher()
    monkeypatch.setattr(module, "DouyinMonitorFetcher", lambda: fetcher)
    schedule(service)
    service._discovery_retries = {
        "timeout": {"failure": classify_collection_error(TimeoutError())},
        "invalid": {"failure": classify_collection_error(ValueError())},
    }
    await service._recover_browser_if_due()
    assert fetcher.calls == 1 and not service._recovery.pending
    assert service._recovery.last_recovered_at and not service._paused
    assert set(service._discovery_retries) == {"invalid"}
    module.monitor_repository.mark_overdue_jobs_missed = AsyncMock(return_value=0)
    module.monitor_repository.list_monitored_accounts = AsyncMock(return_value=[])
    service.run_due_snapshots = AsyncMock()
    await service._run_cycle()
    service.run_due_snapshots.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("guard", ["paused", "crawler", "lock", "cooldown", "timer"])
async def test_no_launch_while_paused_busy_cooling_or_waiting(service, monkeypatch, guard):
    factory = MagicMock(return_value=FakeFetcher())
    monkeypatch.setattr(module, "DouyinMonitorFetcher", factory)
    schedule(service)
    if guard == "paused":
        service.request_safe_stop()
    elif guard == "crawler":
        service._crawler_is_busy = lambda: True
    elif guard == "lock":
        await service._lock.acquire()
    elif guard == "cooldown":
        service._risk_control_until = time.time() + 100
    else:
        service._recovery.retry_at = time.time() + 100
    try:
        await service._recover_browser_if_due()
        factory.assert_not_called()
        assert service._recovery.attempts == 0
    finally:
        if guard == "lock":
            service._lock.release()


@pytest.mark.asyncio
async def test_manual_pause_during_recovery_is_retained_and_no_duplicate_repair(service, monkeypatch):
    entered, finish = asyncio.Event(), asyncio.Event()
    fetcher = FakeFetcher(entered=entered, finish=finish)
    monkeypatch.setattr(module, "DouyinMonitorFetcher", lambda: fetcher)
    schedule(service)
    task = asyncio.create_task(service._recover_browser_if_due())
    await entered.wait()
    await service._recover_browser_if_due()
    service.request_safe_stop()
    assert fetcher.should_stop()
    finish.set()
    await task
    assert service._paused and fetcher.calls == 1
    await service._run_cycle()


@pytest.mark.asyncio
async def test_login_requires_user_action_while_risk_retains_cooldown(service, monkeypatch):
    monkeypatch.setattr(module, "DouyinMonitorFetcher", lambda: FakeFetcher(RuntimeError("login required")))
    schedule(service)
    await service._recover_browser_if_due()
    assert service._paused and service._recovery.state == "login_required"
    assert not service._recovery.pending
    service.resume_monitoring()
    monkeypatch.setattr(module, "DouyinMonitorFetcher", lambda: FakeFetcher(RuntimeError("Blocked by Argus")))
    schedule(service)
    await service._recover_browser_if_due()
    assert service._risk_control_cooldown_remaining() > 0
    assert service._recovery.pending and not service._paused
    assert service.resume_monitoring()["retry_after_seconds"] > 0


@pytest.mark.asyncio
async def test_recovery_timeout_and_cancel_release_service_lock(service, monkeypatch):
    entered, finish = asyncio.Event(), asyncio.Event()
    monkeypatch.setattr(module.config, "BROWSER_RECOVERY_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(module, "DouyinMonitorFetcher", lambda: FakeFetcher(finish=finish))
    schedule(service)
    await service._recover_browser_if_due()
    assert service._recovery.state == "waiting" and not service._lock.locked()
    assert service._recovery.error["error_code"] == "network_timeout"
    monkeypatch.setattr(module.config, "BROWSER_RECOVERY_TIMEOUT_SECONDS", 10)
    monkeypatch.setattr(module, "DouyinMonitorFetcher", lambda: FakeFetcher(entered=entered, finish=finish))
    service._recovery.retry_at = 0
    task = asyncio.create_task(service._recover_browser_if_due())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert service._recovery.state == "waiting" and not service._lock.locked()


@pytest.mark.asyncio
async def test_failed_entry_timeout_releases_global_lease_and_playwright(tmp_path, monkeypatch):
    original_lease = DouyinTabLease
    path = tmp_path / "tab.lock"
    monkeypatch.setattr(module, "DouyinTabLease", lambda **kw: original_lease(path, **kw))
    monkeypatch.setattr(module.config, "BROWSER_RECOVERY_TIMEOUT_SECONDS", 0.01)
    fetcher = DouyinMonitorFetcher()
    stop = AsyncMock()
    finish = asyncio.Event()

    async def hung_open():
        fetcher._playwright = SimpleNamespace(stop=stop)
        await finish.wait()

    fetcher._open_browser = hung_open
    with pytest.raises(TimeoutError):
        await fetcher.__aenter__()
    stop.assert_awaited_once()
    assert fetcher._playwright is None and fetcher._lease is None
    async def acquire():
        async with original_lease(path, timeout=0):
            pass
    await asyncio.create_task(acquire(), context=Context())


@pytest.mark.asyncio
async def test_idle_health_detects_closed_chrome_and_throttles_probe(service, monkeypatch):
    manager = SimpleNamespace(_read_recorded_port=lambda: 9223,
                              _test_cdp_connection=AsyncMock(return_value=False))
    monkeypatch.setattr(module, "CDPBrowserManager", lambda **kw: manager)
    await service._check_browser_health()
    assert service._recovery.pending
    await service._check_browser_health()
    manager._test_cdp_connection.assert_awaited_once()
    service._recovery.recovered()
    await service._check_browser_health()
    manager._test_cdp_connection.assert_awaited_once()


@pytest.mark.asyncio
async def test_disabled_recovery_preserves_manual_browser_pause(service):
    service._recovery.enabled = False
    await service._handle_collection_failure(failure(), "discovery", "one")
    assert service._paused and not service._recovery.pending


@pytest.mark.asyncio
async def test_recovery_never_falls_back_to_an_unrelated_browser(monkeypatch):
    fetcher = DouyinMonitorFetcher()
    playwright = SimpleNamespace(stop=AsyncMock())
    monkeypatch.setattr(module, "async_playwright", lambda: SimpleNamespace(start=AsyncMock(return_value=playwright)))
    manager = SimpleNamespace(launch_and_connect=AsyncMock(side_effect=RuntimeError("CDP disconnected")))
    factory = MagicMock(return_value=manager)
    monkeypatch.setattr(module, "CDPBrowserManager", factory)
    crawler = SimpleNamespace(launch_browser=AsyncMock())
    monkeypatch.setattr(module, "DouYinCrawler", lambda: crawler)
    with pytest.raises(RuntimeError):
        await fetcher._open_browser()
    factory.assert_called_once_with(profile_platform="dy")
    crawler.launch_browser.assert_not_awaited()


@pytest.mark.asyncio
async def test_hot_rank_uses_stale_cache_while_recovery_pending(service):
    schedule(service)
    service._hot_rank_cache = {"items": [{"word": "cached"}]}
    result = await service.get_hot_rank(force=True)
    assert result["stale"] and result["cached"]
    assert "恢复" in result["warning"]


@pytest.mark.asyncio
async def test_hung_second_page_has_deadline_and_retains_first_page(monkeypatch):
    monkeypatch.setattr(module.config, "BROWSER_RECOVERY_TIMEOUT_SECONDS", 0.01)
    finish = asyncio.Event()
    calls = 0
    async def posts(*args):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"aweme_list": [{"aweme_id": "first"}], "has_more": True, "max_cursor": "next"}
        await finish.wait()
    fetcher = DouyinMonitorFetcher()
    fetcher._client = SimpleNamespace(get_user_aweme_posts=posts)
    with pytest.raises(module.PartialDiscoveryError) as exc:
        await fetcher.fetch_latest_posts("one", set())
    assert isinstance(exc.value.cause, TimeoutError)
    assert [post["aweme_id"] for post in exc.value.posts] == ["first"]


@pytest.mark.asyncio
async def test_hung_cleanup_still_stops_playwright_and_releases_global_lease(tmp_path, monkeypatch):
    real_wait_for = asyncio.wait_for
    async def short_wait(awaitable, timeout):
        return await real_wait_for(awaitable, 0.01)
    monkeypatch.setattr(module.asyncio, "wait_for", short_wait)
    monkeypatch.setattr(module.crawler_manager, "add_log", AsyncMock())
    path = tmp_path / "tab.lock"
    lease = DouyinTabLease(path)
    await lease.__aenter__()
    fetcher = DouyinMonitorFetcher()
    fetcher._lease = lease
    finish = asyncio.Event()
    fetcher._client = SimpleNamespace(close_browser_pages=finish.wait)
    cleanup = AsyncMock()
    stop = AsyncMock()
    fetcher._crawler = SimpleNamespace(cdp_manager=SimpleNamespace(cleanup=cleanup))
    fetcher._playwright = SimpleNamespace(stop=stop)
    await fetcher.__aexit__(None, None, None)
    cleanup.assert_awaited_once()
    stop.assert_awaited_once()
    assert fetcher._lease is None and fetcher._client is None
    async def acquire():
        async with DouyinTabLease(path, timeout=0):
            pass
    await asyncio.create_task(acquire(), context=Context())
