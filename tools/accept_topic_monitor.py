"""Loopback UI acceptance with real topic service, isolated DB and fake search."""
import asyncio
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
import sys
import threading
from unittest.mock import AsyncMock
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import pytest
import uvicorn
from fastapi import FastAPI,WebSocket
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from playwright.async_api import async_playwright,expect


async def main():
    from api.routers.topic_monitor import router
    from api.services import topic_monitor_service as svc
    from database import topic_monitor_repository as repo
    from config.db_config import sqlite_db_config
    from tests.test_topic_monitor import Fetcher,response,raw
    out=ROOT/'tmp'/sys.argv[1];out.mkdir(exist_ok=False)
    source=out/'source.db'
    with sqlite3.connect(source) as db:db.execute('CREATE TABLE original(value TEXT)');db.execute("INSERT INTO original VALUES('preserve')")
    original=source.read_bytes();patch=pytest.MonkeyPatch()
    patch.setitem(sqlite_db_config,'db_path',str(source))
    patch.setattr(svc.monitor_service,'_paused',False)
    patch.setattr(svc.monitor_service,'_risk_control_cooldown_remaining',lambda:0)
    patch.setattr(svc.monitor_service,'_crawler_is_busy',lambda:False)
    patch.setattr(svc.monitor_service,'_lock',asyncio.Lock())
    patch.setattr(svc,'wait_between_searches',AsyncMock())
    requests=[];external=[];errors=[];cases=[];state={'error':False};platform_calls=[]
    app=FastAPI()
    @app.middleware('http')
    async def boundary(request,next_handler):
        requests.append({'method':request.method,'path':request.url.path})
        if request.method not in ('GET','HEAD') and not request.url.path.startswith('/api/topic-monitors'):
            return JSONResponse({'detail':'isolated writes only'},405)
        if state['error'] and request.url.path.startswith('/api/topic-monitors'):
            return JSONResponse({'detail':'隔离验收：话题读取失败'},503)
        return await next_handler(request)
    app.include_router(router,prefix='/api')
    @app.get('/api/{path:path}')
    async def fallback(path:str):
        if path=='monitor/accounts':return {'accounts':[],'loop_running':False}
        if path=='crawler/status':return {'status':'idle'}
        if path=='monitor/execution':return {'paused':True,'crawler_running':False,'recovery':{'pending':False}}
        if path=='monitor/health':return {'checks':[],'metrics':{'jobs':{},'unread_alerts':0},'config':{}}
        if path=='monitor/overview':return {'jobs':{},'next_snapshot':None}
        if path=='scheduler/status':return {'enabled':False,'times':[]}
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
            context=await pw.chromium.launch_persistent_context(str(out/'chrome-profile'),
                executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True,
                viewport={'width':1440,'height':1000},args=['--disable-background-networking','--disable-sync','--no-first-run'])
            async def network(route):
                if urlsplit(route.request.url).hostname not in ('127.0.0.1','localhost'):
                    external.append({'type':route.request.resource_type});await route.abort()
                else:await route.continue_()
            await context.route('**/*',network)
            await context.add_init_script("localStorage.setItem('mediacrawler_license_accepted','true');localStorage.setItem('mediacrawler_env_checked','true');localStorage.setItem('i18nextLng','zh-CN')")
            page=await context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
            async def record(name,fn):
                try:detail=await fn();status='passed'
                except Exception as exc:detail=str(exc)[:1500];status='failed'
                shot=f'{len(cases)+1:02d}.png';await page.screenshot(path=str(out/shot),full_page=True)
                cases.append({'name':name,'status':status,'detail':detail,'screenshot':shot});print(name,status,flush=True)
            await page.goto(base+'/?tab=topic-monitor')
            region=page.get_by_role('region',name='话题监控',exact=True)
            async def entry():
                await expect(region.get_by_role('heading',name='话题监控',exact=True)).to_be_visible()
                await expect(region.get_by_role('heading',name='尚未添加话题监控',exact=True)).to_be_visible()
                assert not repo.path_for(source).exists() and not platform_calls
                assert not any(r['method']=='POST' for r in requests)
                return 'independent sidebar and deep link; empty read does not initialize sidecar or collect'
            await record('entry_empty_readonly',entry)
            async def presets():
                await region.get_by_role('button',name='新增话题',exact=True).click()
                form=region.get_by_role('form',name='新增话题监控',exact=True)
                for label,days in [('未来两周',21),('过去一周＋未来一周',14),('过去一周',7)]:
                    await form.get_by_role('button',name=label,exact=True).click()
                    start=await form.get_by_label('作品发布开始时间',exact=True).input_value()
                    end=await form.get_by_label('作品发布结束时间',exact=True).input_value()
                    from datetime import datetime
                    assert (datetime.fromisoformat(end)-datetime.fromisoformat(start)).total_seconds()==days*86400
                await form.get_by_label('话题名称',exact=True).fill('第39届中国电影金鸡奖，金鸡百花奖')
                await expect(form.get_by_label('搜索关键词',exact=True)).to_have_count(0)
                await expect(form.get_by_text('话题名称即搜索关键词；多个词用逗号分隔，任一命中即可纳入，最多10个。',exact=True)).to_be_visible()
                for width in (1440,812,375):
                    await page.set_viewport_size({'width':width,'height':1000})
                    assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    await page.screenshot(path=str(out/f'create-{width}.png'),full_page=True)
                await page.set_viewport_size({'width':1440,'height':1000})
                await form.get_by_role('button',name='过去一周＋未来一周',exact=True).click()
                await form.get_by_role('checkbox',name='创建后启用采集（优先历史补采，再按间隔监控新作）',exact=True).uncheck()
                await form.get_by_role('button',name='创建监控',exact=True).click()
                await expect(region.get_by_role('heading',name='第39届中国电影金鸡奖，金鸡百花奖',exact=True)).to_be_visible()
                assert len(repo.listing(source))==1 and not repo.listing(source)[0]['enabled']
                saved=repo.listing(source)[0]
                assert saved['keywords']==['第39届中国电影金鸡奖','金鸡百花奖']
                return 'topic name splits keywords, week of history precedes two future weeks; responsive presets; no real platform request'
            await record('create_and_time_presets',presets)
            async def enable_collect():
                await region.get_by_role('button',name='启用话题',exact=True).click()
                await expect(region.get_by_role('button',name='暂停话题',exact=True)).to_be_visible()
                topic=repo.listing(source)[0];now=int(svc.time.time())
                values=[raw(str(1000+i),create_time=now-100-i*60,
                    statistics={'digg_count':i*100,'comment_count':i,'collect_count':0,'share_count':0},
                    desc=f'第39届中国电影金鸡奖作品{i} #金鸡奖 #电影') for i in range(12)]
                values.append(raw('9999',create_time=now-100,statistics={},desc='第39届中国电影金鸡奖数据缺失'))
                f=Fetcher([response(*values,more=True),response(*values,more=True,cursor=26),response(*values)])
                entered,release=asyncio.Event(),asyncio.Event()
                fetch_search=f.search_info_by_keyword
                async def searching(*args,**kwargs):
                    entered.set();await release.wait();return await fetch_search(*args,**kwargs)
                f.search_info_by_keyword=searching
                pending=asyncio.create_task(svc.collect(source,topic['id'],manual=True,fetcher_factory=lambda:f))
                try:
                    await asyncio.wait_for(entered.wait(),3)
                    await page.reload()
                    await expect(region.get_by_text('正在补采历史作品',exact=False)).to_be_visible()
                    await expect(region.get_by_text('关键词 1/2',exact=False)).to_be_visible()
                finally:release.set();result=await pending
                platform_calls.extend(f.calls);assert result['status']=='completed'
                await page.reload()
                await expect(region.get_by_role('article',name='话题作品',exact=True)).to_have_count(10)
                await expect(region.get_by_text('第39届中国电影金鸡奖作品11 #金鸡奖 #电影',exact=True)).to_be_visible()
                assert (await svc.detail(source,topic['id']))['total']==13
                return 'UI enables task; actual isolated collection with mocked search; deduped 13 works, heat sorting, no source database mutation'
            await record('enable_and_isolated_collection',enable_collect)
            async def backfill_to_monitoring():
                topic=repo.listing(source)[0]
                assert topic['backfill']['status']=='pending'
                await expect(region.get_by_text('优先历史补采',exact=False)).to_be_visible()
                f=Fetcher([response()])
                result=await svc.collect(source,topic['id'],manual=True,fetcher_factory=lambda:f)
                platform_calls.extend(f.calls)
                assert f.calls[0][1]['offset']==26 and result['backfill_checkpoint']['status']=='complete'
                await page.reload()
                await expect(region.get_by_text('历史补采已结束（平台可见范围）',exact=False)).to_be_visible()
                live=Fetcher([response(),response()])
                result=await svc.collect(source,topic['id'],manual=True,fetcher_factory=lambda:live)
                platform_calls.extend(live.calls)
                assert result['stage']=='monitoring' and all(c[1]['offset']==0 for c in live.calls)
                await page.reload()
                await expect(region.get_by_role('article',name='话题作品',exact=True)).to_have_count(10)
                return 'durable historical cursor resumes at 26; UI transitions to monitoring only after history ends; live searches restart at 0; prior works retained'
            await record('backfill_continuation_then_live_monitoring',backfill_to_monitoring)
            async def pagination():
                await region.get_by_role('button',name='作品下一页',exact=True).click()
                await expect(region.get_by_role('article',name='话题作品',exact=True)).to_have_count(3)
                missing=region.get_by_role('article',name='话题作品',exact=True).filter(has=page.get_by_role('link',name='打开作品 9999',exact=True))
                for label in ('点赞','评论','收藏','分享'):
                    await expect(missing.locator(f'[title="{label}"]').get_by_text('—',exact=True)).to_be_visible()
                zero=region.get_by_role('article',name='话题作品',exact=True).filter(has_text='金鸡奖作品0 ')
                for label in ('点赞','评论','收藏','分享'):
                    await expect(zero.locator(f'[title="{label}"]').get_by_text('0',exact=True)).to_be_visible()
                await region.get_by_label('话题作品排序',exact=True).select_option('recent')
                await expect(region.get_by_role('article',name='话题作品',exact=True)).to_have_count(10)
                return 'pagination/sorting; real zero renders 0 and absent counts render em dash, not zero'
            await record('pagination_zero_null',pagination)
            async def compact():
                await expect(region.get_by_text('作品发布：',exact=False)).not_to_be_visible()
                await expect(region.get_by_role('region',name='作品发布趋势',exact=True)).not_to_be_visible()
                first=region.get_by_role('article',name='话题作品',exact=True).first
                button=first.get_by_role('button',name='展开作品详情',exact=False)
                await expect(button).to_have_attribute('aria-expanded','false')
                height=(await first.bounding_box())['height']
                writes=sum(r['method'] not in ('GET','HEAD') for r in requests)
                summary=region.locator('summary').filter(has_text='监控配置与时间范围')
                await summary.focus();await page.keyboard.press('Enter')
                await expect(region.get_by_text('作品发布：',exact=False)).to_be_visible()
                await page.keyboard.press('Space')
                await expect(region.get_by_text('作品发布：',exact=False)).not_to_be_visible()
                await button.focus();await page.keyboard.press('Enter')
                await expect(first.get_by_role('button',name='收起作品详情',exact=False)).to_have_attribute('aria-expanded','true')
                assert (await first.bounding_box())['height']>height
                await page.keyboard.press('Enter')
                await expect(button).to_be_focused()
                await expect(button).to_have_attribute('aria-expanded','false')
                assert sum(r['method'] not in ('GET','HEAD') for r in requests)==writes
                return f'configuration, insights and work details collapsed by default; keyboard toggles preserve focus; first compact row {height}px; folding makes no write requests'
            await record('compact_default_and_keyboard_folding',compact)
            async def hot_charts():
                await region.get_by_text('趋势与话题排行',exact=True).click()
                await expect(region.get_by_role('region',name='作品发布趋势',exact=True)).to_be_visible()
                await expect(region.get_by_role('region',name='热度话题排行',exact=True)).to_be_visible()
                await expect(region.get_by_text('数据不足',exact=True)).to_be_visible()
                await region.get_by_text('采集记录与计算口径',exact=True).click()
                await expect(region.get_by_text('仅本话题搜索采样范围',exact=False)).to_be_visible()
                assert await region.get_by_role('link',name='打开作品 1000',exact=True).get_attribute('target')=='_blank'
                await page.screenshot(path=str(out/'expanded-insights.png'),full_page=True)
                await region.get_by_text('趋势与话题排行',exact=True).click()
                await region.get_by_text('采集记录与计算口径',exact=True).click()
                return 'trend/tag grouping/observed heat scope; insufficient history never predicts; external work navigation explicit only'
            await record('hot_topics_and_scope',hot_charts)
            async def layouts():
                for dark in (False,True):
                    await page.evaluate('(v)=>document.documentElement.classList.toggle("dark",v)',dark)
                    for width in (1440,812,375):
                        await page.set_viewport_size({'width':width,'height':1000})
                        assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'), f'horizontal overflow at {width}, dark={dark}'
                        works=region.get_by_role('region',name='高热度作品列表',exact=True)
                        assert await works.evaluate('(e)=>e.clientHeight<=512 && e.scrollHeight>e.clientHeight && getComputedStyle(e).overflowY==="auto"'), f'works scrollbox at {width}, dark={dark}'
                        await works.focus();await page.keyboard.press('End')
                        await page.wait_for_function('(e)=>e.scrollTop>0',arg=await works.element_handle(),timeout=3000)
                        await works.evaluate('(e)=>e.scrollTop=0')
                        nav=await region.get_by_role('navigation',name='话题列表').bounding_box()
                        panel=await region.get_by_role('region',name='高热度作品',exact=True).bounding_box()
                        if width==1440:assert nav['x']+nav['width']<=panel['x'] and nav['width']<=240, f'desktop layout: {nav}, {panel}'
                        else:assert nav['y']+nav['height']<=panel['y'], f'narrow layout: {nav}, {panel}'
                        await page.screenshot(path=str(out/f'topic-{width}-{dark}.png'),full_page=True)
                await page.set_viewport_size({'width':1440,'height':1000})
                return 'six viewport/theme checks, no horizontal overflow'
            await record('responsive_and_themes',layouts)
            async def pause_keyboard():
                button=region.get_by_role('button',name='暂停话题',exact=True)
                await button.focus();await page.keyboard.press('Space')
                await expect(region.get_by_role('button',name='启用话题',exact=True)).to_be_visible()
                task=repo.listing(source)[0]
                assert not task['enabled'] and (await svc.collect(source,task['id']))['status']=='deferred'
                await region.get_by_role('button',name='新增话题',exact=True).focus();await page.keyboard.press('Enter')
                await expect(region.get_by_role('form',name='新增话题监控',exact=True)).to_be_visible()
                await region.get_by_label('话题名称',exact=True).focus();await page.keyboard.press('Escape')
                await expect(region.get_by_role('form',name='新增话题监控',exact=True)).to_have_count(0)
                await expect(region.get_by_role('button',name='新增话题',exact=True)).to_be_focused()
                return 'Space pauses, Enter opens create, Escape closes; prior samples retained'
            await record('pause_and_keyboard',pause_keyboard)
            async def coexistence():
                async with svc.monitor_service._lock:
                    await page.reload()
                    await expect(region.get_by_text('专用浏览器正在执行其他采集',exact=False)).to_be_visible()
                svc._stops['isolated-ui-phase']=asyncio.Event()
                try:
                    await page.reload()
                    await expect(region.get_by_text('账号监控保持启用',exact=False)).to_be_visible()
                finally:svc._stops.pop('isolated-ui-phase',None)
                await page.reload()
                await expect(region.get_by_role('heading',name='第39届中国电影金鸡奖，金鸡百花奖',exact=True)).to_be_visible()
                return 'account/browser contention and active topic phases visible; independent pause retains samples; no real collection'
            await record('account_topic_coexistence_status',coexistence)
            async def failure():
                state['error']=True;await page.reload()
                await expect(region.get_by_role('alert')).to_contain_text('话题读取失败')
                state['error']=False;await region.get_by_role('button',name='重读话题',exact=True).click()
                await expect(region.get_by_role('heading',name='第39届中国电影金鸡奖，金鸡百花奖',exact=True)).to_be_visible()
                return 'read failures visible, explicit recovery preserves configuration and collected works'
            await record('error_and_recovery',failure)
            async def delete_cancel():
                await region.get_by_role('button',name='删除监控',exact=True).click()
                modal=page.get_by_role('dialog',name='删除话题监控？',exact=True)
                await expect(modal.get_by_role('button',name='取消',exact=True)).to_be_focused()
                await expect(modal).to_contain_text('其他话题共用的作品')
                for dark in (False,True):
                    await page.evaluate('(v)=>document.documentElement.classList.toggle("dark",v)',dark)
                    await page.set_viewport_size({'width':375,'height':900})
                    assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    await page.screenshot(path=str(out/f'delete-375-{dark}.png'),full_page=True)
                await page.keyboard.press('Escape')
                await expect(modal).to_have_count(0)
                await expect(region.get_by_role('button',name='删除监控',exact=True)).to_be_focused()
                assert len(repo.listing(source))==1
                await page.set_viewport_size({'width':1440,'height':1000})
                return 'explicit confirmation, default cancel focus, Escape returns focus, no delete on cancel, narrow light/dark visible'
            await record('delete_confirmation_and_cancel',delete_cancel)
            async def delete_conflict():
                topic=repo.listing(source)[0]
                await region.get_by_role('button',name='删除监控',exact=True).click()
                request=svc.TopicUpdate(**{k:topic[k] for k in svc.TopicCreate.model_fields},expected_version=topic['version'])
                await svc.update(source,topic['id'],request)
                modal=page.get_by_role('dialog',name='删除话题监控？',exact=True)
                await modal.get_by_role('button',name='确认删除',exact=True).click()
                await expect(modal.get_by_role('alert')).to_contain_text('话题设置已更新')
                assert repo.read(source,topic['id']) and (await svc.detail(source,topic['id']))['total']==13
                await modal.get_by_role('button',name='取消',exact=True).click()
                await page.reload()
                return '409 preserves task/data; no automatic retry; cancel and reload obtain current version'
            await record('delete_conflict_preserves_task',delete_conflict)
            async def deletion():
                first=repo.listing(source)[0]
                other=await svc.create(source,svc.TopicCreate(name='另一话题',keywords=['电影','保留旧关键词'],start_at=first['start_at'],end_at=first['end_at'],enabled=False))
                # Keep an independent topic visible after deleting the selection.
                await page.reload()
                await region.get_by_role('navigation',name='话题列表',exact=True).get_by_role('button').filter(has_text='第39届').click()
                await expect(region.get_by_role('heading',name='第39届中国电影金鸡奖，金鸡百花奖',exact=True)).to_be_visible()
                await region.get_by_role('button',name='删除监控',exact=True).click()
                await page.get_by_role('dialog').get_by_role('button',name='确认删除',exact=True).click()
                await expect(region.get_by_role('heading',name='另一话题',exact=True)).to_be_visible()
                await expect(region.get_by_text('已删除监控“第39届中国电影金鸡奖，金鸡百花奖”',exact=True)).to_be_visible()
                assert len(repo.listing(source))==1 and repo.read(source,other['id'])
                await region.get_by_role('button',name='启用话题',exact=True).click()
                await expect(region.get_by_role('button',name='暂停话题',exact=True)).to_be_visible()
                assert repo.read(source,other['id'])['keywords']==['电影','保留旧关键词']
                await region.get_by_role('button',name='删除监控',exact=True).click()
                await page.get_by_role('dialog').get_by_role('button',name='确认删除',exact=True).click()
                await expect(region.get_by_role('heading',name='尚未添加话题监控',exact=True)).to_be_visible()
                assert not repo.listing(source) and not svc.monitor_service._paused
                return 'confirmed DELETE removes selection, selects remaining task, last deletion returns empty state, account collection remains enabled'
            await record('delete_selected_and_last_task',deletion)
            async def boundaries():
                assert source.read_bytes()==original and not external and not errors
                assert not any('model' in r['path'] or '/titles' in r['path'] for r in requests)
                assert all(r['method'] in ('GET','HEAD') or r['path'].startswith('/api/topic-monitors') for r in requests)
                with sqlite3.connect(repo.path_for(source)) as c:
                    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
                    assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
                return 'zero real model/platform calls, no external page resources, only sidecar writes; original DB bytes preserved'
            await record('network_and_storage_boundary',boundaries)
            await context.close()
    finally:
        server.should_exit=True;thread.join(timeout=10);patch.undo()
        result={'cases':cases,'requests':requests,'page_errors':errors,'external_page_attempts':external,
            'real_model_calls':0,'real_platform_calls':0,'fixture_search_calls':len(platform_calls),'formal_database_used':False}
        (out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(sum(c['status']=='passed' for c in cases),'/',len(cases),'page_errors',len(errors))


if __name__=='__main__':asyncio.run(main())
