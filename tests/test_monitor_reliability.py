"""Fault injection only: no real Chrome, production databases or model requests."""

import asyncio
import json
import logging
import hashlib
import sqlite3
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

from api.services import monitor_service as module
from api.services import monitor_comments_service as comments
from api.services import monitor_runtime_state as runtime
from api.services.monitor_service import MonitorService, DouyinMonitorFetcher
from api.services.browser_recovery import BrowserRecovery
from database import monitor_comments_repository as repo
from tools import douyin_cdp_recovery as cdp
from tools import douyin_collection_page as registry
from tools.collection_errors import classify_collection_error, record_collection_error
from tools.douyin_browser_coordinator import DouyinTabLease


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    source = tmp_path / 'source.db'
    monkeypatch.setattr(comments, 'source', lambda: str(source))
    monkeypatch.setattr(module.crawler_manager, 'add_log', AsyncMock())
    monkeypatch.setattr(comments, 'wait_between_requests', AsyncMock())
    monkeypatch.setattr(module, 'monitor_repository', SimpleNamespace(
        get_post=AsyncMock(return_value=SimpleNamespace(status='active',sec_user_id='account',create_time=time.time())),
        get_monitored_account=AsyncMock(return_value=SimpleNamespace(enabled=True,display_name='测试账号',sec_user_id='account'))))
    model = MonitorService(tmp_path / 'runtime.json')
    model._crawler_is_busy = lambda: False
    repo.save_policy(source,'account',{'enabled':True,'include_replies':True})
    repo.enqueue(source,'account',['123','456'])
    return source, model


def test_diagnostics_are_correlated_and_exclude_messages_and_locals(caplog):
    caplog.set_level(logging.WARNING,logger='MediaCrawler')
    try:
        try:
            raise TypeError('secret-cookie https://remote.invalid/private?token=secret-token')
        except TypeError as cause:
            raise RuntimeError('private-password') from cause
    except RuntimeError as exc:
        first=record_collection_error(exc,kind='comments',phase='comments_root')
        second=record_collection_error(exc,kind='comments',phase='other')
    assert first==second and first['phase']=='comments_root'
    assert 'TypeError' in caplog.text and 'RuntimeError' in caplog.text
    assert 'test_monitor_reliability.py' in caplog.text
    assert len(caplog.records)==1
    assert all(secret not in caplog.text for secret in ('secret-cookie','secret-token','private-password','remote.invalid'))


@pytest.mark.asyncio
async def test_connection_timeout_keeps_stage_and_releases_lease(tmp_path,monkeypatch):
    stop=AsyncMock()
    manager=SimpleNamespace(launch_and_connect=AsyncMock(side_effect=lambda *a,**kw: None),cleanup=AsyncMock())
    async def hang(*a,**kw):await asyncio.Event().wait()
    manager.launch_and_connect=hang
    monkeypatch.setattr(module,'async_playwright',lambda:SimpleNamespace(start=AsyncMock(return_value=SimpleNamespace(stop=stop))))
    monkeypatch.setattr(module,'DouYinCrawler',lambda:SimpleNamespace())
    monkeypatch.setattr(module,'CDPBrowserManager',lambda **kw:manager)
    monkeypatch.setattr(module.config,'BROWSER_RECOVERY_TIMEOUT_SECONDS',.01)
    monkeypatch.setattr(module,'DouyinTabLease',lambda **kw:DouyinTabLease(tmp_path/'lease',**kw))
    fetcher=DouyinMonitorFetcher()
    with pytest.raises(TimeoutError) as raised:await fetcher.__aenter__()
    assert classify_collection_error(raised.value).error_code=='browser_connection_timeout'
    assert raised.value.collection_phase=='browser_connect'
    assert fetcher._lease is None
    stop.assert_awaited_once()
    state=BrowserRecovery()
    assert state.observe(classify_collection_error(raised.value))
    assert state.pending and state.reset_page


@pytest.mark.asyncio
async def test_raw_target_recovery_precedes_playwright_attachment(monkeypatch):
    order=[]
    async def recover(port):order.append('raw');return 'registered_target_closed'
    async def attach(*a,**kw):
        order.append('attach')
        raise RuntimeError('CDP disconnected')
    monkeypatch.setattr(cdp,'recover_registered_target',recover)
    monkeypatch.setattr(module,'async_playwright',lambda:SimpleNamespace(start=AsyncMock()))
    monkeypatch.setattr(module,'DouYinCrawler',lambda:SimpleNamespace())
    monkeypatch.setattr(module,'CDPBrowserManager',lambda **kw:SimpleNamespace(_read_recorded_port=lambda:12345,launch_and_connect=attach))
    fetcher=DouyinMonitorFetcher();fetcher.reset_collection_page=True
    with pytest.raises(RuntimeError):await fetcher._open_browser()
    assert order==['raw','attach']


@pytest.fixture
def raw_cdp(tmp_path,monkeypatch):
    monkeypatch.setattr(registry,'_TARGET_FILE',tmp_path/'target.json')
    monkeypatch.setattr(cdp,'DouyinTabLease',lambda **kw:DouyinTabLease(tmp_path/'lease',**kw))
    registry._TARGET_FILE.write_text(json.dumps({'target_id':'owned'}))
    target={'targetId':'owned','type':'page','url':'https://www.douyin.com/'}
    responses=[{'id':1,'result':{'targetInfos':[target,{'targetId':'user','type':'page','url':'https://www.douyin.com/'}]}},
               {'id':2,'result':{'success':True}}]
    ws=MagicMock()
    ws.send=AsyncMock()
    ws.recv=AsyncMock(side_effect=lambda:json.dumps(responses.pop(0)))
    ws.__aenter__=AsyncMock(return_value=ws);ws.__aexit__=AsyncMock(return_value=False)
    connector=MagicMock(return_value=ws)
    monkeypatch.setattr(cdp,'connect',connector)
    real_client=httpx.AsyncClient
    endpoint=['ws://127.0.0.1:12345/devtools/browser/fake']
    def client(**kwargs):
        assert kwargs['trust_env'] is False and kwargs['follow_redirects'] is False
        return real_client(transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'webSocketDebuggerUrl':endpoint[0]})),**kwargs)
    monkeypatch.setattr(cdp.httpx,'AsyncClient',client)
    return target,responses,ws,connector,endpoint


@pytest.mark.asyncio
async def test_raw_recovery_closes_only_owned_target_and_bypasses_proxy(raw_cdp,monkeypatch):
    monkeypatch.setenv('ALL_PROXY','http://unreachable.invalid')
    target,responses,ws,connector,_=raw_cdp
    assert await cdp.recover_registered_target(12345)=='registered_target_closed'
    assert not registry._TARGET_FILE.exists()
    sent=[json.loads(call.args[0]) for call in ws.send.await_args_list]
    assert [item['method'] for item in sent]==['Target.getTargets','Target.closeTarget']
    assert sent[1]['params']=={'targetId':'owned'}
    assert connector.call_args.kwargs['proxy'] is None


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value',[('type','service_worker'),('url','https://douyin.com.attacker.invalid/'),('url','https://unrelated.invalid/')])
async def test_raw_recovery_refuses_target_identity_mismatch(raw_cdp,field,value):
    target,_,ws,_,_=raw_cdp;target[field]=value
    assert await cdp.recover_registered_target(12345)=='target_identity_mismatch'
    assert ws.send.await_count==1 and registry._TARGET_FILE.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize('url',['ws://remote.invalid:12345/devtools/browser/fake','ws://127.0.0.1:9999/devtools/browser/fake',
    'wss://127.0.0.1:12345/devtools/browser/fake','ws://user:password@127.0.0.1:12345/devtools/browser/fake',
    'ws://127.0.0.1:12345/devtools/page/fake'])
async def test_raw_recovery_rejects_untrusted_debugger_endpoint(raw_cdp,url):
    *_,connector,endpoint=raw_cdp;endpoint[0]=url
    with pytest.raises(ValueError):await cdp.recover_registered_target(12345)
    connector.assert_not_called()


@pytest.mark.asyncio
async def test_raw_recovery_timeout_preserves_registry_and_closes_socket(raw_cdp):
    _,_,ws,_,_=raw_cdp
    async def hang():await asyncio.Event().wait()
    ws.recv.side_effect=hang
    with pytest.raises(TimeoutError):await cdp.recover_registered_target(12345,timeout=.01)
    assert registry._TARGET_FILE.exists()
    ws.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
async def test_unregistered_recovery_never_connects(raw_cdp):
    _,_,_,connector,_=raw_cdp
    registry._TARGET_FILE.unlink()
    assert await cdp.recover_registered_target(12345)=='no_registered_target'
    assert await cdp.recover_registered_target(None)=='no_endpoint'
    connector.assert_not_called()


@pytest.mark.asyncio
async def test_comment_entry_failure_is_deferred_and_next_post_can_run(isolated):
    source,model=isolated
    checkpoint={'version':1,'root_cursor':20,'roots_done':False}
    repo.finish(source,'123',[],{'state':'partial','checkpoint':checkpoint,'error_code':None})
    # Explicit manual action permits the already-saved row after its minimum interval.
    with repo.connection(source,True) as db:db.execute('update collections set updated_at=0,next_at=0')
    failing=MagicMock()
    failing.__aenter__=AsyncMock(side_effect=RuntimeError('opaque implementation failure'))
    failing.__aexit__=AsyncMock()
    first=await model.collect_post_comments('123',fetcher=failing,manual=False)
    assert first['error_code']=='unknown' and first['diagnostic_id']
    saved=repo.progress(source,'123')
    assert saved['checkpoint']==checkpoint and saved['failure_count']==1
    assert '123' not in repo.due(source,'account') and repo.next_due(source,['account'])=='456'
    again=await model.collect_post_comments('123',fetcher=failing,manual=False)
    assert again['status']=='deferred' and failing.__aenter__.await_count==1
    working=SimpleNamespace(_client=SimpleNamespace(get_aweme_comments=AsyncMock(return_value={'comments':[],'has_more':False,'cursor':0})),should_stop=lambda:False)
    fetcher=MagicMock();fetcher.__aenter__=AsyncMock(return_value=working);fetcher.__aexit__=AsyncMock()
    result=await model.collect_post_comments('456',fetcher=fetcher,manual=False)
    assert result['state']=='completed'


def test_comment_backoff_grows_is_capped_and_snapshot_cannot_bypass(isolated,monkeypatch):
    source,_=isolated
    monkeypatch.setattr(repo.time,'time',lambda:1000)
    expected=(1800,3600,7200,14400,21600,21600,21600)
    for delay in expected:
        repo.finish(source,'123',[],{'state':'partial','error_code':'unknown'})
        repo.request_snapshot_refresh(source,'account','123')
        with repo.connection(source) as db:assert db.execute("select next_at from collections where aweme_id='123'").fetchone()[0]==1000+delay
    repo.finish(source,'123',[],{'state':'partial','error_code':None})
    assert 'failure_count' not in repo.progress(source,'123')


def test_health_tracks_independent_failures_and_has_no_storage_writes(isolated,monkeypatch):
    _,model=isolated
    monkeypatch.setattr(runtime,'save',MagicMock(side_effect=AssertionError('GET must not write')))
    model._task=SimpleNamespace(done=lambda:False);model._last_cycle_at=time.time()
    model._record_operation_health('comments',{'error_code':'unknown','phase':'comments_root','diagnostic_id':'test'})
    model._record_operation_health('discovery',{'status':'ok'})
    assert model.business_health()['status']=='degraded'
    model._record_operation_health('comments',{'status':'ok'})
    assert model.business_health()['ready']
    model._recovery.observe(classify_collection_error(RuntimeError('CDP disconnected')))
    assert model.business_health()['status']=='recovering'
    assert not model.execution_status()['business_health']['ready']
    model._risk_control_until=time.time()+10800
    assert model.business_health()['status']=='cooldown'
    model.request_safe_stop()
    assert model.business_health()['status']=='paused'


@pytest.mark.asyncio
async def test_readiness_returns_503_while_liveness_remains_independent(isolated,monkeypatch):
    _,model=isolated
    from api.routers import monitor as routes
    monkeypatch.setattr(routes,'monitor_service',model)
    app=FastAPI();app.include_router(routes.router,prefix='/api')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        response=await client.get('/api/monitor/readiness')
        assert response.status_code==503 and response.json()['status']=='stopped'
        model._task=SimpleNamespace(done=lambda:False);model._last_cycle_at=time.time()
        model._record_operation_health('discovery',{'status':'ok'})
        assert (await client.get('/api/monitor/readiness')).status_code==200


def test_runtime_restart_preserves_pause_cooldown_recovery_and_retry(isolated):
    _,model=isolated
    model.prepare_runtime_state()
    model._risk_control_until=time.time()+10800;model._risk_control_failures=3
    model._recovery.observe(classify_collection_error(RuntimeError('CDP disconnected')))
    model._recovery.attempts=6;model._recovery.retry_at=time.time()+900
    model._discovery_retries={'account':{'attempts':3,'until':time.time()+480,'failure':classify_collection_error(TimeoutError())}}
    model.request_safe_stop()
    restored=MonitorService(model._runtime_state_path);restored.prepare_runtime_state()
    assert restored._paused and restored._risk_control_until==model._risk_control_until
    assert restored._risk_control_failures==3 and restored._recovery.attempts==6
    assert restored._recovery.retry_at==model._recovery.retry_at
    assert restored._discovery_retries['account']['failure'].error_code=='network_timeout'
    restored.resume_monitoring()
    assert restored._risk_control_cooldown_remaining()>10000 and restored._recovery.pending


@pytest.mark.parametrize('data',['not-json','[]','{"version":2}', '{"version":1,"paused":false,"cooldown_until":NaN}'])
def test_invalid_runtime_state_pauses_instead_of_bypassing_cooldown(tmp_path,data):
    path=tmp_path/'state.json';path.write_text(data)
    model=MonitorService(path);model.prepare_runtime_state()
    assert model._paused and model._last_failure['error_code']=='runtime_state_invalid'
    assert path.read_text()==data


def test_atomic_state_write_failure_preserves_previous_file(tmp_path,monkeypatch):
    path=tmp_path/'state.json';path.write_text('original')
    monkeypatch.setattr(runtime.os,'replace',MagicMock(side_effect=OSError('disk failure')))
    with pytest.raises(OSError):runtime.save(path,{'version':1})
    assert path.read_text()=='original' and list(tmp_path.glob('*.tmp'))==[]


@pytest.mark.asyncio
async def test_comment_entry_cancellation_preserves_cursor_and_releases_claim(isolated):
    source,model=isolated
    checkpoint={'version':1,'root_cursor':40,'roots_done':False}
    repo.finish(source,'123',[],{'state':'partial','checkpoint':checkpoint})
    with repo.connection(source,True) as db:db.execute('update collections set updated_at=0,next_at=0')
    entered=asyncio.Event()
    async def hang():entered.set();await asyncio.Event().wait()
    fetcher=MagicMock();fetcher.__aenter__=AsyncMock(side_effect=hang);fetcher.__aexit__=AsyncMock()
    task=asyncio.create_task(model.collect_post_comments('123',fetcher=fetcher,manual=False))
    await asyncio.wait_for(entered.wait(),2);task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    saved=repo.progress(source,'123')
    assert saved['checkpoint']==checkpoint and saved['error_code']=='user_stop'
    with repo.connection(source) as db:
        assert db.execute("select state from collections where aweme_id='123'").fetchone()[0]=='partial'


@pytest.mark.asyncio
async def test_comment_failure_and_retry_never_change_source_database(isolated):
    source,model=isolated
    with sqlite3.connect(source) as db:
        db.execute('create table existing_data(id integer primary key,value text)')
        db.execute("insert into existing_data values(1,'unchanged')")
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    with repo.connection(source) as db:
        schema_before=list(db.execute('select type,name,sql from sqlite_schema order by name'))
    fetcher=MagicMock();fetcher.__aenter__=AsyncMock(side_effect=TypeError('private error'));fetcher.__aexit__=AsyncMock()
    await model.collect_post_comments('123',fetcher=fetcher,manual=False)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before
    with repo.connection(source) as db:
        assert list(db.execute('select type,name,sql from sqlite_schema order by name'))==schema_before


@pytest.mark.asyncio
async def test_loop_survives_failure_to_write_an_alert(isolated,monkeypatch):
    _,model=isolated
    model._check_browser_health=AsyncMock();model._recover_browser_if_due=AsyncMock()
    model._run_cycle=AsyncMock(side_effect=[RuntimeError('original error'),None])
    model._create_alert=AsyncMock(side_effect=RuntimeError('database unavailable'))
    calls=0
    async def sleep(_):
        nonlocal calls
        calls+=1
        if calls==2:raise asyncio.CancelledError()
    monkeypatch.setattr(module.asyncio,'sleep',sleep)
    with pytest.raises(asyncio.CancelledError):await model._loop()
    assert model._run_cycle.await_count==2
    assert model._last_success['loop']>=model._health_failures['loop']['at']


def test_runtime_storage_failure_refuses_to_resume(isolated,monkeypatch):
    _,model=isolated;model.prepare_runtime_state()
    monkeypatch.setattr(runtime,'save',MagicMock(side_effect=OSError('disk unavailable')))
    assert model.resume_monitoring()['status']=='error'
    assert model._paused and model._last_failure['error_code']=='runtime_state_write_failed'


def test_runner_os_lock_blocks_duplicate_process_and_releases(tmp_path):
    from tools.run_monitor_service import service_lock
    path=tmp_path/'service.lock'
    script="from tools.run_monitor_service import service_lock; import sys;\ntry:\n with service_lock(sys.argv[1]):print('acquired')\nexcept OSError:\n print('busy')"
    def probe():return subprocess.check_output([sys.executable,'-c',script,str(path)],text=True).strip()
    with service_lock(path):assert probe()=='busy'
    assert probe()=='acquired'


@pytest.mark.asyncio
async def test_raw_recovery_does_not_close_any_target_when_registry_is_stale(raw_cdp):
    target,_,ws,_,_=raw_cdp;target['targetId']='other-page'
    assert await cdp.recover_registered_target(12345)=='target_already_gone'
    assert ws.send.await_count==1


def test_supervisor_template_is_not_installed_and_limits_restart_rate():
    import plistlib
    from pathlib import Path
    data=plistlib.loads(Path('tools/deployment/com.mediacrawler.main.plist.example').read_bytes())
    assert data['KeepAlive'] is True and data['ThrottleInterval']>=30
    assert '__PROJECT_ROOT__' in data['WorkingDirectory']
    assert data['ProgramArguments'][-1].endswith('tools/run_monitor_service.py')
