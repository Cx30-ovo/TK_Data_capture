"""Topic search acceptance on isolated databases, mocked platform only."""
import asyncio
import copy
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from api.services import topic_monitor_service as svc
from api.routers.topic_monitor import router
from database import topic_monitor_repository as repo
from config.db_config import sqlite_db_config

NOW=1793606400


@pytest.fixture(autouse=True)
def no_real_search_wait(monkeypatch):
    monkeypatch.setattr(svc,'wait_between_searches',AsyncMock())


@pytest.fixture
def source(tmp_path,monkeypatch):
    path=tmp_path/'source.db'
    with sqlite3.connect(path) as c:c.execute('CREATE TABLE original(value TEXT)');c.execute("INSERT INTO original VALUES('preserve')")
    monkeypatch.setattr(svc.time,'time',lambda:NOW)
    monkeypatch.setattr(svc.monitor_service,'_paused',False)
    monkeypatch.setattr(svc.monitor_service,'_risk_control_cooldown_remaining',lambda:0)
    monkeypatch.setattr(svc.monitor_service,'_crawler_is_busy',lambda:False)
    monkeypatch.setattr(svc.monitor_service,'_lock',asyncio.Lock())
    monkeypatch.setitem(sqlite_db_config,'db_path',str(path))
    return path


def config(**kwargs):
    return svc.TopicCreate(name='第39届中国电影金鸡奖',keywords=['金鸡奖','电影金鸡奖'],
        start_at=NOW-7*86400,end_at=NOW+7*86400,**kwargs)


def raw(ident='123',**kwargs):
    return {'aweme_id':ident,'desc':'第39届中国电影金鸡奖揭晓 #金鸡奖 #电影',
        'create_time':NOW-100,'author':{'nickname':'测试媒体','sec_uid':'author'},
        'statistics':{'digg_count':0,'comment_count':2,'collect_count':3,'share_count':4}}|kwargs


class Fetcher:
    def __init__(self,responses):
        self._client=self;self.responses=iter(responses);self.calls=[];self.should_stop=lambda:False
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    async def search_info_by_keyword(self,*args,**kwargs):
        self.calls.append((args,kwargs));value=next(self.responses)
        if isinstance(value,Exception):raise value
        return value


def response(*values,more=False,**kwargs):
    return {'data':[{'aweme_info':v} for v in values],'has_more':more,**kwargs}


@pytest.mark.asyncio
async def test_gets_and_disabled_worker_dont_initialize(source):
    before=source.read_bytes()
    assert not (await svc.listing(source))['items']
    assert not repo.path_for(source).exists() and source.read_bytes()==before
    with pytest.raises(repo.TopicError):await svc.detail(source,'missing')


@pytest.mark.asyncio
async def test_explicit_create_sidecar_only(source):
    before=source.read_bytes();task=await svc.create(source,config())
    assert task['version']==1 and task['keywords']==['金鸡奖','电影金鸡奖']
    assert repo.path_for(source).exists() and source.read_bytes()==before
    with sqlite3.connect(repo.path_for(source)) as c:
        assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert c.execute('PRAGMA foreign_key_check').fetchall()==[]


@pytest.mark.asyncio
async def test_comma_topic_name_splits_keywords_and_preserves_any_match(source):
    config_value=svc.TopicCreate(**(config().model_dump()|{'name':'金鸡奖，金鸡百花奖, 金鸡奖','keywords':['金鸡奖，金鸡百花奖, 金鸡奖']}))
    assert config_value.keywords==['金鸡奖','金鸡百花奖']
    task=await svc.create(source,config_value)
    assert task['keywords']==['金鸡奖','金鸡百花奖']
    work=svc.normalize(raw(desc='金鸡百花奖获奖名单'),task['keywords'],NOW,NOW-1000,NOW+1)
    assert work['matched_keywords']==['金鸡百花奖']


@pytest.mark.asyncio
async def test_legacy_comma_scope_can_pause_without_implicit_keyword_change(source):
    legacy=config().model_dump()|{'keywords':['金鸡奖，金鸡百花奖，']}
    task=repo.create(source,legacy)
    checkpoint=task['backfill']
    paused=await svc.update(source,task['id'],svc.TopicUpdate(**(legacy|{'enabled':False}),expected_version=1))
    assert paused['keywords']==legacy['keywords'] and paused['backfill']==checkpoint
    resumed=await svc.update(source,task['id'],svc.TopicUpdate(**legacy,expected_version=2))
    assert resumed['keywords']==legacy['keywords'] and resumed['backfill']==checkpoint


@pytest.mark.parametrize('change',[{'name':' '},{'keywords':['']},{'keywords':['a'*81]},
    {'start_at':NOW+1,'end_at':NOW},{'start_at':NOW-200*86400,'end_at':NOW},
    {'interval_minutes':1},{'max_pages':6},{'keywords':['a']*11}])
def test_validation(change):
    with pytest.raises(ValidationError):svc.TopicCreate(**(config().model_dump()|change))


@pytest.mark.asyncio
async def test_date_outside_supported_bounds(source):
    c=config().model_dump()|{'start_at':NOW-181*86400,'end_at':NOW-180*86400}
    with pytest.raises(repo.TopicError):await svc.create(source,svc.TopicCreate(**c))


def test_keyword_normalization_and_null_zero():
    assert svc.TopicCreate(**(config().model_dump()|{'keywords':[' #金鸡奖 ','金鸡奖']})).keywords==['金鸡奖']
    work=svc.normalize(raw(statistics={'digg_count':0,'comment_count':None,'share_count':-1,'collect_count':'3'}),['金鸡奖'],NOW,NOW-1000,NOW+1)
    assert work['metrics']=={'liked_count':0,'comment_count':None,'collected_count':None,'share_count':None}
    assert svc.total(work['metrics'])==0 and svc.total({k:None for k in svc.METRICS}) is None


@pytest.mark.parametrize('change',[{'create_time':NOW-900000},{'create_time':NOW+10},{'desc':'无关作品'},
    {'aweme_id':'javascript:bad'},{'create_time':None},{'desc':'金鸡奖'+'x'*10001}])
def test_excluded_inputs(change):
    assert svc.normalize(raw(**change),['金鸡奖'],NOW,NOW-1000,NOW+1) is None


@pytest.mark.asyncio
async def test_collection_dedup_keywords_dates_metrics_and_source_preserved(source):
    task=await svc.create(source,config());before=source.read_bytes()
    fetcher=Fetcher([response(raw(),raw(),raw('999',desc='别的话题'),raw('888',create_time=NOW-900000)),response(raw())])
    result=await svc.collect(source,task['id'],manual=True,fetcher_factory=lambda:fetcher)
    assert result['status']=='completed' and result['saved']==1 and result['filtered']==2
    detail=await svc.detail(source,task['id']);w=detail['items'][0]
    assert w['metrics']['liked_count']==0 and w['interaction_total']==9 and w['growth'] is None
    assert detail['summary']['observation_state']=='数据不足' and len(detail['hot_topics'])==2
    assert detail['runs'][0]['state']=='completed' and source.read_bytes()==before
    assert len(fetcher.calls)==2


@pytest.mark.asyncio
async def test_page_bound_and_has_more_flag(source):
    task=await svc.create(source,config(max_pages=1))
    f=Fetcher([response(raw(),more=True),response(raw(),more=True)])
    result=await svc.collect(source,task['id'],manual=True,fetcher_factory=lambda:f)
    assert result['page_limited'] and result['pages']==2


@pytest.mark.asyncio
async def test_pagination_cursor_and_search_id():
    topic=config().model_dump()|{'keywords':['金鸡奖'],'max_pages':2}
    f=Fetcher([response(raw(),more=True,cursor=15,extra={'logid':'fixture-id'}),response(raw('124'))])
    works,summary=await svc.fetch(topic,f,lambda:False)
    assert len(works)==2 and summary['pages']==2 and not summary['page_limited']
    assert f.calls[1][1]['offset']==15 and f.calls[1][1]['search_id']=='fixture-id'


@pytest.mark.asyncio
async def test_historical_backfill_checkpoints_and_continues_before_future_monitoring(source):
    task=await svc.create(source,svc.TopicCreate(**(config().model_dump()|{'name':'金鸡奖，金鸡百花奖','keywords':['金鸡奖，金鸡百花奖'],'max_pages':1})))
    assert task['keywords']==['金鸡奖','金鸡百花奖']
    first=Fetcher([response(raw('100',desc='金鸡奖'),more=True,cursor=15,extra={'logid':'search-a'}),response()])
    result=await svc.collect(source,task['id'],manual=True,fetcher_factory=lambda:first)
    assert result['status']=='completed' and result['stage']=='backfill' and result['page_limited']
    current=repo.read(source,task['id'])
    assert current['backfill']['status']=='pending'
    assert current['backfill']['keywords'][0]['offset']==15
    assert current['backfill']['keywords'][0]['search_id']=='search-a'
    assert current['backfill']['keywords'][0]['pages']==1 and not current['backfill']['keywords'][0]['complete']
    assert repo.claim(source,task['id']) is None
    monkeypatch_now=NOW+70
    original=svc.time.time
    svc.time.time=lambda:monkeypatch_now
    try:
        second=Fetcher([response(raw('101',desc='金鸡奖'),more=True,cursor=30,extra={'logid':'search-a'})])
        result=await svc.collect(source,task['id'],fetcher_factory=lambda:second)
        assert result['stage']=='backfill' and second.calls[0][1]['offset']==15
        assert second.calls[0][1]['search_id']=='search-a'
        current=repo.read(source,task['id'])
        assert current['backfill']['keywords'][0]['offset']==30
        second_page=Fetcher([response(raw('102',desc='金鸡奖')),response(raw('103',desc='金鸡百花奖'))])
        svc.time.time=lambda:monkeypatch_now+70
        result=await svc.collect(source,task['id'],fetcher_factory=lambda:second_page)
        assert result['stage']=='backfill' and result['backfill_checkpoint']['status']=='complete'
        current=repo.read(source,task['id'])
        assert current['backfill']['status']=='complete'
        assert current['last_monitoring_at'] is None
        assert svc.state(current,monkeypatch_now+70)=='monitoring'
        live=Fetcher([response(raw('104',desc='金鸡奖')),response(raw('105',desc='金鸡百花奖'))])
        result=await svc.collect(source,task['id'],manual=True,fetcher_factory=lambda:live)
        assert result['stage']=='monitoring'
        assert repo.read(source,task['id'])['last_monitoring_at'] is not None
    finally:
        svc.time.time=original


@pytest.mark.asyncio
async def test_backfill_history_window_respects_user_publication_window(source):
    task=await svc.create(source,config())
    fetcher=Fetcher([response(raw('500',create_time=NOW-8*86400),raw('501',create_time=NOW-86400)),response()])
    result=await svc.collect(source,task['id'],manual=True,fetcher_factory=lambda:fetcher)
    assert result['saved']==1
    assert (await svc.detail(source,task['id']))['items'][0]['id']=='501'


@pytest.mark.asyncio
async def test_backfill_safety_cap_does_not_claim_completion(source,monkeypatch):
    task=await svc.create(source,config(max_pages=1))
    monkeypatch.setattr(svc,'BACKFILL_PAGE_LIMIT',1)
    f=Fetcher([response(raw(),more=True,cursor=15)])
    result=await svc.collect(source,task['id'],manual=True,fetcher_factory=lambda:f)
    assert result['page_limited'] and repo.read(source,task['id'])['backfill']['status']=='blocked'
    assert svc.state(repo.read(source,task['id']),NOW)=='backfill_blocked'
    assert (await svc.collect(source,task['id']))['status']=='deferred'


@pytest.mark.asyncio
async def test_backfill_failure_replays_uncommitted_pages_without_losing_checkpoint(source):
    task=await svc.create(source,config())
    checkpoint=task['backfill']
    failing=Fetcher([response(raw(),more=True,cursor=15),RuntimeError('搜索不可用')])
    result=await svc.collect(source,task['id'],fetcher_factory=lambda:failing)
    assert result['status']=='failed'
    assert repo.read(source,task['id'])['backfill']==checkpoint
    assert repo.dataset(source,task['id'])[1]==[]
    retry=Fetcher([response(raw()),response(raw())])
    assert (await svc.collect(source,task['id'],manual=True,fetcher_factory=lambda:retry))['status']=='completed'
    assert retry.calls[0][1]['offset']==0


@pytest.mark.asyncio
async def test_pause_update_keeps_backfill_checkpoint_and_schema(source):
    task=await svc.create(source,config(max_pages=1))
    with sqlite3.connect(repo.path_for(source)) as db:
        before=db.execute('SELECT type,name,sql FROM sqlite_schema ORDER BY type,name').fetchall()
    result=await svc.collect(source,task['id'],fetcher_factory=lambda:Fetcher([
        response(raw(),more=True,cursor=15),response()]))
    checkpoint=repo.read(source,task['id'])['backfill']
    assert result['backfill_checkpoint']==checkpoint
    request=svc.TopicUpdate(**config(max_pages=1,enabled=False).model_dump(),expected_version=1)
    await svc.update(source,task['id'],request)
    assert repo.read(source,task['id'])['backfill']==checkpoint
    assert (await svc.collect(source,task['id']))['status']=='deferred'
    await svc.update(source,task['id'],svc.TopicUpdate(**config(max_pages=1).model_dump(),expected_version=2))
    continued=Fetcher([response(raw('124'))])
    await svc.collect(source,task['id'],manual=True,fetcher_factory=lambda:continued)
    assert continued.calls[0][1]['offset']==15
    assert repo.read(source,task['id'])['backfill']['status']=='complete'
    with sqlite3.connect(repo.path_for(source)) as db:
        assert db.execute('SELECT type,name,sql FROM sqlite_schema ORDER BY type,name').fetchall()==before


@pytest.mark.asyncio
async def test_stalled_backfill_cursor_is_blocked_not_complete(source):
    task=await svc.create(source,config())
    await svc.collect(source,task['id'],fetcher_factory=lambda:Fetcher([response(raw(),more=True,cursor=0)]))
    value=repo.read(source,task['id'])
    assert value['backfill']['status']=='blocked' and '游标' in value['backfill']['reason']
    assert value['backfill']['completed_at'] is None and repo.claim(source,task['id'],manual=True) is None


@pytest.mark.asyncio
async def test_past_only_multiple_pages_finish_before_task_ends(source,monkeypatch):
    request=svc.TopicCreate(**(config(max_pages=1).model_dump()|{'end_at':NOW-1}))
    task=await svc.create(source,request)
    await svc.collect(source,task['id'],fetcher_factory=lambda:Fetcher([
        response(raw(),more=True,cursor=15),response()]))
    assert svc.state(repo.read(source,task['id']),NOW)=='backfill'
    monkeypatch.setattr(svc.time,'time',lambda:NOW+70)
    f=Fetcher([response(raw('124'))])
    await svc.collect(source,task['id'],fetcher_factory=lambda:f)
    assert f.calls[0][1]['offset']==15
    assert svc.state(repo.read(source,task['id']),NOW+70)=='ended'
    assert repo.claim(source,task['id'],manual=True) is None


@pytest.mark.asyncio
async def test_backfill_finishing_after_deadline_still_runs_live_final_sweep(source,monkeypatch):
    request=svc.TopicCreate(**(config().model_dump()|{'end_at':NOW+50}))
    task=await svc.create(source,request)
    monkeypatch.setattr(svc.time,'time',lambda:NOW+100)
    await svc.collect(source,task['id'],fetcher_factory=lambda:Fetcher([response(raw()),response()]))
    current=repo.read(source,task['id'])
    assert current['backfill']['status']=='complete' and current['last_success']>=request.end_at
    assert not repo.window_complete(current) and svc.state(current,NOW+100)=='finalizing'
    monkeypatch.setattr(svc.time,'time',lambda:NOW+170)
    live=Fetcher([response(raw('124',create_time=NOW+10)),response()])
    result=await svc.collect(source,task['id'],fetcher_factory=lambda:live)
    assert result['stage']=='monitoring' and result['saved']==1
    assert svc.state(repo.read(source,task['id']),NOW+170)=='ended'


@pytest.mark.asyncio
async def test_monitoring_crossing_deadline_does_not_skip_final_sweep(source,monkeypatch):
    task=await svc.create(source,svc.TopicCreate(**(config().model_dump()|{'end_at':NOW+100})))
    await svc.collect(source,task['id'],fetcher_factory=lambda:Fetcher([response(),response()]))
    monkeypatch.setattr(svc.time,'time',lambda:NOW+70)
    class CrossDeadline(Fetcher):
        async def search_info_by_keyword(self,*args,**kwargs):
            result=await super().search_info_by_keyword(*args,**kwargs)
            monkeypatch.setattr(svc.time,'time',lambda:NOW+120)
            return result
    await svc.collect(source,task['id'],fetcher_factory=lambda:CrossDeadline([response(),response()]))
    current=repo.read(source,task['id'])
    assert current['last_monitoring_at']==NOW+70 and current['last_success']==NOW+120
    assert not repo.window_complete(current) and svc.state(current,NOW+120)=='finalizing'
    monkeypatch.setattr(svc.time,'time',lambda:NOW+190)
    final=await svc.collect(source,task['id'],manual=True,fetcher_factory=lambda:Fetcher([
        response(raw('901',create_time=NOW+90)),response()]))
    assert final['saved']==1 and repo.window_complete(repo.read(source,task['id']))


@pytest.mark.asyncio
async def test_pause_during_backfill_discards_uncommitted_cursor_and_works(source):
    task=await svc.create(source,config())
    entered=asyncio.Event();release=asyncio.Event()
    class Paused(Fetcher):
        async def search_info_by_keyword(self,*args,**kwargs):
            entered.set();await release.wait()
            return await super().search_info_by_keyword(*args,**kwargs)
    pending=asyncio.create_task(svc.collect(source,task['id'],fetcher_factory=lambda:Paused([
        response(raw(),more=True,cursor=15),response()])))
    try:
        await asyncio.wait_for(entered.wait(),2)
        await svc.update(source,task['id'],svc.TopicUpdate(**config(enabled=False).model_dump(),expected_version=1))
    finally:release.set();result=await pending
    assert result['status']=='failed'
    assert repo.read(source,task['id'])['backfill']==task['backfill']
    assert not repo.dataset(source,task['id'])[1]
    assert not svc.monitor_service._lock.locked()


@pytest.mark.asyncio
async def test_backfill_priority_gets_remain_readonly(source,monkeypatch):
    live=await svc.create(source,config())
    await svc.collect(source,live['id'],fetcher_factory=lambda:Fetcher([response(),response()]))
    pending=await svc.create(source,config())
    seen=[]
    async def observe(source,ident):
        seen.append(ident);return {'status':'completed'}
    monkeypatch.setattr(svc,'collect',observe)
    before=repo.path_for(source).read_bytes()
    await svc.listing(source);await svc.detail(source,pending['id'])
    assert repo.path_for(source).read_bytes()==before
    await svc.tick(source)
    assert seen==[pending['id']]


@pytest.mark.parametrize('value',[{}, {'data':None}, {'data':'invalid'}])
@pytest.mark.asyncio
async def test_bad_response_not_empty_success(source,value):
    task=await svc.create(source,config())
    result=await svc.collect(source,task['id'],manual=True,fetcher_factory=lambda:Fetcher([value]))
    assert result['status']=='failed' and not (await svc.detail(source,task['id']))['total']
    assert repo.read(source,task['id'])['last_success'] is None


@pytest.mark.asyncio
async def test_empty_valid_response_is_empty_not_failure(source):
    task=await svc.create(source,config())
    result=await svc.collect(source,task['id'],manual=True,fetcher_factory=lambda:Fetcher([response(),response()]))
    assert result['status']=='completed' and result['saved']==0
    assert (await svc.detail(source,task['id']))['summary']['interaction_total'] is None


@pytest.mark.asyncio
async def test_pause_and_version_conflict_preserve_data(source):
    task=await svc.create(source,config())
    paused=await svc.update(source,task['id'],svc.TopicUpdate(**config(enabled=False).model_dump(),expected_version=1))
    assert not paused['enabled'] and paused['version']==2
    with pytest.raises(repo.TopicError) as exc:
        await svc.update(source,task['id'],svc.TopicUpdate(**config().model_dump(),expected_version=1))
    assert exc.value.status==409
    with pytest.raises(repo.TopicError):
        repo.update(source,task['id'],2,config().model_dump()|{'keywords':['其他']})
    assert repo.read(source,task['id'])['version']==2


@pytest.mark.asyncio
async def test_global_pause_cooldown_and_browser_busy(source,monkeypatch):
    task=await svc.create(source,config())
    monkeypatch.setattr(svc.monitor_service,'_paused',True)
    assert (await svc.collect(source,task['id']))['status']=='deferred'
    monkeypatch.setattr(svc.monitor_service,'_paused',False)
    monkeypatch.setattr(svc.monitor_service,'_risk_control_cooldown_remaining',lambda:300)
    assert (await svc.collect(source,task['id']))['status']=='deferred'
    monkeypatch.setattr(svc.monitor_service,'_risk_control_cooldown_remaining',lambda:0)
    async with svc.monitor_service._lock:
        assert (await svc.collect(source,task['id']))['status']=='deferred'
    assert not (await svc.detail(source,task['id']))['runs']


@pytest.mark.asyncio
async def test_future_and_final_sweep(source,monkeypatch):
    future=await svc.create(source,svc.TopicCreate(**(config().model_dump()|{'start_at':NOW+100,'end_at':NOW+1000})))
    assert repo.claim(source,future['id']) is None
    past=await svc.create(source,svc.TopicCreate(**(config().model_dump()|{'start_at':NOW-1000,'end_at':NOW-1})))
    result=await svc.collect(source,past['id'],fetcher_factory=lambda:Fetcher([response(),response()]))
    assert result['status']=='completed'
    assert repo.claim(source,past['id'],manual=True) is None
    assert svc.state(repo.read(source,past['id']),NOW)=='ended'


@pytest.mark.asyncio
async def test_single_claim_interval_and_interrupted_recovery(source,monkeypatch):
    task=await svc.create(source,config());job=repo.claim(source,task['id']);assert job
    assert repo.claim(source,task['id'],manual=True) is None
    monkeypatch.setattr(svc.time,'time',lambda:NOW+700)
    assert repo.claim(source,task['id'],manual=True)
    assert any(r['state']=='interrupted' for r in repo.dataset(source,task['id'])[2])
    with pytest.raises(repo.TopicError):repo.finish(source,job,[],{})


@pytest.mark.asyncio
async def test_task_pause_in_flight_discards_new_data(source):
    task=await svc.create(source,config())
    class Pausing(Fetcher):
        async def search_info_by_keyword(self,*a,**k):
            await svc.update(source,task['id'],svc.TopicUpdate(**config(enabled=False).model_dump(),expected_version=1))
            return response(raw())
    result=await svc.collect(source,task['id'],manual=True,fetcher_factory=lambda:Pausing([]))
    assert result['status']=='failed' and repo.dataset(source,task['id'])[1]==[]


@pytest.mark.asyncio
async def test_risk_control_joins_existing_cooldown(source,monkeypatch):
    task=await svc.create(source,config())
    cooldown=AsyncMock();monkeypatch.setattr(svc.monitor_service,'_start_risk_control_cooldown',cooldown)
    result=await svc.collect(source,task['id'],manual=True,fetcher_factory=lambda:Fetcher([RuntimeError('触发风控')]))
    assert result['status']=='failed' and result['error_code']=='risk_control' and cooldown.await_count==1


@pytest.mark.asyncio
async def test_recovery_defers_search_without_claim(source,monkeypatch):
    task=await svc.create(source,config())
    monkeypatch.setattr(svc.monitor_service,'execution_status',lambda:{'paused':False,'recovery':{'pending':True}})
    assert (await svc.collect(source,task['id']))['status']=='deferred'
    assert not (await svc.detail(source,task['id']))['runs']


@pytest.mark.asyncio
async def test_login_failure_uses_existing_recovery(source,monkeypatch):
    task=await svc.create(source,config())
    handler=AsyncMock();monkeypatch.setattr(svc.monitor_service,'_handle_collection_failure',handler)
    result=await svc.collect(source,task['id'],manual=True,fetcher_factory=lambda:Fetcher([RuntimeError('login required')]))
    assert result['status']=='failed' and handler.await_count==1
    assert handler.call_args.args[0].error_code=='login_required' and handler.call_args.args[1]=='topic'


@pytest.mark.asyncio
async def test_keyword_search_is_paced(source):
    task=await svc.create(source,config())
    await svc.collect(source,task['id'],manual=True,fetcher_factory=lambda:Fetcher([response(raw()),response(raw())]))
    assert svc.wait_between_searches.await_count==1


@pytest.mark.asyncio
async def test_observation_readiness_not_limited_by_run_history_page(source,monkeypatch):
    task=await svc.create(source,config())
    for index in range(50):
        stamp=NOW+index*1800;monkeypatch.setattr(svc.time,'time',lambda:stamp)
        job=repo.claim(source,task['id'],manual=True)
        works=[svc.normalize(raw(str(200+j),create_time=stamp-10),['金鸡奖'],stamp,NOW-1000,NOW+7*86400) for j in range(5)]
        repo.finish(source,job,works,{})
    d=await svc.detail(source,task['id'])
    assert len(d['runs'])==20 and d['summary']['observation_state']=='上升'


@pytest.mark.asyncio
async def test_shared_work_keeps_per_topic_keyword_binding(source):
    first=await svc.create(source,config())
    second=await svc.create(source,svc.TopicCreate(**(config().model_dump()|{'keywords':['电影']})))
    for task in (first,second):
        job=repo.claim(source,task['id']);work=svc.normalize(raw(),task['keywords'],NOW,NOW-1000,NOW+1)
        repo.finish(source,job,[work],{})
    assert (await svc.detail(source,first['id']))['items'][0]['matched_keywords']==['金鸡奖','电影金鸡奖']
    assert (await svc.detail(source,second['id']))['items'][0]['matched_keywords']==['电影']


@pytest.fixture
def account_adapter(monkeypatch):
    from api.services import monitor_service as module
    adapter=MagicMock()
    adapter.get_monitored_account=AsyncMock(return_value=SimpleNamespace(id=1,sec_user_id='account-fixture',display_name='验收账号',platform='dy',enabled=True))
    adapter.list_post_ids=AsyncMock(return_value=set())
    adapter.update_account_discovered_at=AsyncMock()
    adapter.record_first_seen_snapshot=AsyncMock()
    adapter.create_snapshot_jobs=AsyncMock(return_value=[])
    adapter.create_alert=AsyncMock()
    adapter.record_account_discovery_result=AsyncMock()
    adapter.upsert_post=AsyncMock(side_effect=lambda **kw:(SimpleNamespace(**kw,first_seen_at=NOW),True))
    monkeypatch.setattr(module,'monitor_repository',adapter)
    monkeypatch.setattr(module.crawler_manager,'add_log',AsyncMock())
    monkeypatch.setattr(svc.monitor_service,'_execution',None)
    return adapter


def account_post():
    return {'aweme_id':'456','sec_user_id':'account-fixture','create_time':NOW-10,
            'canonical_url':'https://www.douyin.com/video/456','title':'账号作品'}


@pytest.mark.asyncio
async def test_account_collects_while_topic_waits_then_topic_continues(source,account_adapter):
    task=await svc.create(source,config());entered=asyncio.Event();release=asyncio.Event()
    class AccountFetcher(Fetcher):
        async def fetch_latest_posts(self,**kwargs):
            entered.set();await release.wait();return [account_post()]
    running=asyncio.create_task(svc.monitor_service.discover_account('account-fixture',fetcher=AccountFetcher([])))
    try:
        await asyncio.wait_for(entered.wait(),2)
        assert (await svc.listing(source))['collector_phase']=='waiting_browser'
        assert (await svc.collect(source,task['id']))['status']=='deferred'
        assert not (await svc.detail(source,task['id']))['runs']
    finally:release.set();result=await running
    assert result['created_posts']==1 and account_adapter.upsert_post.await_count==1
    result=await svc.collect(source,task['id'],manual=True,fetcher_factory=lambda:Fetcher([response(raw()),response(raw())]))
    assert result['status']=='completed' and result['saved']==1
    assert (await svc.detail(source,task['id']))['items'][0]['id']=='123'
    assert account_adapter.upsert_post.call_args.kwargs['aweme_id']=='456'


@pytest.mark.asyncio
async def test_topic_collects_then_account_continues_without_losing_work(source,account_adapter):
    task=await svc.create(source,config());entered=asyncio.Event();release=asyncio.Event()
    class Blocking(Fetcher):
        async def search_info_by_keyword(self,*args,**kwargs):
            entered.set();await release.wait();return response(raw())
    running=asyncio.create_task(svc.collect(source,task['id'],manual=True,fetcher_factory=lambda:Blocking([])))
    try:
        await asyncio.wait_for(entered.wait(),2)
        assert (await svc.listing(source))['collector_phase']=='topic_collecting'
        deferred=await svc.monitor_service.discover_account('account-fixture',fetcher=Fetcher([]))
        assert deferred['error_code']=='browser_busy' and not svc.monitor_service._paused
        account_adapter.upsert_post.assert_not_awaited()
    finally:release.set();result=await running
    assert result['status']=='completed'
    fetcher=Fetcher([]);fetcher.fetch_latest_posts=AsyncMock(return_value=[account_post()])
    account=await svc.monitor_service.discover_account('account-fixture',fetcher=fetcher)
    assert account['created_posts']==1 and account_adapter.upsert_post.await_count==1
    assert (await svc.detail(source,task['id']))['total']==1


@pytest.mark.asyncio
async def test_pausing_one_topic_does_not_pause_account_collection(source,account_adapter):
    task=await svc.create(source,config(enabled=False))
    assert (await svc.collect(source,task['id']))['status']=='deferred'
    fetcher=Fetcher([]);fetcher.fetch_latest_posts=AsyncMock(return_value=[account_post()])
    assert (await svc.monitor_service.discover_account('account-fixture',fetcher=fetcher))['created_posts']==1
    assert not svc.monitor_service._paused and not repo.dataset(source,task['id'])[2]


@pytest.mark.asyncio
async def test_pausing_one_account_does_not_pause_topic_collection(source,account_adapter):
    account_adapter.get_monitored_account.return_value.enabled=False
    result=await svc.monitor_service.discover_account('account-fixture',fetcher=Fetcher([]))
    assert result['error_code']=='account_paused'
    task=await svc.create(source,config())
    assert (await svc.collect(source,task['id'],manual=True,fetcher_factory=lambda:Fetcher([response(raw()),response(raw())])))['status']=='completed'
    assert not svc.monitor_service._paused


@pytest.mark.asyncio
async def test_topic_ticks_are_fair_and_bounded_to_one_round(source,monkeypatch):
    first=await svc.create(source,config());second=await svc.create(source,config())
    seen=[]
    original=svc.collect
    async def isolated(source,ident):
        seen.append(ident)
        return await original(source,ident,fetcher_factory=lambda:Fetcher([response(raw()),response(raw())]))
    monkeypatch.setattr(svc,'collect',isolated)
    assert (await svc.tick(source))['status']=='completed' and len(seen)==1
    assert (await svc.tick(source))['status']=='completed' and len(set(seen))==2
    assert set(seen)=={first['id'],second['id']}


@pytest.mark.asyncio
async def test_runner_leaves_account_poll_window_and_retries_busy_queue(source,monkeypatch):
    monkeypatch.setattr(svc,'tick',AsyncMock(side_effect=[{'status':'completed'},{'status':'deferred'}]))
    sleeper=AsyncMock(side_effect=[None,asyncio.CancelledError()])
    monkeypatch.setattr(svc,'wait_for_poll',sleeper)
    try:
        await svc.start_runner(source)
        with pytest.raises(asyncio.CancelledError):await svc._runner
        assert [call.args[0] for call in sleeper.await_args_list]==[65,15]
    finally:await svc.stop_runner()


@pytest.mark.asyncio
async def test_observations_growth_missing_and_count_decrease(source,monkeypatch):
    task=await svc.create(source,config())
    def add(stamp,stats):
        monkeypatch.setattr(svc.time,'time',lambda:stamp)
        job=repo.claim(source,task['id'],manual=True)
        work=svc.normalize(raw(statistics=stats),['金鸡奖'],stamp,NOW-1000,NOW+10000)
        repo.finish(source,job,[work],{})
    stats={'digg_count':0,'comment_count':2,'collect_count':3,'share_count':4}
    add(NOW,stats);add(NOW+100,stats|{'digg_count':10})
    detail=await svc.detail(source,task['id']);assert detail['items'][0]['growth']==10
    add(NOW+200,stats|{'digg_count':5})
    assert (await svc.detail(source,task['id']))['items'][0]['growth'] is None
    add(NOW+300,{'digg_count':0})
    w=(await svc.detail(source,task['id']))['items'][0]
    assert w['metrics']['comment_count'] is None and not w['metrics_complete'] and w['growth'] is None


@pytest.mark.asyncio
async def test_ranking_pagination_and_missing_counts(source):
    task=await svc.create(source,config());job=repo.claim(source,task['id'])
    works=[svc.normalize(raw(str(i+100),statistics={'digg_count':i}),['金鸡奖'],NOW,NOW-1000,NOW+1) for i in range(12)]
    works.append(svc.normalize(raw('999',statistics={}),['金鸡奖'],NOW,NOW-1000,NOW+1))
    repo.finish(source,job,works,{})
    detail=await svc.detail(source,task['id']);assert detail['total']==13 and detail['items'][0]['metrics']['liked_count']==11
    assert detail['items'][0]['heat_index']==100
    second=await svc.detail(source,task['id'],2)
    assert len(second['items'])==3 and second['items'][-1]['interaction_total'] is None
    with pytest.raises(repo.TopicError):await svc.detail(source,task['id'],sort='invalid')


@pytest.mark.asyncio
async def test_get_detail_no_writes_and_http_contracts(source):
    app=FastAPI();app.include_router(router,prefix='/api')
    before=source.read_bytes()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1') as client:
        assert (await client.get('/api/topic-monitors')).json()['items']==[]
        assert not repo.path_for(source).exists()
        response_value=await client.post('/api/topic-monitors',json=config(enabled=False).model_dump())
        assert response_value.status_code==200;task=response_value.json()
        snapshot=repo.path_for(source).read_bytes()
        assert (await client.get('/api/topic-monitors/'+task['id'])).status_code==200
        assert (await client.get('/api/topic-monitors/missing')).status_code==404
        assert (await client.get('/api/topic-monitors/'+task['id']+'?page=0')).status_code==422
        assert repo.path_for(source).read_bytes()==snapshot
    assert source.read_bytes()==before


@pytest.mark.asyncio
async def test_delete_retains_other_topic_shared_work_and_original_db(source):
    before=source.read_bytes();first=await svc.create(source,config());second=await svc.create(source,config())
    for task in (first,second):
        job=repo.claim(source,task['id'])
        works=[svc.normalize(raw(),task['keywords'],NOW,NOW-1000,NOW+1)]
        if task==first:works.append(svc.normalize(raw('999'),task['keywords'],NOW,NOW-1000,NOW+1))
        repo.finish(source,job,works,{})
    retained=repo.dataset(source,second['id'])
    assert (await svc.delete(source,first['id'],1))['deleted']
    assert repo.dataset(source,second['id'])==retained
    with sqlite3.connect(repo.path_for(source)) as db:
        assert db.execute('SELECT id FROM topic_works').fetchall()==[('123',)]
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
    assert source.read_bytes()==before and not svc.monitor_service._paused
    await svc.delete(source,second['id'],1)
    assert repo.listing(source)==[]
    with sqlite3.connect(repo.path_for(source)) as db:
        for table in ('topic_tasks','topic_works','topic_runs','topic_members','topic_observations'):
            assert db.execute('SELECT count(*) FROM '+table).fetchone()[0]==0


@pytest.mark.asyncio
async def test_delete_conflict_and_missing_are_non_destructive(source):
    task=await svc.create(source,config());before=repo.path_for(source).read_bytes()
    for ident,version,status in [(task['id'],2,409),('missing',1,404)]:
        with pytest.raises(repo.TopicError) as exc:await svc.delete(source,ident,version)
        assert exc.value.status==status
        assert repo.path_for(source).read_bytes()==before


@pytest.mark.asyncio
async def test_delete_in_flight_discards_result_and_releases_lock(source):
    task=await svc.create(source,config());entered=asyncio.Event();release=asyncio.Event()
    class Blocking(Fetcher):
        async def search_info_by_keyword(self,*a,**k):
            entered.set();await release.wait();return response(raw())
    running=asyncio.create_task(svc.collect(source,task['id'],manual=True,fetcher_factory=lambda:Blocking([])))
    try:
        await asyncio.wait_for(entered.wait(),2)
        await svc.delete(source,task['id'],1)
        assert svc._stops[task['id']].is_set()
    finally:release.set();result=await running
    assert result['saved']==0 and repo.listing(source)==[] and not svc.monitor_service._lock.locked()
    assert (await svc.collect(source,task['id']))['status']=='deferred'
    assert not svc.monitor_service._paused


@pytest.mark.asyncio
async def test_delete_between_claim_and_fetch_does_not_open_browser(source,monkeypatch):
    task=await svc.create(source,config())
    claim=repo.claim
    def remove_after_claim(*args,**kwargs):
        job=claim(*args,**kwargs);assert job
        repo.delete(source,task['id'],1)
        return job
    monkeypatch.setattr(repo,'claim',remove_after_claim)
    opened=AsyncMock()
    class NeverOpen(Fetcher):
        async def __aenter__(self):await opened();return self
    result=await svc.collect(source,task['id'],manual=True,fetcher_factory=lambda:NeverOpen([]))
    assert result['status']=='failed' and opened.await_count==0 and repo.listing(source)==[]
    assert not svc.monitor_service._paused and not svc.monitor_service._lock.locked()


@pytest.mark.asyncio
async def test_delete_http_requires_current_version(source):
    app=FastAPI();app.include_router(router,prefix='/api')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1') as client:
        task=(await client.post('/api/topic-monitors',json=config(enabled=False).model_dump())).json()
        path='/api/topic-monitors/'+task['id']
        assert (await client.delete(path)).status_code==422
        assert (await client.delete(path+'?expected_version=2')).status_code==409
        assert (await client.delete(path+'?expected_version=1')).json()['deleted']
        assert (await client.get(path)).status_code==404
        assert (await client.delete(path+'?expected_version=1')).status_code==404


@pytest.mark.asyncio
async def test_new_enabled_task_wakes_idle_worker_without_poll_delay(source,monkeypatch):
    completed=asyncio.Event();original=svc.collect
    async def collect_fixture(source,ident):
        result=await original(source,ident,fetcher_factory=lambda:Fetcher([response(raw()),response(raw())]))
        if result['status']=='completed':completed.set()
        return result
    monkeypatch.setattr(svc,'collect',collect_fixture)
    await svc.start_runner(source)
    try:
        await asyncio.sleep(.05)
        task=await svc.create(source,config())
        await asyncio.wait_for(completed.wait(),2)
        assert repo.read(source,task['id'])['last_success']==NOW
    finally:await svc.stop_runner()


@pytest.mark.asyncio
async def test_paused_creation_does_not_wake_worker(source,monkeypatch):
    wake=asyncio.Event();monkeypatch.setattr(svc,'_wake',wake)
    await svc.create(source,config(enabled=False))
    assert not wake.is_set()
    task=await svc.create(source,config());assert wake.is_set()
    wake.clear()
    await svc.update(source,task['id'],svc.TopicUpdate(**config().model_dump(),expected_version=1))
    assert wake.is_set()


@pytest.mark.asyncio
async def test_expired_running_round_recovers_without_waiting_hour(source,monkeypatch):
    task=await svc.create(source,config());old=repo.claim(source,task['id']);assert old
    monkeypatch.setattr(svc.time,'time',lambda:NOW+601)
    fresh=repo.claim(source,task['id']);assert fresh and fresh['run_id']!=old['run_id']
    assert any(r['state']=='interrupted' for r in repo.dataset(source,task['id'])[2])


@pytest.mark.asyncio
async def test_constructor_failure_finishes_round_and_releases_browser(source):
    task=await svc.create(source,config())
    def bad():raise RuntimeError('constructor failure')
    result=await svc.collect(source,task['id'],manual=True,fetcher_factory=bad)
    assert result['status']=='failed' and not svc.monitor_service._lock.locked()
    assert repo.dataset(source,task['id'])[2][0]['state']=='failed'
    assert task['id'] not in svc._stops and task['id'] not in svc._progress


@pytest.mark.asyncio
async def test_recovery_handler_failure_does_not_leave_running_round(source,monkeypatch):
    task=await svc.create(source,config())
    monkeypatch.setattr(svc.monitor_service,'_handle_collection_failure',AsyncMock(side_effect=RuntimeError('handler failure')))
    with pytest.raises(RuntimeError):
        await svc.collect(source,task['id'],manual=True,fetcher_factory=lambda:Fetcher([RuntimeError('login required')]))
    assert repo.dataset(source,task['id'])[2][0]['state']=='failed'


@pytest.mark.asyncio
async def test_per_topic_status_shows_active_and_stale_rounds(source):
    task=await svc.create(source,config());job=repo.claim(source,task['id'])
    row=(await svc.listing(source))['items'][0]
    assert row['collection']['phase']=='recovering' and row['running_since']==NOW
    svc._progress[task['id']]={'phase':'searching','label':'正在搜索话题作品','pages':1}
    try:assert (await svc.listing(source))['items'][0]['collection']['phase']=='searching'
    finally:svc._progress.pop(task['id'])
    repo.finish(source,job,[],{})
    assert (await svc.listing(source))['items'][0]['collection']['phase']=='waiting_interval'


@pytest.mark.asyncio
async def test_shutdown_during_claim_thread_does_not_leave_running_round(source,monkeypatch):
    import threading
    task=await svc.create(source,config());entered=threading.Event();release=threading.Event();claim=repo.claim
    def slow_claim(*args,**kwargs):
        job=claim(*args,**kwargs);entered.set();assert release.wait(3);return job
    monkeypatch.setattr(repo,'claim',slow_claim)
    running=asyncio.create_task(svc.collect(source,task['id'],fetcher_factory=lambda:Fetcher([])))
    try:
        assert await asyncio.to_thread(entered.wait,2)
        running.cancel()
        await asyncio.sleep(.01)
    finally:release.set()
    with pytest.raises(asyncio.CancelledError):await running
    runs=repo.dataset(source,task['id'])[2]
    assert len(runs)==1 and runs[0]['state']=='failed'
    assert not svc.monitor_service._lock.locked() and task['id'] not in svc._stops


@pytest.mark.asyncio
async def test_interrupted_round_retries_after_service_restart(source):
    task=await svc.create(source,config());job=repo.claim(source,task['id'])
    with repo.connection(source,write=True) as db:
        db.execute("UPDATE topic_runs SET state='interrupted' WHERE id=?",(job['run_id'],))
    assert repo.claim(source,task['id']) is not None
