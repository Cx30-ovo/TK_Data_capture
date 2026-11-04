"""Interrupted snapshot reconciliation: isolated databases, no platform requests."""
import asyncio
from contextvars import Context
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select, update

from api.services import monitor_service as module
from api.services.monitor_execution import MonitorExecution
from api.services.monitor_service import MonitorService
from database import db_session
from database.models import DouyinMonitorJob, DouyinPost, DouyinPostSnapshot
from database.monitor_repository import SNAPSHOT_ALLOWED_WINDOWS, SNAPSHOT_STAGES, monitor_repository as repo
from tools.douyin_browser_coordinator import DouyinTabLease

BASE = 1_800_000_000


@pytest_asyncio.fixture
async def env(tmp_path, monkeypatch):
    monkeypatch.setitem(db_session.sqlite_db_config, 'db_path', str(tmp_path / 'source.db'))
    monkeypatch.setattr(db_session, '_engines', {})
    monkeypatch.setattr(module.crawler_manager, 'add_log', AsyncMock())
    monkeypatch.setattr(module, 'DouyinTabLease', lambda **kw: DouyinTabLease(tmp_path / 'tab.lock', **kw))
    await db_session.create_tables('sqlite')
    await repo.upsert_monitored_account('recovery-account', display_name='回收测试账号')
    yield tmp_path
    for engine in db_session._engines.values():
        await engine.dispose()


async def running_job(stage='24h', ident='123', attempts=1):
    offset=dict(SNAPSHOT_STAGES).get(stage,86400)
    post, _ = await repo.upsert_post(aweme_id=ident, sec_user_id='recovery-account', title='隔离作品', desc='',
        create_time=BASE-offset, canonical_url=f'https://www.douyin.com/video/{ident}')
    jobs = await repo.create_snapshot_jobs(post, stages=[(stage,offset)])
    job = jobs[0]
    async with db_session.get_monitor_session() as session:
        await session.execute(update(DouyinMonitorJob).where(DouyinMonitorJob.id==job.id).values(
            status='running', started_at=BASE+10, attempts=attempts))
    return await repo.get_job(job.id)


async def rows(model):
    async with db_session.get_monitor_session() as session:
        return [dict(row) for row in (await session.execute(select(model.__table__).order_by(model.id))).mappings()]


@pytest.mark.parametrize('stage', list(SNAPSHOT_ALLOWED_WINDOWS))
@pytest.mark.asyncio
async def test_within_window_requeues_without_changing_schedule_or_attempts(env,stage):
    job=await running_job(stage)
    result=await repo.recover_interrupted_snapshot_jobs(now=BASE+SNAPSHOT_ALLOWED_WINDOWS[stage])
    saved=await repo.get_job(job.id)
    assert result['pending']==1 and sum(result.values())==1
    assert saved.status=='pending' and saved.due_at==BASE and saved.attempts==1
    assert saved.started_at is None and saved.finished_at is None and saved.last_error
    assert await rows(DouyinPostSnapshot)==[]


@pytest.mark.parametrize('stage', list(SNAPSHOT_ALLOWED_WINDOWS))
@pytest.mark.asyncio
async def test_expired_window_misses_without_fabricating_snapshot(env,stage):
    job=await running_job(stage)
    now=BASE+SNAPSHOT_ALLOWED_WINDOWS[stage]+1
    result=await repo.recover_interrupted_snapshot_jobs(now=now)
    saved=await repo.get_job(job.id)
    assert result['missed']==1 and saved.status=='missed' and saved.finished_at==now
    assert saved.started_at==BASE+10 and saved.due_at==BASE and saved.attempts==1
    assert '采集窗口' in saved.miss_reason and await rows(DouyinPostSnapshot)==[]


@pytest.mark.asyncio
async def test_existing_real_snapshot_reconciles_done_without_changing_data(env):
    job=await running_job()
    await repo.record_snapshot(job.id,liked_count=123,comment_count=45,captured_at=BASE+100)
    async with db_session.get_monitor_session() as session:
        await session.execute(update(DouyinMonitorJob).where(DouyinMonitorJob.id==job.id).values(
            status='running',finished_at=None))
    before=await rows(DouyinPostSnapshot)
    result=await repo.recover_interrupted_snapshot_jobs(now=BASE+86400)
    saved=await repo.get_job(job.id)
    assert result['done']==1 and saved.status=='done' and saved.finished_at==BASE+100
    assert before==await rows(DouyinPostSnapshot)


@pytest.mark.asyncio
async def test_only_running_snapshot_jobs_and_selected_ids_change(env):
    jobs=[await running_job(ident=str(123+i)) for i in range(7)]
    async with db_session.get_monitor_session() as session:
        for job,status in zip(jobs[1:6],('pending','done','missed','skipped','failed')):
            await session.execute(update(DouyinMonitorJob).where(DouyinMonitorJob.id==job.id).values(status=status))
        await session.execute(update(DouyinMonitorJob).where(DouyinMonitorJob.id==jobs[6].id).values(job_type='topic'))
    before=await rows(DouyinMonitorJob)
    assert sum((await repo.recover_interrupted_snapshot_jobs(now=BASE+99999,job_ids=[])).values())==0
    result=await repo.recover_interrupted_snapshot_jobs(now=BASE+99999,job_ids=[jobs[0].id])
    after=await rows(DouyinMonitorJob)
    assert result['missed']==1 and after[1:]==before[1:]
    assert sum((await repo.recover_interrupted_snapshot_jobs(now=BASE+99999)).values())==0


@pytest.mark.asyncio
async def test_targeted_recovery_leaves_other_running_jobs_untouched(env):
    first=await running_job();second=await running_job(ident='124')
    before=[r for r in await rows(DouyinMonitorJob) if r['id']==second.id]
    await repo.recover_interrupted_snapshot_jobs(now=BASE+99999,job_ids=[first.id])
    assert before==[r for r in await rows(DouyinMonitorJob) if r['id']==second.id]


@pytest.mark.asyncio
async def test_retry_budget_is_not_reset_by_recovery(env):
    job=await running_job(attempts=3)
    result=await repo.recover_interrupted_snapshot_jobs(now=BASE+100)
    saved=await repo.get_job(job.id)
    assert result['failed']==1 and saved.attempts==3 and saved.status=='failed'


@pytest.mark.asyncio
async def test_unrecognized_stage_is_not_automatically_executed(env):
    job=await running_job(stage='unknown')
    result=await repo.recover_interrupted_snapshot_jobs(now=BASE+100)
    assert result['failed']==1 and (await repo.get_job(job.id)).status=='failed'


@pytest.mark.asyncio
async def test_retry_due_time_cannot_extend_original_observation_window(env):
    job=await running_job()
    async with db_session.get_monitor_session() as session:
        await session.execute(update(DouyinMonitorJob).where(DouyinMonitorJob.id==job.id).values(due_at=BASE+86400))
    result=await repo.recover_interrupted_snapshot_jobs(now=BASE+86400)
    saved=await repo.get_job(job.id)
    assert result['missed']==1 and saved.status=='missed' and saved.due_at==BASE+86400


@pytest.mark.asyncio
async def test_unavailable_post_is_skipped_without_changing_post_or_snapshots(env):
    job=await running_job()
    async with db_session.get_monitor_session() as session:
        await session.execute(update(DouyinPost).where(DouyinPost.aweme_id=='123').values(status='deleted'))
    before=await rows(DouyinPost)
    result=await repo.recover_interrupted_snapshot_jobs(now=BASE+100)
    assert result['skipped']==1 and (await repo.get_job(job.id)).status=='skipped'
    assert before==await rows(DouyinPost) and await rows(DouyinPostSnapshot)==[]


@pytest.mark.asyncio
async def test_start_recovers_before_background_loop_and_only_once(env,monkeypatch):
    service=MonitorService();service._crawler_is_busy=lambda:False
    recovered=AsyncMock(return_value={'pending':1,'missed':0,'done':0,'skipped':0,'failed':0})
    monkeypatch.setattr(repo,'recover_interrupted_snapshot_jobs',recovered)
    monkeypatch.setattr(repo,'reconcile_deleted_post_jobs',AsyncMock(return_value=0))
    async def loop():await asyncio.Event().wait()
    monkeypatch.setattr(service,'_loop',loop)
    await service.start()
    try:
        assert service.is_running and not service._snapshot_recovery_pending
        recovered.assert_awaited_once()
        await service.start();recovered.assert_awaited_once()
        assert await service._recover_interrupted_snapshots()
        recovered.assert_awaited_once()
    finally:await service.stop()


@pytest.mark.asyncio
async def test_cross_process_browser_lease_defers_recovery(env,monkeypatch):
    service=MonitorService();service._crawler_is_busy=lambda:False;service._snapshot_recovery_pending=True
    recovered=AsyncMock(return_value={name:0 for name in ('pending','missed','done','skipped','failed')})
    monkeypatch.setattr(repo,'recover_interrupted_snapshot_jobs',recovered)
    async with DouyinTabLease(env/'tab.lock'):
        # Fresh Context models another owner instead of borrowing the current lease.
        assert not await asyncio.create_task(service._recover_interrupted_snapshots(),context=Context())
    recovered.assert_not_awaited();assert service._snapshot_recovery_pending
    assert await service._recover_interrupted_snapshots()
    recovered.assert_awaited_once()


@pytest.mark.parametrize('busy',['lock','execution','crawler'])
@pytest.mark.asyncio
async def test_live_operations_are_never_reclaimed(env,monkeypatch,busy):
    service=MonitorService();service._crawler_is_busy=lambda:busy=='crawler';service._snapshot_recovery_pending=True
    recovered=AsyncMock();monkeypatch.setattr(repo,'recover_interrupted_snapshot_jobs',recovered)
    if busy=='lock':await service._lock.acquire()
    if busy=='execution':service._execution=MonitorExecution('snapshots')
    try:
        assert not await service._recover_interrupted_snapshots()
        recovered.assert_not_awaited();assert service._snapshot_recovery_pending
    finally:
        if service._lock.locked():service._lock.release()


@pytest.mark.asyncio
async def test_cycle_retries_deferred_recovery_before_any_collection(env,monkeypatch):
    service=MonitorService();service._crawler_is_busy=lambda:False;service._snapshot_recovery_pending=True
    recover=AsyncMock(return_value=False);monkeypatch.setattr(service,'_recover_interrupted_snapshots',recover)
    snapshots=AsyncMock();monkeypatch.setattr(service,'run_due_snapshots',snapshots)
    await service._run_cycle()
    recover.assert_awaited_once();snapshots.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_snapshot_marks_recovery_for_next_cycle(env,monkeypatch):
    import time
    # Use a currently due, still valid job so normal queue rules remain intact.
    await repo.upsert_post(aweme_id='123',sec_user_id='recovery-account',title='中断测试',desc='',
        create_time=int(time.time())-100,canonical_url='https://www.douyin.com/video/123')
    jobs=await repo.create_snapshot_jobs(await repo.get_post('123'),stages=[('1h',0)])
    entered=asyncio.Event()
    class Fetcher:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def fetch_metrics(self,ident):entered.set();await asyncio.Event().wait()
    service=MonitorService();service._crawler_is_busy=lambda:False
    task=asyncio.create_task(service.run_due_snapshots(fetcher=Fetcher()))
    await asyncio.wait_for(entered.wait(),3);task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert service._snapshot_recovery_pending and not service._execution.active
    assert (await repo.get_job(jobs[0].id)).status=='running'
    assert await service._recover_interrupted_snapshots()
    assert (await repo.get_job(jobs[0].id)).status=='pending'
