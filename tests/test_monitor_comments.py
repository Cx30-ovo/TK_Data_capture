"""Comment collection uses isolated SQLite and fake signed clients only."""
import asyncio
import json
import sqlite3
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from pydantic import ValidationError

from api.services import monitor_comments_service as svc
from api.services.monitor_service import MonitorService
from api.routers.monitor import router
from database import db_session
from database import monitor_comments_repository as repo
from database.monitor_repository import monitor_repository as posts


def raw(cid='100',**kw):
    return {'cid':cid,'aweme_id':'123','text':'这是评论正文','create_time':100,'digg_count':12,
            'reply_comment_total':1,'user':{'uid':'private-user','nickname':'真实昵称','sec_uid':'private-sec'}}|kw


def response(*items,more=False,cursor=0):
    return {'comments':list(items),'has_more':more,'cursor':cursor}


class Fetcher:
    def __init__(self,roots=None,replies=None,works=None):
        self._client=SimpleNamespace(get_aweme_comments=AsyncMock(side_effect=roots or [response()]),
                                     get_sub_comments=AsyncMock(side_effect=replies or [response()]))
        self.should_stop=lambda:False;self.works=works or [];self.opened=0
    async def __aenter__(self):self.opened+=1;return self
    async def __aexit__(self,*args):pass
    async def fetch_latest_posts(self,**kw):return self.works


@pytest_asyncio.fixture
async def env(tmp_path,monkeypatch):
    path=tmp_path/'source.db'
    monkeypatch.setitem(db_session.sqlite_db_config,'db_path',str(path))
    monkeypatch.setattr(db_session,'_engines',{})
    monkeypatch.setattr(svc,'source',lambda:str(path))
    monkeypatch.setattr(svc,'wait_between_requests',AsyncMock())
    await db_session.create_tables('sqlite')
    account=await posts.upsert_monitored_account('account-comments',display_name='验收账号')
    model=MonitorService();model._paused=False;model._lock=asyncio.Lock()
    monkeypatch.setattr(model,'_risk_control_cooldown_remaining',lambda:0)
    monkeypatch.setattr(model,'_crawler_is_busy',lambda:False)
    monkeypatch.setattr(model,'_handle_collection_failure',AsyncMock(return_value=1800))
    from api.services import monitor_service as module
    monkeypatch.setattr(module.crawler_manager,'add_log',AsyncMock())
    yield path,account,model
    for engine in db_session._engines.values():await engine.dispose()


async def add_post():
    return (await posts.upsert_post(aweme_id='123',sec_user_id='account-comments',title='测试作品',desc='',
        create_time=int(time.time())-100,canonical_url='https://www.douyin.com/video/123'))[0]


def policy(env,**kw):
    path,account,_=env
    return repo.save_policy(path,account.sec_user_id,svc.CommentPolicy(enabled=True,**kw).model_dump())


@pytest.mark.asyncio
async def test_absent_read_no_sidecar_or_source_writes(env):
    path,account,_=env;before=path.read_bytes()
    assert not repo.policy(path,account.sec_user_id)['enabled']
    assert repo.read(path,'123')['collection'] is None and repo.due(path,account.sec_user_id)==[]
    assert not path.with_name('monitor_comments.db').exists() and before==path.read_bytes()


@pytest.mark.parametrize('kw',[{'max_comments':-1},{'max_replies':-1},{'unexpected':1}])
def test_policy_bounds(kw):
    with pytest.raises(ValidationError):svc.CommentPolicy(**kw)


@pytest.mark.asyncio
async def test_policy_roundtrip_isolated_from_original_schema(env):
    path,account,_=env;before=path.read_bytes()
    p=policy(env)
    assert repo.policy(path,account.sec_user_id)==p
    assert not repo.policy(path,'another-account')['enabled']
    assert path.read_bytes()==before
    with sqlite3.connect(path.with_name('monitor_comments.db')) as db:assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'


@pytest.mark.asyncio
async def test_main_and_replies_parent_relation_and_redaction(env):
    p=policy(env);f=Fetcher([response(raw())],[response(raw('101',text='回复具体内容'))])
    result,failure=await svc.collect_one(f,'account-comments','123',p)
    assert not failure and result['state']=='completed' and result['root_comments']==1 and result['replies']==1
    page=repo.read(env[0],'123');assert page['total_saved']==2 and page['items'][0]['saved_replies']==1
    child=repo.read(env[0],'123',parent='100')['items'][0]
    assert child['content']=='回复具体内容' and child['parent_comment_id']=='100'
    serialized=json.dumps(page,ensure_ascii=False)
    assert 'private-user' not in serialized and 'private-sec' not in serialized and '真实昵称' not in serialized
    assert svc.wait_between_requests.await_count==2


@pytest.mark.asyncio
async def test_legacy_limits_are_ignored_and_full_pages_are_saved(env):
    p=policy(env,max_comments=1,max_replies=1)
    f=Fetcher([response(raw(),raw('102'))],[response(raw('101'),raw('103'),more=True,cursor=20),response(raw('104')),response()])
    result,_=await svc.collect_one(f,'account-comments','123',p)
    assert result['root_comments']==2 and result['replies']==3 and not result['limited']
    assert result['state']=='completed' and repo.read(env[0],'123')['total_saved']==5
    assert 'max_comments' not in p and 'max_replies' not in p


@pytest.mark.asyncio
async def test_dedup_and_root_cursor(env):
    p=policy(env,include_replies=False)
    f=Fetcher([response(raw(),more=True,cursor=20),response(raw(),raw('102'))])
    result,_=await svc.collect_one(f,'account-comments','123',p)
    assert result['root_comments']==2 and not result['limited']
    assert f._client.get_aweme_comments.await_args_list[1].args==('123',20)
    f._client.get_sub_comments.assert_not_awaited()


@pytest.mark.asyncio
async def test_request_budget_is_bounded(env):
    p=policy(env,max_comments=200,include_replies=False)
    f=Fetcher([response(raw(str(100+i)),more=True,cursor=(i+1)*20) for i in range(10)])
    result,_=await svc.collect_one(f,'account-comments','123',p)
    assert result['requests']==10 and result['continuation'] and not result['limited'] and result['state']=='partial'
    assert result['checkpoint']['root_cursor']==200


@pytest.mark.parametrize('bad',[{}, {'comments':'invalid'}, {'comments':None},
    {'status_code':1,'comments':[]},response(raw(aweme_id='999')),response(raw(cid='invalid')),
    response(raw(),more=True,cursor=0),response(more=True,cursor=20)])
@pytest.mark.asyncio
async def test_invalid_data_or_stalled_cursor_not_empty_success(env,bad):
    p=policy(env);result,err=await svc.collect_one(Fetcher([bad]),'account-comments','123',p)
    assert err and result['state']=='partial' and result['error_code']=='invalid_response'


@pytest.mark.parametrize('value',[response(),{'comments':None,'total':0,'has_more':False}])
@pytest.mark.asyncio
async def test_valid_empty_is_not_error(env,value):
    result,err=await svc.collect_one(Fetcher([value]),'account-comments','123',policy(env))
    assert not err and result['state']=='completed' and repo.read(env[0],'123')['total_saved']==0


@pytest.mark.asyncio
async def test_failure_preserves_collected_parent_and_previous_rows(env):
    p=policy(env);result,err=await svc.collect_one(Fetcher([response(raw())],[RuntimeError('http 429 cookie=secret')]),'account-comments','123',p)
    assert err and result['error_code']=='risk_control'
    page=repo.read(env[0],'123');assert page['total']==1
    assert 'secret' not in json.dumps(page) and repo.due(env[0],'account-comments')==[]


@pytest.mark.asyncio
async def test_retry_upserts_comments_without_duplicate_or_deletion(env,monkeypatch):
    p=policy(env,include_replies=False);now=int(time.time())
    await svc.collect_one(Fetcher([response(raw())]),'account-comments','123',p)
    monkeypatch.setattr(repo.time,'time',lambda:now+22000)
    await svc.collect_one(Fetcher([response(raw(text='更新后的评论'))]),'account-comments','123',p)
    page=repo.read(env[0],'123');assert page['total']==1 and page['items'][0]['content']=='更新后的评论'


@pytest.mark.asyncio
async def test_lease_manual_throttle_and_restart_recovery(env,monkeypatch):
    path,account,_=env;now=int(time.time());repo.enqueue(path,account.sec_user_id,['123'])
    assert repo.claim(path,account.sec_user_id,'123')
    assert not repo.claim(path,account.sec_user_id,'123',True)
    assert not repo.claim(path,'other','123')
    monkeypatch.setattr(repo.time,'time',lambda:now+601)
    assert repo.due(path,account.sec_user_id)==['123']
    assert repo.claim(path,account.sec_user_id,'123')
    repo.finish(path,'123',[],{'state':'completed'})
    assert not repo.claim(path,account.sec_user_id,'123',True)
    monkeypatch.setattr(repo.time,'time',lambda:now+662)
    assert repo.claim(path,account.sec_user_id,'123',True)


@pytest.mark.asyncio
async def test_comment_and_reply_pagination(env):
    path,account,_=env;repo.enqueue(path,account.sec_user_id,['123'])
    roots=[svc.normalize(raw(str(i+100)), '123','') for i in range(25)]
    children=[svc.normalize(raw(str(i+200)),'123','100') for i in range(25)]
    repo.finish(path,'123',roots+children,{'state':'completed'})
    assert repo.read(path,'123')['total']==25 and len(repo.read(path,'123')['items'])==20
    assert len(repo.read(path,'123',page=2)['items'])==5
    assert len(repo.read(path,'123',page=2,parent='100')['items'])==5


@pytest.mark.asyncio
async def test_auto_discovery_saves_posts_then_collects_in_same_browser(env):
    path,account,monitor=env;policy(env)
    work={'aweme_id':'123','sec_user_id':account.sec_user_id,'create_time':int(time.time())-30,'title':'新作品',
          'canonical_url':'https://www.douyin.com/video/123'}
    f=Fetcher([response(raw())],[response(raw('101'))],works=[work])
    result=await monitor.discover_account(account.sec_user_id,fetcher=f)
    assert result['created_posts']==1 and result['created_jobs']>0 and f.opened==1
    assert result['comment_collections'][0]['root_comments']==1
    assert repo.read(path,'123')['total_saved']==2 and await posts.get_post('123')


@pytest.mark.asyncio
async def test_comments_off_does_not_request_or_initialize(env):
    path,account,monitor=env
    await monitor.discover_account(account.sec_user_id,fetcher=Fetcher())
    assert not path.with_name('monitor_comments.db').exists()


@pytest.mark.asyncio
async def test_comment_risk_stops_requests_but_new_post_survives(env):
    path,account,monitor=env;policy(env)
    work={'aweme_id':'123','sec_user_id':account.sec_user_id,'create_time':int(time.time())-30,
          'canonical_url':'https://www.douyin.com/video/123'}
    result=await monitor.discover_account(account.sec_user_id,fetcher=Fetcher([{'status_code':429}],works=[work]))
    assert result['status']=='partial' and result['error_code']=='risk_control'
    assert await posts.get_post('123') and result['created_posts']==1
    monitor._handle_collection_failure.assert_awaited_once()


@pytest.mark.parametrize('state',['pause','cooldown','busy','account_paused'])
@pytest.mark.asyncio
async def test_manual_obeys_monitor_boundaries(env,state,monkeypatch):
    _,account,monitor=env;await add_post();policy(env);f=Fetcher()
    if state=='pause':monitor._paused=True
    if state=='cooldown':monkeypatch.setattr(monitor,'_risk_control_cooldown_remaining',lambda:300)
    if state=='busy':await monitor._lock.acquire()
    if state=='account_paused':await posts.update_monitored_account(account.id,enabled=False)
    result=await monitor.collect_post_comments('123',fetcher=f)
    assert result['status'] in ('skipped','deferred') and f.opened==0
    if monitor._lock.locked():monitor._lock.release()


@pytest.mark.asyncio
async def test_api_contract_readonly_get_and_isolated_sidecar_post(env):
    path,account,_=env;await add_post();app=FastAPI();app.include_router(router,prefix='/api')
    before=path.read_bytes()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1') as client:
        url=f'/api/monitor/accounts/{account.id}/comment-policy'
        assert (await client.get(url)).json()['enabled'] is False
        assert (await client.get('/api/monitor/posts/123/comments')).json()['total']==0
        assert not path.with_name('monitor_comments.db').exists()
        assert (await client.put(url,json=svc.CommentPolicy(enabled=True).model_dump())).status_code==200
        assert (await client.put(url,json={'max_comments':-1})).status_code==422
        assert (await client.get('/api/monitor/posts/missing/comments')).status_code==404
        assert (await client.get('/api/monitor/posts/123/comments?page=0')).status_code==422
        assert (await client.get('/api/monitor/posts/123/comments?parent_comment_id=invalid')).status_code==422
        snapshot=path.with_name('monitor_comments.db').read_bytes()
        await client.get(url);await client.get('/api/monitor/posts/123/comments')
        assert path.with_name('monitor_comments.db').read_bytes()==snapshot
    assert path.read_bytes()==before


@pytest.mark.asyncio
async def test_stop_flag_does_not_send_request(env):
    f=Fetcher();f.should_stop=lambda:True
    result,failure=await svc.collect_one(f,'account-comments','123',policy(env))
    assert failure and result['state']=='partial'
    f._client.get_aweme_comments.assert_not_awaited()


@pytest.mark.asyncio
async def test_reply_pagination_and_policy_disable_between_pages(env):
    p=policy(env)
    f=Fetcher([response(raw())],[response(raw('101'),more=True,cursor=20),response(raw('102'))])
    result,failure=await svc.collect_one(f,'account-comments','123',p)
    assert failure is None and result['replies']==2
    assert f._client.get_sub_comments.await_args_list[1].args==('123','100',20)


@pytest.mark.asyncio
async def test_disable_policy_stops_next_request_without_losing_first_page(env):
    p=policy(env);f=Fetcher()
    async def first_page(*args):
        repo.save_policy(env[0],'account-comments',p|{'enabled':False})
        return response(raw(),more=True,cursor=20)
    f._client.get_aweme_comments=AsyncMock(side_effect=first_page)
    result,failure=await svc.collect_one(f,'account-comments','123',p)
    assert failure and result['state']=='partial'
    assert f._client.get_aweme_comments.await_count==1
    assert repo.read(env[0],'123')['total']==1


@pytest.mark.asyncio
async def test_cancel_retains_pages_and_closes_running_state(env):
    p=policy(env);f=Fetcher();entered=asyncio.Event();release=asyncio.Event()
    async def replies(*args):
        entered.set();await release.wait();return response(raw('101'))
    f._client.get_aweme_comments=AsyncMock(return_value=response(raw()))
    f._client.get_sub_comments=AsyncMock(side_effect=replies)
    task=asyncio.create_task(svc.collect_one(f,'account-comments','123',p))
    try:
        await asyncio.wait_for(entered.wait(),2);task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
    finally:release.set()
    data=repo.read(env[0],'123')
    assert data['collection']['state']=='partial' and data['total']==1


@pytest.mark.asyncio
async def test_no_new_work_still_processes_due_comment_queue(env):
    path,account,monitor=env;await add_post();policy(env)
    repo.enqueue(path,account.sec_user_id,['123'])
    result=await monitor.discover_account(account.sec_user_id,fetcher=Fetcher([response(raw())],[response(raw('101'))]))
    assert result['created_posts']==0 and result['comment_collections'][0]['root_comments']==1
    assert repo.read(path,'123')['total_saved']==2


@pytest.mark.asyncio
async def test_more_than_old_root_cap_and_no_text_truncation(env):
    p=policy(env,max_comments=1,include_replies=False)
    roots=[raw(str(1000+i),text='字'*20001 if i==0 else '评论') for i in range(235)]
    result,error=await svc.collect_one(Fetcher([response(*roots)]),'account-comments','123',p)
    assert not error and result['state']=='completed' and result['root_comments']==235
    assert len(repo.read(env[0],'123')['items'][0]['content'])==20001


@pytest.mark.asyncio
async def test_more_than_old_reply_cap_including_zero_advertised_count(env):
    p=policy(env,max_replies=1)
    pages=[response(*[raw(str(1000+i)) for i in range(start,min(start+150,651))],
                    more=start+150<651,cursor=start+150) for start in range(0,651,150)]
    result,error=await svc.collect_one(Fetcher([response(raw(reply_comment_total=0))],pages),'account-comments','123',p)
    assert not error and result['state']=='completed' and result['replies']==651
    assert repo.read(env[0],'123',parent='100')['total']==651


@pytest.mark.asyncio
async def test_root_budget_yields_and_new_collector_resumes_exact_cursor(env,monkeypatch):
    p=policy(env,include_replies=False);now=int(time.time())
    first=Fetcher([response(raw(str(100+i)),more=True,cursor=(i+1)*20) for i in range(10)])
    result,error=await svc.collect_one(first,'account-comments','123',p)
    assert not error and result['continuation'] and repo.due(env[0],'account-comments')==[]
    monkeypatch.setattr(repo.time,'time',lambda:now+61)
    assert repo.due(env[0],'account-comments')==['123']
    second=Fetcher([response(raw('110'),more=True,cursor=220),response(raw('111'))])
    result,error=await svc.collect_one(second,'account-comments','123',p)
    assert second._client.get_aweme_comments.await_args_list[0].args==('123',200)
    assert result['root_comments']==12 and result['state']=='completed' and not error
    assert not result['continuation'] and repo.due(env[0],'account-comments')==[]


@pytest.mark.asyncio
async def test_reply_budget_resumes_parent_and_cursor_without_repeating_roots(env,monkeypatch):
    p=policy(env);now=int(time.time())
    first=Fetcher([response(raw())],[response(raw(str(1000+i)),more=True,cursor=(i+1)*20) for i in range(9)])
    result,error=await svc.collect_one(first,'account-comments','123',p)
    assert not error and result['state']=='partial' and result['checkpoint']['reply_parent']=='100'
    assert result['checkpoint']['reply_cursor']==180
    monkeypatch.setattr(repo.time,'time',lambda:now+61)
    second=Fetcher(replies=[response(raw('1009'),more=True,cursor=200),response(raw('1010'))])
    result,error=await svc.collect_one(second,'account-comments','123',p)
    second._client.get_aweme_comments.assert_not_awaited()
    assert second._client.get_sub_comments.await_args_list[0].args==('123','100',180)
    assert not error and result['state']=='completed' and result['replies']==11


@pytest.mark.asyncio
async def test_cancellation_resumes_last_committed_parent_page(env,monkeypatch):
    p=policy(env);now=int(time.time());entered=asyncio.Event()
    async def hanging(*args):entered.set();await asyncio.Event().wait()
    f=Fetcher([response(raw())],[response(raw('101'),more=True,cursor=20)])
    async def replies(*args):
        if args[-1]==0:return response(raw('101'),more=True,cursor=20)
        return await hanging(*args)
    f._client.get_sub_comments=AsyncMock(side_effect=replies)
    task=asyncio.create_task(svc.collect_one(f,'account-comments','123',p))
    await asyncio.wait_for(entered.wait(),3);task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert repo.progress(env[0],'123')['checkpoint']['reply_cursor']==20
    monkeypatch.setattr(repo.time,'time',lambda:now+1801)
    f=Fetcher(replies=[response(raw('102'))]);result,error=await svc.collect_one(f,'account-comments','123',p)
    f._client.get_aweme_comments.assert_not_awaited()
    assert f._client.get_sub_comments.await_args.args==('123','100',20)
    assert not error and result['state']=='completed' and result['replies']==2


@pytest.mark.asyncio
async def test_slice_timeout_is_continuation_not_six_hour_completion(env,monkeypatch):
    p=policy(env,include_replies=False);now=int(time.time())
    async def pages(ident,cursor):
        if cursor==0:return response(raw(),more=True,cursor=20)
        await asyncio.Event().wait()
    f=Fetcher();f._client.get_aweme_comments=AsyncMock(side_effect=pages)
    result,error=await svc.collect_one(f,'account-comments','123',p,timeout_seconds=.2)
    assert not error and result['state']=='partial' and result['checkpoint']['root_cursor']==20
    assert result['error_code'] is None and repo.read(env[0],'123')['total_saved']==1
    monkeypatch.setattr(repo.time,'time',lambda:now+61)
    assert repo.due(env[0],'account-comments')==['123']


@pytest.mark.asyncio
async def test_failed_page_never_advances_cursor_and_retries_exact_page(env,monkeypatch):
    p=policy(env,include_replies=False);now=int(time.time())
    result,error=await svc.collect_one(Fetcher([response(raw(),more=True,cursor=20),{}]),'account-comments','123',p)
    assert error and result['checkpoint']['root_cursor']==20
    monkeypatch.setattr(repo.time,'time',lambda:now+1801)
    f=Fetcher([response(raw('102'))]);result,error=await svc.collect_one(f,'account-comments','123',p)
    assert f._client.get_aweme_comments.await_args.args==('123',20)
    assert not error and result['root_comments']==2 and result['state']=='completed'


@pytest.mark.asyncio
async def test_page_and_checkpoint_atomic_on_parent_conflict(env):
    path,account,_=env;policy(env);repo.enqueue(path,account.sec_user_id,['123'])
    initial={'state':'partial','checkpoint':{'version':1,'root_cursor':20,'roots_done':False}}
    repo.finish(path,'123',[svc.normalize(raw('101'),'123','100')],initial)
    with pytest.raises(ValueError):
        repo.finish(path,'123',[svc.normalize(raw('102'),'123',''),svc.normalize(raw('101'),'123','')],
                    {'state':'partial','checkpoint':{'root_cursor':40}})
    assert repo.progress(path,'123')==initial and repo.read(path,'123')['total_saved']==1


@pytest.mark.asyncio
async def test_legacy_saved_limits_and_partial_results_backfill_without_migration(env):
    path,account,_=env;before=path.read_bytes();repo.enqueue(path,account.sec_user_id,['123'])
    with repo.connection(path,True) as db:
        db.execute('INSERT INTO policies VALUES(?,?)',(account.sec_user_id,json.dumps({'enabled':True,'include_replies':False,'max_comments':1,'max_replies':0})))
        db.execute("UPDATE collections SET state='partial',payload=?",(json.dumps({'state':'partial','limited':True}),))
        schema_before=list(db.execute('SELECT sql FROM sqlite_schema ORDER BY name'))
    p=repo.policy(path,account.sec_user_id)
    f=Fetcher([response(raw(),raw('102'))]);result,error=await svc.collect_one(f,account.sec_user_id,'123',p)
    assert not error and result['root_comments']==2 and 'max_comments' not in p
    with repo.connection(path) as db:assert list(db.execute('SELECT sql FROM sqlite_schema ORDER BY name'))==schema_before
    assert before==path.read_bytes()


@pytest.mark.asyncio
async def test_enabling_replies_wakes_completed_root_only_work(env,monkeypatch):
    p=policy(env,include_replies=False);now=int(time.time())
    await svc.collect_one(Fetcher([response(raw())]),'account-comments','123',p)
    assert not repo.fully_traversed(env[0],'123')
    p=policy(env,include_replies=True)
    assert repo.due(env[0],'account-comments')==['123']
    monkeypatch.setattr(repo.time,'time',lambda:now+61)
    result,error=await svc.collect_one(Fetcher([response(raw())],[response(raw('101'))]),'account-comments','123',p)
    assert not error and result['replies']==1 and repo.fully_traversed(env[0],'123')


@pytest.mark.asyncio
async def test_cycle_resumes_comments_without_waiting_for_discovery(env,monkeypatch):
    from api.services import monitor_service as module
    path,account,monitor=env;policy(env);await add_post();repo.enqueue(path,account.sec_user_id,['123'])
    account.last_discovered_at=int(time.time())
    monkeypatch.setattr(module.monitor_repository,'mark_overdue_jobs_missed',AsyncMock(return_value=0))
    monkeypatch.setattr(module.monitor_repository,'list_monitored_accounts',AsyncMock(return_value=[account]))
    monkeypatch.setattr(monitor,'run_due_snapshots',AsyncMock())
    monkeypatch.setattr(monitor,'discover_account',AsyncMock())
    monkeypatch.setattr(monitor,'collect_post_comments',AsyncMock())
    await monitor._run_cycle()
    monitor.discover_account.assert_not_awaited()
    monitor.collect_post_comments.assert_awaited_once_with('123',manual=False)
    monitor.run_due_snapshots.assert_awaited_once()


@pytest.mark.asyncio
async def test_due_selection_is_fair_and_excludes_disabled_policy(env):
    path,account,_=env;policy(env);repo.enqueue(path,account.sec_user_id,['123'])
    repo.save_policy(path,'account-two',{'enabled':True,'include_replies':True});repo.enqueue(path,'account-two',['456'])
    repo.finish(path,'123',[],{'state':'partial'})
    assert repo.next_due(path,[account.sec_user_id,'account-two'])=='456'
    repo.save_policy(path,'account-two',{'enabled':False})
    assert repo.next_due(path,[account.sec_user_id,'account-two']) is None
    assert repo.next_due(path,[]) is None


@pytest.mark.asyncio
async def test_pending_old_post_is_not_expired_before_traversal_finishes(env):
    path,account,monitor=env;p=policy(env);await add_post()
    from database.models import DouyinPost
    from sqlalchemy import update
    async with db_session.get_monitor_session() as session:
        await session.execute(update(DouyinPost).where(DouyinPost.aweme_id=='123').values(create_time=int(time.time())-8*86400))
        await session.commit()
    repo.enqueue(path,account.sec_user_id,['123'])
    f=Fetcher([response(raw())],[response(raw('101'))])
    result=await monitor.collect_post_comments('123',fetcher=f,manual=False)
    assert result['state']=='completed' and repo.read(path,'123')['total_saved']==2
    f=Fetcher();result=await monitor.collect_post_comments('123',fetcher=f,manual=False)
    assert result['status']=='skipped' and f.opened==0 and repo.due(path,account.sec_user_id)==[]


async def snapshot_jobs(stages=None):
    await add_post()
    return await posts.create_snapshot_jobs(await posts.get_post('123'),stages=stages or [('comment-test',0)])


@pytest.mark.asyncio
async def test_snapshot_collects_comments_and_replies_in_same_browser(env):
    path,account,monitor=env;policy(env);jobs=await snapshot_jobs()
    f=Fetcher([response(raw())],[response(raw('101'))])
    f.fetch_metrics=AsyncMock(return_value={'liked_count':1,'comment_count':2})
    result=await monitor.run_due_snapshots(fetcher=f)
    assert result['completed']==1 and result['comment_collections'][0]['state']=='completed'
    assert repo.read(path,'123')['total_saved']==2 and f.opened==1
    assert (await posts.get_job(jobs[0].id)).status=='done'


@pytest.mark.asyncio
async def test_snapshot_refreshes_completed_comments_without_waiting_six_hours(env,monkeypatch):
    path,account,monitor=env;p=policy(env,include_replies=False);now=int(time.time())
    await snapshot_jobs()
    await svc.collect_one(Fetcher([response(raw())]),account.sec_user_id,'123',p)
    assert repo.due(path,account.sec_user_id)==[]
    monkeypatch.setattr(repo.time,'time',lambda:now+61)
    f=Fetcher([response(raw(text='更新后的正文'),raw('102'))]);f.fetch_metrics=AsyncMock(return_value={'comment_count':2})
    result=await monitor.run_due_snapshots(fetcher=f)
    assert result['completed']==1 and result['comment_collections'][0]['root_comments']==2
    assert repo.read(path,'123')['items'][0]['content']=='更新后的正文'
    assert repo.progress(path,'123')['checkpoint']['generation']==1


@pytest.mark.asyncio
async def test_snapshot_and_comment_minimum_interval_is_preserved(env):
    path,account,monitor=env;p=policy(env);await snapshot_jobs()
    await svc.collect_one(Fetcher([response(raw())],[response()]),account.sec_user_id,'123',p)
    f=Fetcher();f.fetch_metrics=AsyncMock(return_value={'comment_count':5})
    result=await monitor.run_due_snapshots(fetcher=f)
    assert result['completed']==1 and result['comment_collections'][0]['state']=='deferred'
    f._client.get_aweme_comments.assert_not_awaited()
    assert not repo.fully_traversed(path,'123') # Snapshot refresh remains queued.


@pytest.mark.asyncio
async def test_multiple_snapshots_for_same_post_only_update_comments_once(env):
    path,account,monitor=env;policy(env,include_replies=False)
    await snapshot_jobs([('comment-first',0),('comment-second',1)])
    f=Fetcher([response(raw())]);f.fetch_metrics=AsyncMock(return_value={'comment_count':1})
    result=await monitor.run_due_snapshots(fetcher=f)
    assert result['completed']==2 and len(result['comment_collections'])==1
    f._client.get_aweme_comments.assert_awaited_once()
    assert repo.progress(path,'123')['refresh_generation']==1


@pytest.mark.asyncio
async def test_snapshot_comments_off_never_initializes_sidecar(env):
    path,account,monitor=env;await snapshot_jobs()
    f=Fetcher();f.fetch_metrics=AsyncMock(return_value={'comment_count':99})
    result=await monitor.run_due_snapshots(fetcher=f)
    assert result['completed']==1 and result.get('comment_collections',[])==[]
    assert not path.with_name('monitor_comments.db').exists()
    f._client.get_aweme_comments.assert_not_awaited()


@pytest.mark.parametrize('error',[RuntimeError('评论接口风控'),ValueError('响应不完整')])
@pytest.mark.asyncio
async def test_comment_failure_never_retries_or_loses_successful_snapshot(env,error):
    path,account,monitor=env;policy(env);jobs=await snapshot_jobs()
    f=Fetcher([error]);f.fetch_metrics=AsyncMock(return_value={'comment_count':3})
    result=await monitor.run_due_snapshots(fetcher=f)
    assert result['completed']==1 and result['retried']==0 and result['failed']==0 and result['status']=='partial'
    assert (await posts.get_job(jobs[0].id)).status=='done'
    assert (await posts.get_last_snapshot(sec_user_id=account.sec_user_id)).comment_count==3
    assert repo.progress(path,'123')['state']=='partial'
    if '风控' in str(error):monitor._handle_collection_failure.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_snapshot_does_not_create_comment_refresh(env):
    path,account,monitor=env;policy(env);await snapshot_jobs()
    f=Fetcher();f.fetch_metrics=AsyncMock(side_effect=TimeoutError())
    result=await monitor.run_due_snapshots(fetcher=f)
    assert result['completed']==0 and result['retried']==1 and not result.get('comment_collections')
    assert repo.progress(path,'123')=={}
    f._client.get_aweme_comments.assert_not_awaited()


@pytest.mark.asyncio
async def test_snapshot_refresh_during_partial_collection_preserves_cursor_then_rechecks_newest(env,monkeypatch):
    path,account,_=env;p=policy(env,include_replies=False);now=int(time.time())
    first=Fetcher([response(raw(str(100+i)),more=True,cursor=(i+1)*20) for i in range(10)])
    await svc.collect_one(first,account.sec_user_id,'123',p)
    repo.request_snapshot_refresh(path,account.sec_user_id,'123')
    assert repo.progress(path,'123')['checkpoint']['root_cursor']==200
    monkeypatch.setattr(repo.time,'time',lambda:now+61)
    f=Fetcher([response(raw('110'))]);result,error=await svc.collect_one(f,account.sec_user_id,'123',p)
    assert f._client.get_aweme_comments.await_args.args==('123',200)
    assert not error and result['state']=='partial' and result['checkpoint']['root_cursor']==0
    assert result['checkpoint']['generation']==1 and repo.read(path,'123')['total_saved']==11
    monkeypatch.setattr(repo.time,'time',lambda:now+122)
    f=Fetcher([response(raw('111'))]);result,error=await svc.collect_one(f,account.sec_user_id,'123',p)
    assert f._client.get_aweme_comments.await_args.args==('123',0)
    assert not error and result['state']=='completed' and result['root_comments']==12


@pytest.mark.asyncio
async def test_snapshot_refresh_preserves_error_backoff_and_can_wake_expired_posts(env,monkeypatch):
    path,account,_=env;p=policy(env,include_replies=False);now=int(time.time())
    await svc.collect_one(Fetcher([RuntimeError('评论接口风控')]),account.sec_user_id,'123',p)
    repo.request_snapshot_refresh(path,account.sec_user_id,'123')
    assert repo.due(path,account.sec_user_id)==[]
    f=Fetcher();result,error=await svc.collect_one(f,account.sec_user_id,'123',p)
    assert not error and result['state']=='deferred';f._client.get_aweme_comments.assert_not_awaited()
    monkeypatch.setattr(repo.time,'time',lambda:now+1801)
    await svc.collect_one(Fetcher([response(raw())]),account.sec_user_id,'123',p)
    repo.expire(path,'123');repo.request_snapshot_refresh(path,account.sec_user_id,'123')
    monkeypatch.setattr(repo.time,'time',lambda:now+1862)
    assert repo.due(path,account.sec_user_id)==['123']


@pytest.mark.asyncio
async def test_stopping_snapshot_batch_keeps_refresh_queued_without_comment_request(env):
    path,account,monitor=env;policy(env);jobs=await snapshot_jobs()
    f=Fetcher()
    async def metrics(ident):
        monitor.request_safe_stop()
        return {'comment_count':3}
    f.fetch_metrics=AsyncMock(side_effect=metrics)
    result=await monitor.run_due_snapshots(fetcher=f)
    assert result['completed']==1 and result['status']=='stopped'
    assert result['comment_collections'][0]['state']=='pending'
    assert (await posts.get_job(jobs[0].id)).status=='done'
    assert repo.progress(path,'123')['refresh_generation']==1
    f._client.get_aweme_comments.assert_not_awaited()


@pytest.mark.asyncio
async def test_comment_risk_after_snapshots_leaves_other_posts_queued(env):
    path,account,monitor=env;policy(env);await snapshot_jobs()
    other=(await posts.upsert_post(aweme_id='124',sec_user_id=account.sec_user_id,title='另一个作品',desc='',
        create_time=int(time.time())-100,canonical_url='https://www.douyin.com/video/124'))[0]
    jobs=await posts.create_snapshot_jobs(other,stages=[('comment-test',0)])
    f=Fetcher([RuntimeError('评论接口风控')]);f.fetch_metrics=AsyncMock(return_value={'comment_count':3})
    result=await monitor.run_due_snapshots(fetcher=f)
    assert result['completed']==2 and result['status']=='partial' and result['error_code']=='risk_control'
    assert (await posts.get_job(jobs[0].id)).status=='done'
    assert result['comment_collections'][1]['state']=='pending' and repo.progress(path,'124')['refresh_generation']==1
    f._client.get_aweme_comments.assert_awaited_once()
