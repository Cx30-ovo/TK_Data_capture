"""Removed feature routes stay absent, without starting application workers."""
import importlib

import httpx
import pytest


@pytest.mark.asyncio
async def test_removed_routes_return_404_without_storage(tmp_path, monkeypatch):
    from api.main import app
    from config.db_config import sqlite_db_config

    monkeypatch.setitem(sqlite_db_config, 'db_path', str(tmp_path/'source.db'))
    paths = [
        '/event-comparison', '/event-comparison/posts',
        '/event-comparison/candidates', '/event-comparison/candidate-runs',
        '/event-comparison/candidate-runs/old', '/event-comparison/candidate-runs/old/check',
        '/event-comparison/feedback', '/event-comparison/feedback-summary',
        '/event-comparison/automatic-runs', '/event-comparison/automatic-runs/old',
        '/event-comparison/automatic-runs/old/stop', '/event-comparison/automation',
        '/event-opportunities', '/event-opportunities/titles',
        '/editorial-drafts', '/editorial-drafts/old', '/editorial-drafts/old/revisions',
        '/idea-automation', '/training-data/readiness', '/training-data/exports',
    ]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        for path in paths:
            for method in ('GET', 'POST', 'PUT'):
                response = await client.request(method, '/api/monitor'+path, json={})
                assert response.status_code == 404, (method, path, response.text)
    assert list(tmp_path.iterdir()) == []


def test_retained_account_and_topic_routes_registered():
    from api.main import app

    paths = {r.path for r in app.routes}
    for path in ('/api/monitor/accounts', '/api/monitor/account-matrix',
                 '/api/monitor/accounts/{account_id}/profile',
                 '/api/monitor/accounts/{account_id}/style-profile',
                 '/api/monitor/execution', '/api/topic-monitors', '/api/health'):
        assert path in paths


@pytest.mark.asyncio
async def test_lifespan_only_starts_retained_workers(monkeypatch):
    from unittest.mock import AsyncMock
    import config

    main = importlib.import_module('api.main')
    monkeypatch.setattr(config, 'START_BROWSER_ON_SERVICE_START', False)
    monkeypatch.setattr(main.db, 'init_db', AsyncMock())
    pairs = []
    for service in (main.scheduler_service, main.monitor_service, main.maintenance_service):
        start, stop = AsyncMock(), AsyncMock()
        monkeypatch.setattr(service, 'start', start)
        monkeypatch.setattr(service, 'stop', stop)
        pairs.append((start, stop))
    start, stop = AsyncMock(), AsyncMock()
    monkeypatch.setattr(main.topic_monitor_service, 'start_runner', start)
    monkeypatch.setattr(main.topic_monitor_service, 'stop_runner', stop)
    pairs.append((start, stop))
    async with main.lifespan(main.app):
        for start, stop in pairs:
            start.assert_awaited_once()
            stop.assert_not_awaited()
    for start, stop in pairs:
        stop.assert_awaited_once()
