"""Multi-account scheduler fairness and bounded topic slices."""
import asyncio
import hashlib
import sqlite3
import time
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock

from api.services import monitor_service as monitor_module
from api.services import topic_monitor_service as topic_service
from api.services.monitor_scheduler import MonitorScheduler
from database import monitor_comments_repository as comment_repo
from database import db_session
from database.monitor_repository import monitor_repository
from database import topic_monitor_repository as topic_repo


def account(ident, last, interval=5):
    return SimpleNamespace(id=ident, sec_user_id=f'account-{ident}', display_name=f'Account {ident}',
        enabled=True, last_discovered_at=last, discover_interval_minutes=interval,
        last_discovery_result=None, snapshots_paused=False)


def test_oldest_due_first_and_equal_age_round_robin(monkeypatch):
    service = monitor_module.MonitorService()
    monkeypatch.setattr(service, '_discovery_retry_remaining', lambda _key: 0)
    accounts = [account(1, 0), account(2, 0), account(3, 0)]
    assert service._choose_due_account(accounts, now=1000).id == 1
    assert service._choose_due_account(accounts, now=1000).id == 2
    assert service._choose_due_account(accounts, now=1000).id == 3
    accounts[0].last_discovered_at = 950
    assert service._choose_due_account(accounts, now=1000).id == 2


@pytest.mark.asyncio
async def test_scheduler_admits_waiters_in_fifo_order():
    scheduler = MonitorScheduler()
    entered = []
    release = asyncio.Event()
    async def operation(name):
        async with scheduler.turn(name):
            entered.append(name)
            if name == 'first':await release.wait()
    first = asyncio.create_task(operation('first'))
    await asyncio.sleep(0)
    second = asyncio.create_task(operation('second'))
    third = asyncio.create_task(operation('third'))
    await asyncio.sleep(0)
    assert [item['kind'] for item in scheduler.snapshot()['waiting']] == ['second', 'third']
    release.set()
    await asyncio.gather(first, second, third)
    assert entered == ['first', 'second', 'third']
    assert scheduler.snapshot() == {'active': None, 'waiting': []}


@pytest.mark.asyncio
async def test_comment_jobs_rotate_accounts_without_skipping_due_work(tmp_path, monkeypatch):
    source = tmp_path / 'source.db'
    with sqlite3.connect(source):pass
    for key, ident in [('a', '101'), ('a', '102'), ('b', '201'), ('c', '301')]:
        comment_repo.save_policy(source, key, {'enabled': True, 'include_replies': True})
        comment_repo.enqueue(source, key, [ident])
    assert comment_repo.next_due_task(source, ['a', 'b', 'c'], 'a')['aweme_id'] == '201'
    assert comment_repo.next_due_task(source, ['a', 'b', 'c'], 'b')['aweme_id'] == '301'
    assert comment_repo.next_due_task(source, ['a', 'b', 'c'], 'c')['aweme_id'] == '101'
    comment_repo.save_policy(source, 'b', {'enabled': False})
    assert comment_repo.next_due_task(source, ['a', 'b', 'c'], 'a')['account_key'] == 'c'


@pytest.mark.asyncio
async def test_health_workload_is_per_account_and_read_only(monkeypatch):
    service = monitor_module.MonitorService()
    first, second = account(1, 100), account(2, 0)
    second.enabled = False
    second.last_discovery_result = '{"error_code":"network_timeout"}'
    monkeypatch.setattr(monitor_module.time, 'time', lambda: 1000)
    monkeypatch.setattr(monitor_module.monitor_repository, 'list_monitored_accounts',
                        AsyncMock(return_value=[first, second]))
    monkeypatch.setattr(monitor_module.monitor_repository, 'get_account_snapshot_workload',
                        AsyncMock(return_value={'account-1': {'pending': 4, 'due': 2, 'oldest_due_at': 0}}))
    monkeypatch.setattr(monitor_module.comment_repo, 'account_workload', lambda *args: {
        'account-1': {'pending': 9, 'due': 3, 'oldest_due_at': 7200}})
    monkeypatch.setattr(monitor_module.comment_service, 'source', lambda: 'isolated-source')
    monkeypatch.setattr(monitor_module.topic_repo, 'scheduler_summary', lambda *args: {
        'active': 2, 'backfill_pending': 1, 'queued': 1, 'running': 0})
    workload = await service.get_account_workload()
    assert workload['snapshot_slice_limit'] == 3 and workload['discovery_slices_per_cycle'] == 1
    assert workload['topics']['active'] == 2
    assert workload['accounts'][0]['snapshots_due'] == 2
    assert workload['accounts'][0]['comments_pending'] == 9
    assert workload['accounts'][0]['oldest_comment_due_seconds'] == 7200
    assert workload['accounts'][1]['last_error'] == 'network_timeout'
    assert workload['accounts'][1]['enabled'] is False
    assert 'account-1' not in repr(workload) and 'account-2' not in repr(workload)


@pytest.mark.asyncio
async def test_topic_live_search_yields_and_resumes_saved_keyword_cursor(monkeypatch):
    monkeypatch.setattr(topic_service.time, 'time', lambda: 1000)
    task = {'id': 'topic', 'keywords': [f'k{i}' for i in range(10)], 'max_pages': 5,
            'start_at': 1, 'end_at': 5000, 'backfill': {'status': 'complete', 'keywords': []},
            'live_checkpoint': None}
    class Client:
        def __init__(self):self.calls=[]
        async def search_info_by_keyword(self, keyword, offset, **kwargs):
            self.calls.append((keyword, offset))
            return {'status_code': 0, 'data': [], 'has_more': True, 'cursor': offset + 1}
    client = Client()
    works, summary = await topic_service.fetch(task, SimpleNamespace(_client=client), lambda: False)
    assert works == [] and len(client.calls) == topic_service.TOPIC_PAGE_SLICE_LIMIT
    assert summary['live_checkpoint']['keywords'][0]['pages'] == 4
    assert summary['live_checkpoint']['keywords'][0]['offset'] == 4
    resumed = task | {'live_checkpoint': summary['live_checkpoint']}
    client = Client()
    _, next_summary = await topic_service.fetch(resumed, SimpleNamespace(_client=client), lambda: False)
    assert client.calls[0] == ('k0', 4)
    assert len(client.calls) == topic_service.TOPIC_PAGE_SLICE_LIMIT
    assert next_summary['live_checkpoint']['keywords'][0]['complete']
    assert next_summary['live_checkpoint']['keywords'][1]['offset'] == 3


def test_topic_live_checkpoint_is_persisted_without_schema_change(tmp_path):
    source = tmp_path / 'source.db'
    with sqlite3.connect(source) as db:db.execute("CREATE TABLE original(value TEXT)")
    task = topic_repo.create(source, {'name':'topic','keywords':['one'],'start_at':1,'end_at':9999999999,
        'interval_minutes':60,'max_pages':5,'enabled':True})
    before = source.read_bytes()
    job = topic_repo.claim(source, task['id'], manual=True)
    checkpoint = {'version':1,'cutoff':10,'keywords':[{'keyword':'one','offset':4,'search_id':'','pages':4,'complete':False}]}
    topic_repo.finish(source, job, [], {'stage':'monitoring','observed_until':10,'live_checkpoint':checkpoint})
    saved = topic_repo.read(source, task['id'])
    assert saved['live_checkpoint'] == checkpoint and topic_repo.collection_interval(saved) == 65
    assert source.read_bytes() == before
    with topic_repo.connection(source) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'


@pytest.mark.asyncio
async def test_snapshot_workload_query_groups_real_isolated_rows(tmp_path, monkeypatch):
    source = tmp_path / 'monitor.db'
    monkeypatch.setitem(db_session.sqlite_db_config, 'db_path', str(source))
    monkeypatch.setattr(db_session, '_engines', {})
    await db_session.create_tables('sqlite')
    try:
        first = await monitor_repository.upsert_monitored_account('one', display_name='First')
        await monitor_repository.upsert_monitored_account('two', display_name='Second')
        now = int(time.time())
        post, _ = await monitor_repository.upsert_post(aweme_id='101', sec_user_id='one', title='title', desc='',
            create_time=now-30, canonical_url='https://www.douyin.com/video/101')
        other, _ = await monitor_repository.upsert_post(aweme_id='201', sec_user_id='two', title='title', desc='',
            create_time=now-30, canonical_url='https://www.douyin.com/video/201')
        await monitor_repository.create_snapshot_jobs(post, stages=[('due', 0), ('future', 3600)])
        await monitor_repository.create_snapshot_jobs(other, stages=[('due', 0)])
        workload = await monitor_repository.get_account_snapshot_workload(now)
        assert workload['one']['pending'] == 2 and workload['one']['due'] == 1
        assert workload['two']['pending'] == 1 and workload['two']['due'] == 1
        assert await monitor_repository.list_due_jobs(now=now, limit=2, fair_accounts=True)
    finally:
        for engine in db_session._engines.values():await engine.dispose()
        db_session._engines.clear()
