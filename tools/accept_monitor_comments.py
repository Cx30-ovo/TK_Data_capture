"""Isolated loopback browser acceptance; fake platform, real comment endpoints."""
import asyncio
import hashlib
import json
from pathlib import Path
import socket
import sys
import threading
import time
from urllib.parse import urlsplit
from unittest.mock import AsyncMock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import pytest
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from playwright.async_api import async_playwright,expect


async def main():
    from database import db_session
    from database.monitor_repository import monitor_repository as posts
    from api.routers.monitor import router
    from api.routers import monitor as routes
    from api.services import monitor_comments_service as comments
    from api.services import monitor_service as monitor_module
    from api.services.monitor_service import MonitorService
    from api.main import get_config_options,get_platforms
    from tests.test_monitor_comments import Fetcher,raw,response
    out=ROOT/'tmp'/sys.argv[1];out.mkdir(exist_ok=False)
    source=out/'source.db';patch=pytest.MonkeyPatch()
    patch.setitem(db_session.sqlite_db_config,'db_path',str(source))
    patch.setattr(db_session,'_engines',{})
    patch.setattr(comments,'source',lambda:str(source))
    patch.setattr(comments,'wait_between_requests',AsyncMock())
    await db_session.create_tables('sqlite')
    account=await posts.upsert_monitored_account('account-comments',display_name='评论验收账号')
    post=(await posts.upsert_post(aweme_id='123',sec_user_id=account.sec_user_id,title='评论验收作品',desc='作品文案',
          create_time=int(time.time())-100,canonical_url='https://www.douyin.com/video/123'))[0]
    for engine in db_session._engines.values():await engine.dispose()
    db_session._engines.clear()
    source_sha=hashlib.sha256(source.read_bytes()).hexdigest()
    platform=[]
    long_comment='长评论样本：'+('这是保留完整正文的长评论，用于验证展开后仍只在评论区内部滚动。'*30)+'longtoken'*60
    class Fake(Fetcher):
        def __init__(self):
            super().__init__([response(*[raw(str(i+100),text=long_comment if i==1 else f'实际评论样本{i}',reply_comment_total=2 if i==0 else 0,digg_count=100-i) for i in range(22)])],
                             [response()])
            async def replies(ident,parent,cursor):
                return response(raw('200',text='第一条子评论',reply_comment_total=0),raw('201',text='第二条子评论',reply_comment_total=0)) if parent=='100' else response()
            self._client.get_sub_comments=AsyncMock(side_effect=replies)
            platform.append(self)
    model=MonitorService();model._paused=False
    patch.setattr(model,'_crawler_is_busy',lambda:False)
    patch.setattr(model,'_risk_control_cooldown_remaining',lambda:0)
    patch.setattr(routes,'monitor_service',model)
    patch.setattr(monitor_module,'DouyinMonitorFetcher',Fake)
    patch.setattr(monitor_module.crawler_manager,'add_log',AsyncMock())
    app=FastAPI();requests=[];errors=[];external=[];cases=[];state={'fail':False}
    @app.middleware('http')
    async def boundary(request,next_handler):
        path=request.url.path;requests.append({'method':request.method,'path':path})
        if request.method not in ('GET','HEAD') and not ('comment-policy' in path or path.endswith('/comments/collect')):
            return JSONResponse({'detail':'隔离验收禁止其他写入'},405)
        if state['fail'] and path.endswith('/comments'):return JSONResponse({'detail':'隔离评论读取失败'},503)
        return await next_handler(request)
    app.get('/api/config/options')(get_config_options)
    app.get('/api/config/platforms')(get_platforms)
    @app.get('/api/monitor/dashboard')
    async def dashboard():
        return {'generated_at':'2026-11-04','account':None,'counts':{'posts':1,'snapshots':0,'jobs':{}},
                'posts':[{'aweme_id':'123','title':'评论验收作品','desc':'作品文案','create_time':post.create_time,
                    'first_seen_at':post.first_seen_at,'canonical_url':post.canonical_url,'cover_url':None,
                    'status':'active','snapshots':[]}]}
    @app.get('/api/monitor/health')
    async def health():return {'checks':[],'metrics':{},'system_config':{}}
    @app.get('/api/monitor/hot-rank')
    async def hot_rank():return {'items':[],'generated_at':'2026-11-04','source':'isolated fixture','cached':True}
    @app.get('/api/monitor/overview')
    async def overview():return {'jobs':{},'next_snapshot':None}
    app.include_router(router,prefix='/api')
    @app.get('/api/{path:path}')
    async def fallback(path):
        if path=='crawler/status':return {'status':'idle'}
        if path=='scheduler/status':return {'enabled':False,'times':[]}
        if path=='crawler/logs':return {'logs':[]}
        return {}
    @app.websocket('/api/ws/logs')
    async def logs(ws:WebSocket):
        await ws.accept()
        try:
            while True:
                if await ws.receive_text()=='ping':await ws.send_text('pong')
        except Exception:pass
    app.mount('/',StaticFiles(directory=ROOT/'webui'/sys.argv[2],html=True))
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(128)
    base=f'http://127.0.0.1:{listener.getsockname()[1]}'
    server=uvicorn.Server(uvicorn.Config(app,log_level='error'))
    thread=threading.Thread(target=server.run,kwargs={'sockets':[listener]},daemon=True);thread.start()
    try:
        async with async_playwright() as pw:
            context=await pw.chromium.launch_persistent_context(str(out/'chrome-profile'),headless=True,
                executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',viewport={'width':1440,'height':1000},
                args=['--disable-background-networking','--disable-sync','--no-first-run'])
            async def network(route):
                if urlsplit(route.request.url).hostname not in ('127.0.0.1','localhost'):
                    external.append({'type':route.request.resource_type});await route.abort()
                else:await route.continue_()
            await context.route('**/*',network)
            await context.add_init_script("localStorage.setItem('mediacrawler_license_accepted','true');localStorage.setItem('mediacrawler_env_checked','true');localStorage.setItem('i18nextLng','zh-CN')")
            page=await context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            async def record(name,fn):
                try:detail=await fn();status='passed'
                except Exception as exc:detail=str(exc)[:2000];status='failed'
                shot=f'{len(cases)+1:02d}.png';await page.screenshot(path=str(out/shot),full_page=True)
                cases.append({'name':name,'status':status,'detail':detail,'screenshot':shot});print(name,status,flush=True)
            async def settings():
                await page.goto(base+'/?tab=config')
                summary=page.locator('summary').filter(has_text='评论与子评论采集')
                await expect(summary).to_be_visible();await summary.click()
                await expect(page.get_by_label('自动采集新作品评论',exact=True)).not_to_be_checked()
                await page.get_by_label('自动采集新作品评论',exact=True).check()
                await expect(page.get_by_label('每作品主评论上限',exact=True)).to_have_count(0)
                await expect(page.get_by_label('每作品子评论总上限',exact=True)).to_have_count(0)
                await expect(page.get_by_text('不设数量上限 · 分页采集全部平台可见评论',exact=True)).to_be_visible()
                await page.get_by_role('button',name='保存评论设置',exact=True).click()
                await expect(page.get_by_text('评论设置已保存',exact=True)).to_be_visible()
                assert comments.repo.policy(source,account.sec_user_id)['enabled']
                return 'settings are separately saved, opt-in, no count cap inputs; no platform request on saving'
            await record('account_comment_settings',settings)
            async def open_empty():
                await page.goto(base+'/?tab=insights')
                await page.get_by_role('button').filter(has=page.get_by_role('heading',name='评论验收作品',exact=True)).first.click()
                panel=page.get_by_role('region',name='作品评论与子评论',exact=True)
                await panel.get_by_role('button',name='评论与子评论 · 展开',exact=True).click()
                await expect(panel.get_by_text('暂无已采集评论。',exact=False)).to_be_visible()
                assert not platform
                return 'reading details is lazy and readonly; empty does not claim platform has zero comments'
            await record('detail_empty_lazy_read',open_empty)
            async def collect():
                panel=page.get_by_role('region',name='作品评论与子评论',exact=True)
                await panel.get_by_role('button',name='采集 / 更新评论',exact=True).click()
                await expect(panel.get_by_text('实际评论样本0',exact=True)).to_be_visible()
                await panel.get_by_role('button',name='查看已采集回复（2 / 平台显示 2）',exact=True).click()
                await expect(panel.get_by_text('第一条子评论',exact=True)).to_be_visible()
                await expect(panel.get_by_text('第二条子评论',exact=True)).to_be_visible()
                assert comments.repo.read(source,'123')['total_saved']==24
                await expect(panel.get_by_text('未完成，进度已保存',exact=False)).to_be_visible()
                assert comments.repo.progress(source,'123')['checkpoint']['reply_after']=='108'
                return 'real isolated endpoint saves first slice (22 roots, 2 replies) and durable resume state; not marked completed'
            await record('collect_and_expand_replies',collect)
            async def resume():
                # Isolated clock advance only: production still respects 60-second pacing.
                with comments.repo.connection(source,True) as db:
                    db.execute('UPDATE collections SET updated_at=?,next_at=0 WHERE aweme_id=?',(int(time.time())-61,'123'))
                result=await model.collect_post_comments('123',manual=False)
                assert result['state']=='partial' and result['replies']==2
                assert platform[-1]._client.get_aweme_comments.await_count==0
                assert platform[-1]._client.get_sub_comments.await_args_list[0].args==('123','109',0)
                with comments.repo.connection(source,True) as db:
                    db.execute('UPDATE collections SET updated_at=?,next_at=0 WHERE aweme_id=?',(int(time.time())-61,'123'))
                result=await model.collect_post_comments('123',manual=False)
                assert result['state']=='completed' and comments.repo.fully_traversed(source,'123')
                await page.get_by_role('region',name='作品评论与子评论',exact=True).get_by_role('button',name='采集 / 更新评论',exact=True).click()
                await expect(page.get_by_text('本轮可见评论分页已完成',exact=False)).to_be_visible()
                return 'two further slices resume roots 109 then 119; no repeat root request; completes only after all child pages'
            await record('resume_until_all_visible_pages_done',resume)
            async def pagination():
                panel=page.get_by_role('region',name='作品评论与子评论',exact=True)
                await panel.get_by_role('button',name='下一页',exact=True).click()
                await expect(panel.get_by_text('实际评论样本21',exact=True)).to_be_visible()
                await expect(panel.get_by_text('第 2 页 · 共 22 条',exact=True)).to_be_visible()
                await panel.get_by_role('button',name='上一页',exact=True).click()
                await expect(panel.get_by_text('实际评论样本0',exact=True)).to_be_visible()
                await panel.get_by_role('button',name='采集 / 更新评论',exact=True).click()
                await expect(panel.get_by_text('评论采集尚在等待间隔或正在执行',exact=False)).to_be_visible()
                assert comments.repo.read(source,'123')['total_saved']==24
                return 'parent pagination and 60-second manual throttle; repeat does not duplicate rows'
            await record('pagination_and_repeat_throttle',pagination)
            async def keyboard():
                panel=page.get_by_role('region',name='作品评论与子评论',exact=True)
                button=panel.get_by_role('button',name='评论与子评论 · 收起',exact=True)
                writes=len([r for r in requests if r['method']=='POST'])
                await button.focus();await page.keyboard.press('Enter')
                await expect(panel.get_by_role('button',name='评论与子评论 · 展开',exact=True)).to_be_focused()
                await page.keyboard.press('Space')
                await expect(panel.get_by_text('实际评论样本0',exact=True)).to_be_visible()
                assert len([r for r in requests if r['method']=='POST'])==writes
                return 'Enter/Space expand and collapse, focus retained, no collection triggered by folding'
            await record('keyboard_readonly_folding',keyboard)
            async def compact_list():
                panel=page.get_by_role('region',name='作品评论与子评论',exact=True)
                listing=panel.get_by_role('region',name='已采集评论列表',exact=True)
                size=await listing.evaluate('(el)=>({height:el.clientHeight,scroll:el.scrollHeight})')
                assert size['height']<=241 and size['scroll']>size['height'],size
                height=(await panel.bounding_box())['height'];assert height<480,height
                article=listing.locator('article').filter(has_text='长评论样本：').first
                toggle=article.get_by_role('button',name='展开全文',exact=True)
                await expect(toggle).to_be_visible();await toggle.click()
                text=article.get_by_text(long_comment,exact=True)
                assert (await text.bounding_box())['height']>80
                assert abs((await panel.bounding_box())['height']-height)<2
                await article.get_by_role('button',name='收起全文',exact=True).click()
                assert (await text.bounding_box())['height']<=41
                await listing.focus();await page.keyboard.press('Home');await page.keyboard.press('PageDown')
                await page.wait_for_function('(el)=>el.scrollTop>0',arg=await listing.element_handle())
                await expect(panel.locator('details')).not_to_have_attribute('open','')
                return {'list':size,'section_height':height,'long_comment':'two lines, expandable, full text retained; inner scroll and keyboard verified'}
            await record('compact_scroll_and_long_text',compact_list)
            async def layouts():
                for dark in (False,True):
                    await page.evaluate('(v)=>document.documentElement.classList.toggle("dark",v)',dark)
                    for width in (1440,812,375):
                        await page.set_viewport_size({'width':width,'height':1000})
                        assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),f'overflow {width}'
                        await page.screenshot(path=str(out/f'comments-{width}-{dark}.png'),full_page=True)
                return 'light/dark and 1440/812/375 have no page horizontal overflow'
            await record('responsive_themes',layouts)
            async def data_dialog():
                await page.set_viewport_size({'width':1440,'height':1000})
                await page.goto(base+'/?tab=data')
                await page.get_by_role('button',name='评论验收作品',exact=True).click()
                dialog=page.get_by_role('dialog')
                panel=dialog.get_by_role('region',name='作品评论与子评论',exact=True)
                await panel.get_by_role('button',name='评论与子评论 · 展开',exact=True).click()
                await expect(panel.get_by_text('实际评论样本0',exact=True)).to_be_visible()
                dimensions=[]
                for dark in (False,True):
                    await page.evaluate('(v)=>document.documentElement.classList.toggle("dark",v)',dark)
                    for width in (1440,812,375):
                        await page.set_viewport_size({'width':width,'height':1000})
                        listing=panel.get_by_role('region',name='已采集评论列表',exact=True)
                        size=await listing.evaluate('(el)=>({height:el.clientHeight,scroll:el.scrollHeight})')
                        assert size['height']<=241 and size['scroll']>size['height'],size
                        assert (await panel.bounding_box())['height']<480
                        assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                        await page.screenshot(path=str(out/f'dialog-comments-{width}-{dark}.png'),full_page=True)
                        dimensions.append({'width':width,'dark':dark,**size})
                return dimensions
            await record('performance_dialog_compact_list',data_dialog)
            async def error_read():
                state['fail']=True
                await page.goto(base+'/?tab=insights')
                await page.get_by_role('button').filter(has=page.get_by_role('heading',name='评论验收作品',exact=True)).first.click()
                panel=page.get_by_role('region',name='作品评论与子评论',exact=True)
                await panel.get_by_role('button',name='评论与子评论 · 展开',exact=True).click()
                await expect(panel.get_by_role('alert')).to_contain_text('隔离评论读取失败')
                state['fail']=False
                await panel.get_by_role('button',name='重新读取评论',exact=True).click()
                await expect(panel.get_by_text('实际评论样本0',exact=True)).to_be_visible()
                return '503 is displayed and explicit retry recovers saved comments without collection'
            await record('read_error_and_recovery',error_read)
            async def boundaries():
                assert not external and not errors
                assert source_sha==hashlib.sha256(source.read_bytes()).hexdigest()
                assert all('model' not in r['path'] for r in requests)
                return 'source DB bytes unchanged; writes only sidecar; no real platform/model or external page requests'
            await record('storage_network_console',boundaries)
            await context.close()
    finally:
        server.should_exit=True;thread.join(timeout=10);patch.undo()
        (out/'results.json').write_text(json.dumps({'cases':cases,'requests':requests,'page_errors':errors,
            'external_page_attempts':external,'real_model_calls':0,'real_platform_calls':0,'formal_database_used':False},ensure_ascii=False,indent=2),encoding='utf-8')
    print(sum(c['status']=='passed' for c in cases),'/',len(cases))


if __name__=='__main__':asyncio.run(main())
