"""Regression tests for browser-session snapshot validation and cooldowns."""

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services import monitor_service as module
from api.services.monitor_service import DouyinMonitorFetcher, MonitorService


@pytest.mark.asyncio
async def test_snapshot_rejects_response_for_another_post():
    fetcher = DouyinMonitorFetcher()
    fetcher._client = SimpleNamespace(get_video_by_id=AsyncMock(return_value={
        "aweme_id": "other-post",
        "statistics": {"digg_count": 1, "collect_count": 2, "comment_count": 3, "share_count": 4},
    }))
    with pytest.raises(ValueError, match="does not match"):
        await fetcher._fetch_metrics_once("requested-post")


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["digg_count", "collect_count", "comment_count", "share_count"])
async def test_snapshot_rejects_missing_metrics_instead_of_recording_zero(missing):
    statistics = {"digg_count": 1, "collect_count": 2, "comment_count": 3, "share_count": 4}
    statistics.pop(missing)
    fetcher = DouyinMonitorFetcher()
    fetcher._client = SimpleNamespace(get_video_by_id=AsyncMock(return_value={
        "aweme_id": "requested-post", "statistics": statistics,
    }))
    with pytest.raises(ValueError, match="missing required"):
        await fetcher._fetch_metrics_once("requested-post")


@pytest.mark.asyncio
async def test_snapshot_accepts_real_zero_metrics():
    fetcher = DouyinMonitorFetcher()
    fetcher._client = SimpleNamespace(get_video_by_id=AsyncMock(return_value={
        "aweme_id": "requested-post",
        "statistics": {"digg_count": 0, "collect_count": 0, "comment_count": 0, "share_count": 0},
    }))
    metrics = await fetcher._fetch_metrics_once("requested-post")
    assert metrics == {
        "liked_count": 0, "collected_count": 0, "comment_count": 0,
        "share_count": 0, "cover_url": "",
    }


@pytest.mark.asyncio
async def test_fetcher_closes_owned_pages_before_disconnecting():
    fetcher = DouyinMonitorFetcher()
    actions = MagicMock()
    actions.attach_mock(AsyncMock(), "close_pages")
    actions.attach_mock(AsyncMock(), "disconnect")
    actions.attach_mock(AsyncMock(), "stop")
    fetcher._client = SimpleNamespace(close_browser_pages=actions.close_pages)
    fetcher._crawler = SimpleNamespace(cdp_manager=SimpleNamespace(cleanup=actions.disconnect))
    fetcher._playwright = SimpleNamespace(stop=actions.stop)
    await fetcher.__aexit__(None, None, None)
    assert [call[0] for call in actions.mock_calls] == ["close_pages", "disconnect", "stop"]
    assert fetcher._client is None


@pytest.mark.asyncio
async def test_risk_cooldown_grows_to_six_hours_and_success_resets_it():
    service = MonitorService()
    with patch.object(module.crawler_manager, "add_log", AsyncMock()), patch.object(module.time, "time", return_value=1000):
        for expected in (1800, 3600, 7200, 14400, 21600, 21600):
            assert await service._start_risk_control_cooldown("Blocked by Argus") == expected
            assert service._risk_control_cooldown_remaining() == expected
        service._clear_risk_control_cooldown()
        assert service._risk_control_cooldown_remaining() == 0
        assert await service._start_risk_control_cooldown("Blocked by Argus") == 1800


@pytest.mark.asyncio
async def test_cooldown_defers_discovery_and_snapshots_without_entering_browser():
    service = MonitorService()
    service._risk_control_until = time.time() + 1800
    fetcher = MagicMock()
    fetcher.__aenter__ = AsyncMock()
    with patch.object(module.monitor_repository, "list_due_jobs", AsyncMock()) as jobs:
        for result in (
            await service.discover_account(sec_user_id="test-user", fetcher=fetcher),
            await service.run_due_snapshots(fetcher=fetcher),
        ):
            assert result["status"] == "deferred"
            assert result["reason"] == "risk_control_cooldown"
            assert result["retry_after_seconds"] > 0
        jobs.assert_not_awaited()
    fetcher.__aenter__.assert_not_awaited()


@pytest.mark.asyncio
async def test_risk_control_stops_the_current_snapshot_batch():
    service = MonitorService()
    service._create_alert = AsyncMock()
    fetcher = MagicMock()
    fetcher.__aenter__ = AsyncMock(return_value=fetcher)
    fetcher.__aexit__ = AsyncMock(return_value=False)
    fetcher.fetch_metrics = AsyncMock(side_effect=RuntimeError("Blocked by ArgusSecurityPlugin Uifid Not Found"))
    jobs = [SimpleNamespace(id=i, aweme_id=str(i), sec_user_id="test-user", platform="dy") for i in (1, 2)]
    with (
        patch.object(module.crawler_manager, "add_log", AsyncMock()),
        patch.object(service, "_crawler_is_busy", return_value=False),
        patch.object(module.monitor_repository, "list_due_jobs", AsyncMock(return_value=jobs)),
        patch.object(module.monitor_repository, "mark_job_running", AsyncMock(return_value=jobs[0])) as running,
        patch.object(module.monitor_repository, "mark_job_retry", AsyncMock(return_value=SimpleNamespace(status="retry"))) as retry,
    ):
        result = await service.run_due_snapshots(fetcher=fetcher)
        assert result["retried"] == 1
        assert result["completed"] == 0
        fetcher.fetch_metrics.assert_awaited_once_with("1")
        running.assert_awaited_once_with(1)
        assert retry.await_args.kwargs["retry_delay_seconds"] == 1800
    assert service._risk_control_cooldown_remaining() > 0
