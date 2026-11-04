"""Keyword collection and observed heat, isolated from account membership."""
import asyncio
import copy
import math
import re
import time
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from database import topic_monitor_repository as repo
from media_platform.douyin.field import SearchSortType, SearchChannelType, PublishTimeType
from tools.collection_errors import classify_collection_error
from tools import utils
from tools.douyin_browser_coordinator import CollectionStoppedError
from .monitor_service import monitor_service, DouyinMonitorFetcher

VERSION='topic-monitor-v0.2.0'
BACKFILL_PAGE_LIMIT=100
METRICS=('liked_count','comment_count','collected_count','share_count')
_runner=None
_stops={}
_progress={}
_wake=None
logger=utils.logger


def wake_runner():
    if _wake is not None:_wake.set()


class TopicCreate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str=Field(min_length=1,max_length=80)
    keywords:list[str]=Field(min_length=1,max_length=10)
    start_at:int=Field(gt=0)
    end_at:int=Field(gt=0)
    interval_minutes:int=Field(default=60,ge=30,le=1440)
    max_pages:int=Field(default=2,ge=1,le=5)
    enabled:bool=True

    @field_validator('name')
    @classmethod
    def name_valid(cls,value):
        if not value.strip():raise ValueError('话题名称不能为空')
        return value.strip()

    @field_validator('keywords')
    @classmethod
    def keywords_valid(cls,values):
        values=list(dict.fromkeys(part.strip().lstrip('#') for value in values for part in re.split(r'[,，\n]+',value) if part.strip()))
        if not values or len(values)>10 or any(not v or len(v)>80 or any(ord(c)<32 for c in v) for v in values):
            raise ValueError('关键词应为1—80字，不含控制字符')
        return values

    @model_validator(mode='after')
    def dates(self):
        if self.start_at>=self.end_at or self.end_at-self.start_at>180*86400:
            raise ValueError('结束时间须晚于开始时间，最长180天')
        return self


class TopicUpdate(TopicCreate):
    expected_version:int=Field(ge=1)

    @field_validator('keywords')
    @classmethod
    def keywords_valid(cls,values):
        # Existing task scope is immutable. Pausing/resuming a legacy task
        # must not silently split its original keyword or reset its cursor.
        if any(not v.strip() or len(v)>80 or any(ord(c)<32 for c in v) for v in values):
            raise ValueError('关键词应为1—80字，不含控制字符')
        return values


async def create(source,request):
    now=int(time.time())
    if request.start_at<now-180*86400 or request.end_at>now+180*86400:
        raise repo.TopicError('监控时间须在过去180天与未来180天范围内')
    result=await asyncio.to_thread(repo.create,source,request.model_dump())
    if request.enabled:wake_runner()
    return result


async def update(source,topic_id,request):
    result=await asyncio.to_thread(repo.update,source,topic_id,request.expected_version,
                                  request.model_dump(exclude={'expected_version'}))
    if topic_id in _stops:_stops[topic_id].set()
    if request.enabled:wake_runner()
    return result


async def delete(source,topic_id,version):
    result=await asyncio.to_thread(repo.delete,source,topic_id,version)
    if topic_id in _stops:_stops[topic_id].set()
    return result


def state(topic,now):
    if not topic['enabled']:return 'paused'
    if now<topic['start_at']:return 'scheduled'
    if topic['backfill']['status']=='blocked':return 'backfill_blocked'
    if topic['backfill']['status']=='pending':return 'backfill'
    if repo.window_complete(topic):return 'ended'
    return 'finalizing' if now>=topic['end_at'] else 'monitoring'


def backfill_status(topic):
    value=topic['backfill']
    return {k:value.get(k) for k in ('status','start_at','end_at','completed_at','reason')}|{
        'completed_keywords':sum(k['complete'] for k in value['keywords']),
        'keyword_count':len(value['keywords']), 'pages':sum(k['pages'] for k in value['keywords'])}


async def listing(source):
    now=int(time.time())
    topics=await asyncio.to_thread(repo.listing,source)
    return {'items':[t|{'backfill':backfill_status(t),'state':state(t,now),'collection':collection_status(t,now)} for t in topics],'server_time':now,
            'worker_running':bool(_runner and not _runner.done()),
            'worker_version':VERSION,
            'collection_paused':monitor_service.execution_status()['paused'],
            'collector_phase':'topic_collecting' if _stops else 'waiting_browser' if monitor_service._lock.locked() else 'ready',
            'retry_after_seconds':monitor_service._risk_control_cooldown_remaining(),'model_requests':0}


def collection_status(topic,now):
    if topic['id'] in _progress:return dict(_progress[topic['id']])
    if not topic['enabled']:return {'phase':'paused','label':'话题已暂停'}
    if now<topic['start_at']:return {'phase':'scheduled','label':'等待发布时间窗口开始','next_at':topic['start_at']}
    execution=monitor_service.execution_status()
    if execution['paused']:return {'phase':'paused','label':'采集总开关已暂停'}
    if monitor_service._risk_control_cooldown_remaining():return {'phase':'cooldown','label':'风控冷却中，等待恢复'}
    if topic.get('running_since'):
        return {'phase':'recovering','label':'上轮未正常结束，等待执行租约到期后恢复','next_at':topic['running_since']+600}
    if state(topic,now)=='ended':return {'phase':'ended','label':'监控窗口已完成'}
    if topic['backfill']['status']=='blocked':return {'phase':'blocked','label':topic['backfill']['reason'] or '历史补采受限，未标记完成'}
    if execution.get('recovery',{}).get('pending'):return {'phase':'waiting_browser','label':'专用浏览器正在恢复'}
    if monitor_service._lock.locked() or monitor_service._crawler_is_busy():return {'phase':'waiting_browser','label':'等待账号采集释放浏览器'}
    interval=repo.collection_interval(topic)
    if topic['last_attempt'] and now<topic['last_attempt']+interval:
        return {'phase':'waiting_interval','label':'历史补采分页已保存，等待续采' if topic['backfill']['status']=='pending' else '等待下次定时采集','next_at':topic['last_attempt']+interval}
    return {'phase':'queued','label':'已加入采集队列，等待首轮采集' if not topic['last_attempt'] else '已加入采集队列'}


def count(value):
    return value if type(value) is int and value>=0 else None


def normalize(raw,keywords,now,start,end):
    ident=str(raw.get('aweme_id') or '')
    published=raw.get('create_time')
    text=raw.get('desc')
    if (not ident.isdigit() or type(published) is not int or not start<=published<min(end,now+1)
            or not isinstance(text,str) or len(text)>10000):return None
    normalized=re.sub(r'\s+','',text).casefold()
    matched=[k for k in keywords if re.sub(r'\s+','',k).casefold() in normalized]
    if not matched:return None
    author=raw.get('author') or {};stats=raw.get('statistics') or {}
    tags=list(dict.fromkeys(re.findall(r'#([^#\s，。！？,!?；;（）()]{1,50})',text)))[:30]
    return {'id':ident,'title':text,'published_at':published,'author':str(author.get('nickname') or '未知账号')[:100],
        'author_id':str(author.get('sec_uid') or author.get('uid') or '')[:255],
        'url':'https://www.douyin.com/video/'+ident,'hashtags':tags,'matched_keywords':matched,
        'metrics':{key:count(stats.get(source)) for key,source in
            zip(METRICS,('digg_count','comment_count','collect_count','share_count'))}}


async def wait_between_searches(stop):
    # Search uses the existing HTTP adapter, so pace it here rather than assume
    # the browser adapter's page interval also applies to keyword requests.
    for _ in range(10):
        if stop():raise CollectionStoppedError('话题监控已暂停')
        await asyncio.sleep(.5)


async def fetch(topic,fetcher,stop):
    works={};pages=0;limited=False;filtered=0
    cutoff=int(time.time())
    checkpoint=copy.deepcopy(topic.get('backfill'))
    historical=checkpoint is not None and checkpoint['status']=='pending'
    entries=checkpoint['keywords'] if historical else [
        {'keyword':keyword,'offset':0,'search_id':'','pages':0,'complete':False} for keyword in topic['keywords']]
    for entry in entries:
        if entry['complete']:continue
        keyword=entry['keyword'];offset=entry['offset'];search_id=entry['search_id']
        for index in range(topic['max_pages']):
            if stop():raise CollectionStoppedError('话题监控已暂停')
            if pages:await wait_between_searches(stop)
            if topic.get('id') in _progress:
                _progress[topic['id']].update(phase='searching',label='正在补采历史作品' if historical else '正在搜索话题作品',keyword_index=topic['keywords'].index(keyword)+1,keyword_count=len(topic['keywords']),pages=pages)
            response=await fetcher._client.search_info_by_keyword(keyword,offset=offset,
                search_channel=SearchChannelType.VIDEO,sort_type=SearchSortType.LATEST,
                publish_time=PublishTimeType.UNLIMITED,search_id=search_id)
            pages+=1
            if topic.get('id') in _progress:_progress[topic['id']]['pages']=pages
            if isinstance(response,dict) and response.get('status_code',0)!=0:
                raise ValueError('搜索返回非成功状态，不将其当作无作品')
            if not isinstance(response,dict) or not isinstance(response.get('data'),list):
                raise ValueError('搜索响应不可用，不将其当作无作品')
            for item in response['data']:
                if not isinstance(item,dict):continue
                raw=item.get('aweme_info')
                if not isinstance(raw,dict):continue
                work=normalize(raw,topic['keywords'],cutoff,topic['start_at'],checkpoint['end_at'] if historical else topic['end_at'])
                if work:works[work['id']]=work
                else:filtered+=1
            entry['pages']+=1
            if not response.get('has_more'):
                entry['complete']=True
                break
            next_offset=response.get('cursor',offset+len(response['data']))
            if type(next_offset) is not int or not offset<next_offset<=10000000:
                limited=True
                if historical:
                    checkpoint.update(status='blocked',reason='平台分页游标未推进，历史补采未完成；需核查后重试')
                break
            extra=response.get('extra')
            search_id=str((extra if isinstance(extra,dict) else {}).get('logid') or search_id)
            offset=next_offset
            entry.update(offset=offset,search_id=search_id)
            if historical and entry['pages']>=BACKFILL_PAGE_LIMIT:
                limited=True
                checkpoint.update(status='blocked',reason='历史补采达到安全页数上限，未宣称完整；需人工核查')
                break
            if index==topic['max_pages']-1:limited=True
        if historical and checkpoint['status']=='blocked':break
    summary={'pages':pages,'page_limited':limited,'filtered':filtered,
        'stage':'backfill' if historical else 'monitoring',
        'observed_until':cutoff,
        'scope':'平台关键词搜索可见且文案字面命中；非全量、非语义事件确认'}
    if historical:
        if all(entry['complete'] for entry in entries):
            checkpoint.update(status='complete',completed_at=cutoff,reason=None)
        summary['backfill_checkpoint']=checkpoint
    return list(works.values()),summary


async def collect(source,topic_id,*,manual=False,fetcher_factory=None):
    # Respect the existing application stop, browser lock and platform cooldown.
    if monitor_service.execution_status()['paused']:
        return {'status':'deferred','reason':'采集总开关已暂停'}
    if monitor_service._risk_control_cooldown_remaining():
        return {'status':'deferred','reason':'风控冷却中，话题搜索同步暂停'}
    if monitor_service.execution_status().get('recovery',{}).get('pending'):
        return {'status':'deferred','reason':'采集浏览器正在恢复，等待下一轮'}
    if monitor_service._lock.locked() or monitor_service._crawler_is_busy():
        return {'status':'deferred','reason':'采集浏览器正在使用，等待下一轮'}
    async with monitor_service._lock:
        claim_task=asyncio.create_task(asyncio.to_thread(repo.claim,source,topic_id,manual=manual))
        try:job=await asyncio.shield(claim_task)
        except asyncio.CancelledError:
            # to_thread keeps committing after its awaiter is cancelled. Join
            # the claim and close any acquired round before shutdown completes.
            job=await claim_task
            if job:await asyncio.shield(asyncio.to_thread(repo.finish,source,job,[],{},'服务停止，领取任务后未开始采集'))
            raise
        except repo.TopicError as exc:
            if exc.status==404:return {'status':'deferred','reason':'话题监控已删除'}
            raise
        if not job:return {'status':'deferred','reason':'未到执行时间、已暂停、已结束或已有任务'}
        event=asyncio.Event();_stops[topic_id]=event
        _progress[topic_id]={'phase':'connecting','label':'正在连接专用浏览器','started_at':int(time.time()),'pages':0}
        stop=lambda:event.is_set() or monitor_service.execution_status()['paused']
        try:
            fetcher=(fetcher_factory or DouyinMonitorFetcher)()
            fetcher.should_stop=stop
            # Deletion may commit between the claim thread completing and this
            # coroutine registering its stop event. Recheck before opening Chrome.
            await asyncio.to_thread(repo.read,source,topic_id)
            if stop():raise CollectionStoppedError('话题监控已停止')
            async with asyncio.timeout(480):
                async with fetcher as active:
                    works,summary=await fetch(job['config'],active,stop)
            if stop():raise CollectionStoppedError('话题监控已暂停')
            result=await asyncio.to_thread(repo.finish,source,job,works,summary)
            return {'status':'failed' if result['error'] else 'completed',**result}
        except asyncio.CancelledError:
            await asyncio.shield(asyncio.to_thread(repo.finish,source,job,[],{},'服务停止，本轮未完成'))
            raise
        except Exception as exc:
            failure=classify_collection_error(exc)
            # Persist the failed outcome before recovery/logging side effects;
            # failure handlers must not leave a dangling running lease.
            result=await asyncio.to_thread(repo.finish,source,job,[],{},failure.message)
            if failure.error_code in ('risk_control','login_required','tab_changed','browser_disconnected'):
                await monitor_service._handle_collection_failure(failure,'topic')
            logger.warning('topic_collection_failed category=%s exception_type=%s',failure.error_code,type(exc).__name__)
            return {'status':'failed','error_code':failure.error_code,**result}
        finally:
            _stops.pop(topic_id,None)
            _progress.pop(topic_id,None)


def total(metrics):
    present=[v for v in metrics.values() if v is not None]
    return sum(present) if present else None


async def detail(source,topic_id,page=1,sort='heat'):
    topic,works,runs=await asyncio.to_thread(repo.dataset,source,topic_id)
    now=int(time.time());tags={};trend={};valid=[];growth_total=0;growth_available=0
    for work in works:
        if not topic['start_at']<=work['published_at']<topic['end_at']:continue
        normalized=re.sub(r'\s+','',work['title']).casefold()
        work['matched_keywords']=[k for k in topic['keywords'] if re.sub(r'\s+','',k).casefold() in normalized]
        observations=work.pop('observations')
        last=observations[-1] if observations else None
        work['metrics']=last['metrics'] if last else {k:None for k in METRICS}
        work['captured_at']=last['captured_at'] if last else None
        work['interaction_total']=total(work['metrics'])
        work['metrics_complete']=all(v is not None for v in work['metrics'].values())
        work['growth']=None
        if len(observations)>1:
            previous=next((r for r in reversed(observations[:-1]) if r['captured_at']<last['captured_at']),None)
            if previous and all(previous['metrics'].get(k) is not None and work['metrics'][k] is not None
                                and work['metrics'][k]>=previous['metrics'][k] for k in METRICS):
                work['growth']=sum(work['metrics'][k]-previous['metrics'][k] for k in METRICS)
                work['growth_since']=previous['captured_at'];growth_total+=work['growth'];growth_available+=1
        day=datetime.fromtimestamp(work['published_at'],__import__('zoneinfo').ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d')
        trend[day]=trend.get(day,0)+1
        for tag in work['hashtags']:
            bucket=tags.setdefault(tag,{'name':tag,'works':0,'interaction_total':0,'observed_works':0})
            bucket['works']+=1
            if work['interaction_total'] is not None:
                bucket['interaction_total']+=work['interaction_total'];bucket['observed_works']+=1
        valid.append(work)
    if sort not in ('heat','recent','growth'):raise repo.TopicError('作品排序无效')
    key={'heat':'interaction_total','recent':'published_at','growth':'growth'}[sort]
    valid.sort(key=lambda w:(w.get(key) is not None,w.get(key) or 0,w['published_at'],w['id']),reverse=True)
    maximum=max((w['interaction_total'] or 0 for w in valid),default=0)
    for work in valid:
        work['heat_index']=round(100*math.log1p(work['interaction_total'])/math.log1p(maximum),1) if maximum and work['interaction_total'] is not None else 0 if work['interaction_total']==0 else None
    hot_tags=sorted(tags.values(),key=lambda v:(-v['interaction_total'],-v['works'],v['name']))[:15]
    for tag in hot_tags:
        if not tag['observed_works']:tag['interaction_total']=None
    recent=sum(w['published_at']>=now-86400 for w in valid)
    prior=sum(now-172800<=w['published_at']<now-86400 for w in valid)
    history=topic.pop('successful_observation_window')
    status='数据不足'
    if history['rounds']>=2 and history['last_at']-history['first_at']>=86400 and len(valid)>=5:
        status='上升' if recent>=max(3,prior*1.5) else '退潮' if prior>=3 and recent<prior*.5 else '持续发酵'
    return {'version':VERSION,'topic':topic|{'backfill':backfill_status(topic),'state':state(topic,now)},'total':len(valid),'page':page,'page_size':10,
        'items':valid[(page-1)*10:page*10],'runs':runs,'hot_topics':hot_tags,
        'trend':[{'date':d,'works':n} for d,n in sorted(trend.items())],
        'summary':{'works':len(valid),'authors':len({w['author_id'] for w in valid if w['author_id']}),
            'observed_works':sum(w['interaction_total'] is not None for w in valid),
            'interaction_total':sum(w['interaction_total'] or 0 for w in valid) if any(w['interaction_total'] is not None for w in valid) else None,'new_24h':recent,
            'growth':growth_total if growth_available else None,'growth_works':growth_available,'observation_state':status},
        'model_requests':0,'limitations':['仅本话题搜索采样范围，关键词命中不等于同事件确认，不保证历史完整召回。',
            '热度为点赞+评论+收藏+分享的累计观察值之和及样本内对数归一指数，不是播放量或平台官方热度。',
            '话题排行按已采集文案的#标签分组，不是模型语义聚类；不同作品可能重复转载。',
            '增量仅比较同作品两次有效计数，缺失或回落不补0；各作品观测间隔可能不同，不是统一增长率。',
            '未来窗口只约束后续采集，不能预先取得未发布作品；历史搜索和单轮页数存在平台覆盖限制。']}


async def tick(source):
    # An older, deferred task retains its place. One actual collection per tick
    # leaves browser time for the independently scheduled account monitor.
    topics=await asyncio.to_thread(repo.listing,source)
    topics.sort(key=lambda t:(t['backfill']['status']!='pending',t['last_attempt'] or 0,t['created_at'],t['id']))
    for topic in topics:
        result=await collect(source,topic['id'])
        if result['status']!='deferred':return result
    return {'status':'deferred'}


async def wait_for_poll(delay):
    if delay==65:await asyncio.sleep(delay)
    else:
        try:await asyncio.wait_for(_wake.wait(),timeout=delay)
        except TimeoutError:pass


async def start_runner(source):
    global _runner,_wake
    if _runner and not _runner.done():return
    _wake=asyncio.Event()
    async def loop():
        while True:
            _wake.clear()
            delay=15
            try:
                result=await tick(source)
                # The account monitor polls every 60 seconds. Leave a full
                # poll window after each topic round instead of chaining topics.
                if result['status']!='deferred':delay=65
            except asyncio.CancelledError:raise
            except Exception as exc:
                import traceback
                frames=traceback.extract_tb(exc.__traceback__)
                logger.error('topic_monitor_poll_unavailable exception_type=%s frames=%s',type(exc).__name__,','.join(f'{frame.name}:{frame.lineno}' for frame in frames))
            await wait_for_poll(delay)
    _runner=asyncio.create_task(loop())


async def stop_runner():
    global _runner,_wake
    if _runner:
        _runner.cancel();await asyncio.gather(_runner,return_exceptions=True);_runner=None
    _wake=None
