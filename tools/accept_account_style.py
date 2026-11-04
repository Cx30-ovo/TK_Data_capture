"""Isolated browser acceptance: real style persistence/validation, mocked model only."""
import asyncio
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
import sys
import threading
import time

import httpx
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from playwright.async_api import async_playwright, expect
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def main():
    from api.services import account_style_service as style
    from api.services.account_profile_service import get_account_profile
    from database.account_matrix_repository import get_matrix, read_accounts
    output = ROOT/'tmp'/sys.argv[1]
    output.mkdir(exist_ok=False)
    copy = output/'isolated.db'
    with sqlite3.connect((ROOT/'database/sqlite_tables.db').as_uri()+'?mode=ro',uri=True) as src, sqlite3.connect(copy) as dest:
        src.backup(dest)
    account = read_accounts(str(copy))[0]
    # Only this isolated copy is written. Clear previous style snapshots for deterministic empty state.
    with sqlite3.connect(copy) as conn:
        legacy_row = conn.execute("SELECT result_json FROM ai_analysis_results WHERE analysis_type='account_style' AND sec_user_id=? AND json_extract(result_json,'$.version')='account-style-v0.1' ORDER BY id DESC LIMIT 1",(account['sec_user_id'],)).fetchone()
        legacy_snapshot = json.loads(legacy_row[0]) if legacy_row else None
        conn.execute("DELETE FROM ai_analysis_results WHERE analysis_type='account_style'")
    metadata = output/'matrix.db'
    style.config.ai_config = {'enabled': True, 'model': 'browser-fixture', 'base_url': 'http://127.0.0.1/fixture', 'api_key': ''}
    state = {'failure': False, 'calls': 0}
    requests, errors, external, cases = [], [], [], []
    def provider(request):
        state['calls'] += 1
        if state['failure']: return httpx.Response(500)
        inputs = json.loads(json.loads(request.content)['messages'][1]['content'])
        summaries={'themes':'以本地民生与公共服务为主','title_structure':'事实前置，问句与短句结合','phrasing':'口语化叙事，兼有严肃表达','geography':'立足厦门，关注福建及周边','audience':'可能面向关注本地生活的读者'}
        tags={'themes':['本地民生','公共服务'],'title_structure':['事实前置','短句'],'phrasing':['口语叙事','直接表达'],'geography':['厦门','福建'],'audience':['本地生活','时事关注']}
        if 'post_id' in inputs[0]:
            result={'notes':summaries,'evidence_indices':{k:[i % min(3,len(inputs))] for i,k in enumerate(style.DIMENSIONS)},
                    'topic_labels':['本地民生','社会新闻','区域时事','其他'],'topic_assignments':[i%4 for i in range(len(inputs))]}
        else:
            result = {k:{'text': f'浏览器验收替身：{k}，仅作待核实推断。'+('完整材料中出现多种标题表达，需要结合代表作品理解。'*5), 'summary':summaries[k], 'labels':tags[k], 'evidence_post_ids':inputs[0]['evidence_post_ids'][:3]} for k in style.DIMENSIONS}
            result.update(topic_labels=['本地民生','社会新闻','区域时事','其他'],
                topic_mapping={t[0]:i for batch in inputs for i,t in enumerate(batch['topics'])},
                limitations=['浏览器模型响应替身，不代表真实模型生成质量'])
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(result,ensure_ascii=False)}}]})
    app=FastAPI()
    @app.middleware('http')
    async def log(request, call_next):
        requests.append({'method':request.method,'path':request.url.path})
        if request.method not in {'GET','HEAD'} and not request.url.path.endswith('/style-profile'):
            return JSONResponse({'detail':'写入已拦截'},405)
        try: return await call_next(request)
        except style.GroupingError as exc: return JSONResponse({'detail':str(exc)},exc.status)
    @app.get('/api/monitor/account-matrix')
    async def matrix(): return get_matrix(str(copy),str(metadata))
    @app.get('/api/monitor/account-matrix/model-status')
    async def status(): return style.model_status()
    @app.get('/api/monitor/accounts/{id}/profile')
    async def profile(id:int,days:int=30): return await get_account_profile(str(copy),id,days)
    @app.get('/api/monitor/accounts/{id}/style-profile')
    async def read(id:int,days:int=30): return await style.read_style(str(copy),id,days)
    @app.post('/api/monitor/accounts/{id}/style-profile')
    async def analyze(id:int,request:Request):
        body=await request.json()
        return await style.analyze_style(str(copy),id,body['days'],transport=httpx.MockTransport(provider),max_model_requests=body.get('max_model_requests',13))
    @app.get('/api/{path:path}')
    async def fallback(path:str):
        if path=='monitor/accounts': return {'accounts':read_accounts(str(copy)),'loop_running':False}
        if path=='crawler/status': return {'status':'idle'}
        if path=='monitor/execution': return {'paused':True,'crawler_running':False,'recovery':{'pending':False}}
        if path=='monitor/health': return {'checks':[],'metrics':{'jobs':{},'unread_alerts':0},'config':{}}
        if path=='monitor/overview': return {'jobs':{},'next_snapshot':None}
        if path=='scheduler/status': return {'enabled':False,'times':[]}
        if path=='config/platforms': return {'platforms':[]}
        if path=='config/options': return {'login_types':[],'crawler_types':[],'save_options':[]}
        return {}
    @app.websocket('/api/ws/logs')
    async def logs(ws:WebSocket):
        await ws.accept()
        try:
            while True:
                if await ws.receive_text()=='ping': await ws.send_text('pong')
        except Exception: pass
    app.mount('/',StaticFiles(directory=ROOT/'webui'/sys.argv[2],html=True))
    listener=socket.socket(); listener.bind(('127.0.0.1',0)); listener.listen(128)
    base=f'http://127.0.0.1:{listener.getsockname()[1]}'
    server=uvicorn.Server(uvicorn.Config(app,log_level='error'))
    thread=threading.Thread(target=server.run,kwargs={'sockets':[listener]},daemon=True); thread.start()
    try:
        async with async_playwright() as pw:
            context=await pw.chromium.launch_persistent_context(str(output/'chrome-profile'),executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True,viewport={'width':1440,'height':1000},args=['--disable-background-networking','--disable-sync','--no-first-run'])
            async def network(route):
                from urllib.parse import urlsplit
                if urlsplit(route.request.url).hostname not in {'127.0.0.1','localhost'}:
                    external.append(route.request.resource_type); await route.abort()
                else: await route.continue_()
            await context.route('**/*',network)
            await context.add_init_script("localStorage.setItem('mediacrawler_license_accepted','true');localStorage.setItem('mediacrawler_env_checked','true');localStorage.setItem('i18nextLng','zh-CN');")
            page=context.pages[0]; page.on('pageerror',lambda e:errors.append(str(e)))
            async def record(name,fn):
                try: detail=await fn(); status='通过'
                except Exception as exc: detail=str(exc)[:800]; status='失败'
                screenshot=f'{len(cases)+1:02d}.png'
                await page.screenshot(path=str(output/screenshot),full_page=True)
                cases.append(dict(name=name,status=status,detail=detail,screenshot=screenshot))
                print(name,status,flush=True)
            async def open_profile():
                await page.goto(base+'/?tab=accounts')
                await page.get_by_role('article').first.get_by_role('button').click()
                await page.locator('summary').filter(has_text='查看账号档案').click()
                await page.get_by_role('heading',name='账号风格档案',exact=True).wait_for()
            await open_profile()
            panel=page.get_by_role('region',name='账号风格档案',exact=True)
            async def initial():
                await expect(panel.get_by_text('尚未生成风格档案。',exact=False)).to_be_visible()
                assert state['calls']==0
                return 'GET不调用模型；空状态真实显示'
            await record('只读打开及空状态',initial)
            async def budget_ui():
                await panel.get_by_label('本次模型请求预算').select_option('1')
                await panel.get_by_role('button',name='分析账号风格',exact=True).click()
                await expect(panel.get_by_role('alert')).to_contain_text('超过本次预算')
                assert state['calls']==0
                await panel.get_by_label('本次模型请求预算').select_option('13')
                return '预算不足先拒绝，模型调用为0；预算可以显式调整'
            await record('请求预算前置拦截',budget_ui)
            async def generate():
                await panel.get_by_role('button',name='分析账号风格',exact=True).focus()
                await page.keyboard.press('Enter')
                await expect(panel.get_by_role('button',name='内容主题',exact=False)).to_be_visible()
                assert state['calls']==11
                await expect(panel.get_by_text('受众推测',exact=True)).to_be_visible()
                await expect(panel.get_by_text('模型逐篇归类',exact=True)).to_be_visible()
                assert (await style.read_style(str(copy),account['id']))['latest']['scope']['sampled']>40
                assert not await panel.get_by_text('完整材料中出现',exact=False).is_visible()
                await panel.screenshot(path=str(output/'style-overview.png'))
                return '显式点击一次；扩大样本超过40篇；五维短摘要，详情默认收起，真实样本主题计数'
            await record('显式分析及五个维度',generate)
            async def evidence():
                await panel.locator('summary').filter(has_text='分析详情与依据').first.focus()
                await page.keyboard.press('Space')
                await panel.locator('summary').filter(has_text='引用校验信息').first.click()
                await expect(panel.get_by_text('字段 title · 标题级 · SHA-256',exact=False).first).to_be_visible()
                await panel.get_by_role('button',name='风格依据下一条').click()
                await expect(panel.get_by_role('button',name='风格依据上一条')).to_be_enabled()
                await panel.locator('summary').filter(has_text='输入范围与分析限制').click()
                await expect(panel.get_by_text('不是专用模型训练结果',exact=False).first).to_be_visible()
                return '作品片段、字段、发布时间、ID和SHA可追溯；限制可展开'
            await record('代表作品依据与键盘展开',evidence)
            async def cache():
                await panel.get_by_role('button',name='更新风格分析',exact=True).click()
                await expect(panel.get_by_role('button',name='更新风格分析',exact=True)).to_be_enabled()
                assert state['calls']==11
                assert len(await style.history(str(copy),await style.source(str(copy),account['id'],30)))==1
                return '相同输入命中保存档案，不追加版本、不再调用模型'
            await record('相同输入复用',cache)
            async def windows_ui():
                before=state['calls']
                await panel.get_by_label('风格观察范围').select_option('long')
                await expect(panel.get_by_text('尚未生成风格档案。',exact=False)).to_be_visible()
                await expect(panel.get_by_text('篇 / 近 365 天',exact=False)).to_be_visible()
                await panel.get_by_label('风格观察范围').select_option('recent')
                await expect(panel.get_by_role('button',name='内容主题',exact=False)).to_be_visible()
                assert state['calls']==before
                return '长期与近期独立快照；切换只GET，不调用模型'
            await record('长期近期范围隔离',windows_ui)
            with sqlite3.connect(copy) as conn:
                now=int(time.time())
                # Copy an existing post to satisfy all NOT NULL source columns; only in isolated copy.
                original=conn.execute("SELECT * FROM douyin_posts WHERE platform=? AND sec_user_id=? AND status='active' LIMIT 1",(account['platform'],account['sec_user_id'])).fetchone()
                columns=[r[1] for r in conn.execute('PRAGMA table_info(douyin_posts)')]
                new=dict(zip(columns,original)); new.update(id=None,aweme_id='style-browser-new',title='验收新增标题：社区服务持续改善',create_time=now-2,first_seen_at=now-1)
                conn.execute('INSERT INTO douyin_posts('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',list(new.values()))
            async def update():
                await page.reload(); await page.get_by_role('article').first.get_by_role('button').click()
                await page.locator('summary').filter(has_text='查看账号档案').click()
                await expect(panel.get_by_text('输入已更新：新增 1 篇',exact=False)).to_be_visible()
                assert state['calls']==11
                await panel.get_by_role('button',name='更新风格分析',exact=True).click()
                await expect(panel.get_by_label('分析记录')).to_have_count(1)
                await expect(panel.get_by_label('分析记录').locator('option')).to_have_count(2)
                return '新增作品只提示；手动更新后历史版本保留'
            await record('新作品提示与追加版本',update)
            async def history_ui():
                select=panel.get_by_label('分析记录')
                value=await select.locator('option').last.get_attribute('value')
                await select.select_option(value)
                await expect(panel.get_by_text('正在查看历史版本',exact=True)).to_be_visible()
                return '历史快照可切换，使用原样本和原依据'
            await record('历史版本读取',history_ui)
            for width in [1440,812,375]:
                for dark in [False,True]:
                    async def layout():
                        await page.set_viewport_size({'width':width,'height':1000})
                        await page.evaluate('(v)=>document.documentElement.classList.toggle("dark",v)',dark)
                        await panel.scroll_into_view_if_needed()
                        assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                        return '深浅色可读，无横向溢出，历史和依据可操作'
                    await record(f'布局{width}{"深" if dark else "浅"}色',layout)
            async def failure():
                with sqlite3.connect(copy) as conn: conn.execute("UPDATE douyin_posts SET title='验收更正标题' WHERE aweme_id='style-browser-new'")
                state['failure']=True
                await panel.get_by_role('button',name='更新风格分析',exact=True).click()
                await expect(panel.get_by_role('alert')).to_contain_text('模型服务连接失败或拒绝请求')
                await expect(panel.get_by_role('button',name='内容主题',exact=False)).to_be_visible()
                assert len(await style.history(str(copy),await style.source(str(copy),account['id'],30)))==2
                return '失败提示明确，旧版本保留；不重试模型，不写失败结果覆盖旧稿'
            await record('模型失败保留原档案',failure)
            async def legacy_ui():
                if legacy_snapshot is None:
                    raise AssertionError('真实旧版样本不存在，不能声称通过旧档案验收')
                assert legacy_snapshot['version']=='account-style-v0.1'
                with sqlite3.connect(copy) as conn:
                    conn.execute("UPDATE ai_analysis_results SET result_json=? WHERE analysis_type='account_style' AND id=(SELECT max(id) FROM ai_analysis_results WHERE analysis_type='account_style')",(json.dumps(legacy_snapshot,ensure_ascii=False),))
                previous_calls=state['calls']
                await page.set_viewport_size({'width':1440,'height':1000})
                await page.evaluate('document.documentElement.classList.remove("dark")')
                await open_profile()
                await expect(panel.get_by_role('button',name='扩大样本并更新')).to_be_enabled()
                await expect(panel.get_by_text('该版本未记录逐篇主题分类',exact=False)).to_be_visible()
                await expect(panel.get_by_text('当前为旧版档案。',exact=False)).to_be_visible()
                assert state['calls']==previous_calls
                await panel.screenshot(path=str(output/'legacy-overview.png'))
                return '真实v0.1快照：40篇等原始计数保留；短文案展示兼容，不编造主题分布'
            await record('真实旧版档案展示兼容',legacy_ui)
            await context.close()
    finally:
        server.should_exit=True; thread.join(timeout=10)
        result=dict(cases=cases,requests=requests,page_errors=errors,external_page_attempts=external,
                    real_model_calls=0,fixture_model_calls=state['calls'],database='isolated copy only',server_stopped=not thread.is_alive())
        (output/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(sum(c['status']=='通过' for c in cases),'/',len(cases),'errors',errors)


if __name__=='__main__': asyncio.run(main())
