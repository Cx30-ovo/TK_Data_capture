"""All visible comments and replies, paginated in durable, fair time slices."""
import asyncio
import time
from pydantic import BaseModel, ConfigDict, Field
from config.db_config import sqlite_db_config
from database import monitor_comments_repository as repo
from tools.collection_errors import classify_collection_error
from tools.douyin_browser_coordinator import CollectionStoppedError
from tools.user_hash import anonymize_user_id, mask_nickname


class CommentPolicy(BaseModel):
    model_config=ConfigDict(extra='forbid')
    enabled:bool=False
    include_replies:bool=True
    # Accept legacy clients without enforcing or persisting their old count caps.
    max_comments:int|None=Field(default=None,ge=0,exclude=True)
    max_replies:int|None=Field(default=None,ge=0,exclude=True)


def source():return sqlite_db_config['db_path']


async def wait_between_requests(fetcher):
    for _ in range(10):
        if fetcher.should_stop():raise CollectionStoppedError('评论采集已暂停')
        await asyncio.sleep(.5)


def normalize(raw,ident,parent):
    cid=str(raw.get('cid') or '')
    if not cid.isdigit() or not isinstance(raw.get('text'),str):raise ValueError('评论字段不完整')
    if raw.get('aweme_id') and str(raw['aweme_id'])!=ident:raise ValueError('评论作品身份不匹配')
    user=raw.get('user') or {}
    def count(v):
        try:return max(0,int(v or 0))
        except (ValueError,TypeError):return 0
    return {'comment_id':cid,'parent_comment_id':parent,'content':raw['text'],
            'nickname':mask_nickname(user.get('nickname')),'creator_hash':anonymize_user_id(user.get('uid')),
            'create_time':count(raw.get('create_time')),'like_count':count(raw.get('digg_count')),
            'reply_count':count(raw.get('reply_comment_total')),'captured_at':int(time.time())}


class CommentCollector:
    def __init__(self,fetcher,policy,key,previous):
        self.fetcher=fetcher;self.policy=policy;self.key=key;self.requests=0
        checkpoint=previous.get('checkpoint',{})
        self.checkpoint=(dict(checkpoint) if checkpoint.get('version')==1 and previous.get('state')!='completed'
                         else {'version':1,'generation':previous.get('refresh_generation',0),'root_cursor':0,'roots_done':False,'reply_after':'',
                               'reply_parent':'','reply_cursor':0,'replies_done':False})

    def check(self):
        if self.fetcher.should_stop():raise CollectionStoppedError('评论采集已暂停')

    async def page(self,ident,parent,cursor):
        self.check()
        # A request budget yields the browser lease, never discards remaining pages.
        if self.requests>=10:return None
        # Shared account/topic browser lease is already held by the caller.
        # Pace every request and poll the existing stop flag during the delay.
        await wait_between_requests(self.fetcher)
        current=await asyncio.to_thread(repo.policy,source(),self.key)
        if not current['enabled'] or parent and not current['include_replies']:
            raise CollectionStoppedError('该账号评论采集已关闭')
        self.requests+=1
        client=self.fetcher._client
        async with asyncio.timeout(30):
            response=await (client.get_sub_comments(ident,parent,cursor) if parent else client.get_aweme_comments(ident,cursor))
        if not isinstance(response,dict):raise ValueError('评论响应无效')
        code=response.get('status_code',0)
        if code in (403,429,8,9):raise RuntimeError('评论接口风控')
        if code!=0:raise ValueError('评论接口返回非成功状态')
        comments=response.get('comments')
        if comments is None and response.get('total')==0 and not response.get('has_more'):comments=[]
        if not isinstance(comments,list):raise ValueError('评论响应缺少列表，不视为零评论')
        if response.get('has_more') not in (False,True,0,1):raise ValueError('评论响应缺少分页状态')
        return response,comments

    async def save_page(self,ident,rows,checkpoint):
        # Don't let cancellation split saved rows from the cursor or race finalization.
        write=asyncio.create_task(asyncio.to_thread(repo.finish,source(),ident,rows,
            {'state':'running','checkpoint':checkpoint,'requests':self.requests}))
        try:await asyncio.shield(write)
        except asyncio.CancelledError:
            await write;self.checkpoint=checkpoint
            raise
        self.checkpoint=checkpoint

    async def collect_page(self,ident,parent,cursor):
        result=await self.page(ident,parent,cursor)
        if result is None:return False
        response,comments=result;rows={}
        for raw in comments:
            if not isinstance(raw,dict):raise ValueError('评论响应字段无效')
            item=normalize(raw,ident,parent);rows[item['comment_id']]=item
        more=bool(response['has_more']);next_cursor=response.get('cursor')
        if more and (not comments or type(next_cursor) is not int or next_cursor<=cursor):
            raise ValueError('评论分页未推进，不标记完成')
        checkpoint=dict(self.checkpoint)
        if not parent:
            checkpoint.update(root_cursor=next_cursor if more else cursor,roots_done=not more)
        elif more:checkpoint.update(reply_parent=parent,reply_cursor=next_cursor)
        else:checkpoint.update(reply_after=parent,reply_parent='',reply_cursor=0)
        await self.save_page(ident,list(rows.values()),checkpoint)
        return True

    async def summary(self,ident,state,failure=None):
        message=('已遍历本轮平台可见主评论及子评论' if self.policy['include_replies'] else '已遍历本轮主评论；子评论采集已关闭') if state=='completed' else '进度已保存，等待自动续采'
        result={'state':state,'limited':False,'continuation':state!='completed','checkpoint':dict(self.checkpoint),
                'requests':self.requests,'error_code':None,'message':message,
                **await asyncio.to_thread(repo.counts,source(),ident)}
        if failure:result.update(**{k:v for k,v in classify_collection_error(failure).as_dict().items() if k in ('error_code','message')})
        return result

    async def run(self,ident):
        failure=None
        try:
            while not self.checkpoint['roots_done']:
                if not await self.collect_page(ident,'',self.checkpoint['root_cursor']):break
            while self.checkpoint['roots_done'] and self.policy['include_replies'] and not self.checkpoint['replies_done']:
                self.check()
                parent=self.checkpoint['reply_parent'] or await asyncio.to_thread(repo.next_parent,source(),ident,self.checkpoint['reply_after'])
                if not parent:
                    await self.save_page(ident,[],dict(self.checkpoint,replies_done=True));break
                # Check every root, even if an earlier counter advertised zero replies.
                if not await self.collect_page(ident,parent,self.checkpoint['reply_cursor']):break
        except Exception as exc:failure=exc
        complete=self.checkpoint['roots_done'] and (not self.policy['include_replies'] or self.checkpoint['replies_done'])
        return await self.summary(ident,'completed' if complete and not failure else 'partial',failure),failure


async def close_cancelled(ident):
    previous=await asyncio.to_thread(repo.progress,source(),ident)
    await asyncio.to_thread(repo.finish,source(),ident,[],previous|{'state':'partial','continuation':True,
        'error_code':'user_stop','message':'服务停止，评论进度已保存'})


async def collect_one(fetcher,key,ident,policy,manual=False,timeout_seconds=120):
    claim=asyncio.create_task(asyncio.to_thread(repo.claim,source(),key,ident,manual))
    try:claimed=await asyncio.shield(claim)
    except asyncio.CancelledError:
        if await claim:
            await asyncio.shield(close_cancelled(ident))
        raise
    if not claimed:return {'state':'deferred','message':'评论采集尚在等待间隔或正在执行'},None
    try:
        previous=await asyncio.to_thread(repo.progress,source(),ident)
        collector=CommentCollector(fetcher,policy,key,previous)
        try:
            async with asyncio.timeout(timeout_seconds):
                summary,failure=await collector.run(ident)
        except TimeoutError:
            # Whole-slice timeout is a cooperative yield, not collection completion.
            summary=await collector.summary(ident,'partial');failure=None
        write=asyncio.create_task(asyncio.to_thread(repo.finish,source(),ident,[],summary))
        try:summary=await asyncio.shield(write)
        except asyncio.CancelledError:
            await write;raise
        return summary,failure
    except asyncio.CancelledError:
        await asyncio.shield(close_cancelled(ident))
        raise
