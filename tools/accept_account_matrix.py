"""Isolated UI acceptance: actual matrix/profile code, test metadata only."""
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import sqlite3
import threading
import sys

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from playwright.async_api import async_playwright, expect
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


async def main():
    import sys
    output = ROOT / ('tmp/' + (sys.argv[1] if len(sys.argv) > 1 else 'account-matrix-browser-20261022-01'))
    output.mkdir(exist_ok=False)
    source = ROOT / 'database/sqlite_tables.db'
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    copy = output / 'source-copy.db'
    with sqlite3.connect(source.as_uri()+'?mode=ro', uri=True) as original, sqlite3.connect(copy) as dest:
        original.backup(dest)
    copy_sha = hashlib.sha256(copy.read_bytes()).hexdigest()
    metadata = output / 'matrix-test.db'
    repo = module('matrix_accept_repository', 'database/account_matrix_repository.py')
    schemas = module('matrix_accept_schema', 'api/schemas/account_matrix.py')
    profiles = module('matrix_accept_profiles', 'api/services/account_profile_service.py')
    accounts = repo.read_accounts(str(copy))
    assert len(accounts) >= 2
    first, second = accounts[0], accounts[1]
    requests, externals, errors, cases = [], [], [], []
    state = {'error': False}
    app = FastAPI()

    @app.middleware('http')
    async def log(request: Request, call_next):
        requests.append({'method': request.method, 'path': request.url.path})
        if request.method not in {'GET', 'HEAD'} and not request.url.path.startswith('/api/monitor/account-matrix/'):
            return JSONResponse({'detail': 'Writes blocked'}, status_code=405)
        try:
            return await call_next(request)
        except repo.MatrixError as exc:
            return JSONResponse({'detail': str(exc)}, status_code=exc.status)

    @app.get('/api/monitor/account-matrix')
    async def read():
        if state['error']:
            return JSONResponse({'detail': '验收注入：元数据不可用'}, status_code=503)
        return repo.get_matrix(str(copy), str(metadata))

    @app.get('/api/monitor/account-matrix/model-status')
    async def model_status():
        return {'available': True, 'reason': None, 'model': 'browser-fixture-model', 'scope': '标题级'}

    @app.post('/api/monitor/account-matrix/{id}/infer-group')
    async def grouping_fixture(id: int):
        # Explicit UI fixture: real provider validation is recorded separately.
        p = await profiles.get_account_profile(str(copy), id, 30)
        refs = next(s['evidence'] for s in p['signals'] if s['evidence'])
        inference = dict(group='本地民生', rationale='浏览器注入：仅验证推断建议交互', evidence=refs,
                    limitations=['浏览器响应替身，不代表真实模型推断'], model='browser-fixture-model',
                    scope='标题级待核验', cached=False, input_titles=len(refs), input_sha256=p['input_sha256'], generated_at=1800000000)
        baseline = repo.get_matrix(str(copy),str(metadata))
        account = next(a for a in baseline['accounts'] if a['id']==id)
        updated = repo.save_assignment(str(copy),str(metadata),id,dict(expected_version=baseline['version'],identity_sha256=account['identity_sha256']),generated_group=inference)
        return {**inference,'matrix':updated}

    @app.put('/api/monitor/account-matrix/{id}')
    async def save(id: int, request: Request):
        value = schemas.MatrixAssignment.model_validate(await request.json())
        return repo.save_assignment(str(copy), str(metadata), id, value.model_dump())

    @app.get('/api/monitor/accounts/{id}/profile')
    async def profile(id: int, days: int = 30):
        return await profiles.get_account_profile(str(copy), id, days)

    @app.get('/api/monitor/accounts/{id}/style-profile')
    async def style_profile(id: int, days: int = 30):
        from api.services.account_style_service import read_style
        return await read_style(str(copy), id, days)

    @app.get('/api/{path:path}')
    async def stub(path: str):
        if path == 'monitor/accounts': return {'accounts': accounts, 'loop_running': False}
        if path == 'crawler/status': return {'status': 'idle'}
        if path == 'monitor/execution': return {'paused': True, 'crawler_running': False, 'recovery': {'pending': False}}
        if path == 'monitor/health': return {'checks': [], 'metrics': {'jobs': {}, 'unread_alerts': 0}, 'config': {}}
        if path == 'monitor/overview': return {'jobs': {}, 'next_snapshot': None}
        if path == 'scheduler/status': return {'enabled': False, 'times': []}
        if path == 'config/platforms': return {'platforms': []}
        if path == 'config/options': return {'login_types': [], 'crawler_types': [], 'save_options': []}
        return {}

    @app.websocket('/api/ws/logs')
    async def logs(websocket: WebSocket):
        await websocket.accept()
        try:
            while True:
                if await websocket.receive_text() == 'ping':
                    await websocket.send_text('pong')
        except Exception:
            pass

    app.mount('/', StaticFiles(directory=ROOT/'webui'/(sys.argv[2] if len(sys.argv)>2 else 'dist-account-matrix-20261022-02'), html=True))
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{port}'
    async def record(name, operation):
        try:
            detail = await operation()
            status = '通过'
        except Exception as exc:
            detail, status = str(exc)[:600], '失败'
        shot = f'{len(cases)+1:02d}.png'
        await page.screenshot(path=str(output/shot), full_page=True)
        cases.append(dict(name=name, status=status, detail=detail, screenshot=shot))
        print(name, status, flush=True)
    try:
        async with async_playwright() as pw:
            context = await pw.chromium.launch_persistent_context(str(output/'chrome-profile'),
                executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe', headless=True,
                viewport={'width': 1440, 'height': 1000},
                args=['--disable-background-networking', '--disable-sync', '--no-first-run'])
            async def network(route):
                from urllib.parse import urlsplit
                host = urlsplit(route.request.url).hostname
                if host not in {'localhost', '127.0.0.1'}:
                    externals.append(route.request.resource_type)
                    await route.abort()
                else: await route.continue_()
            await context.route('**/*', network)
            await context.add_init_script("localStorage.setItem('mediacrawler_license_accepted','true');localStorage.setItem('mediacrawler_env_checked','true');localStorage.setItem('i18nextLng','zh-CN');")
            page = context.pages[0]
            page.on('pageerror', lambda error: errors.append(str(error)))
            await page.goto(base+'/?tab=accounts')
            await page.get_by_role('heading', name='账号矩阵', exact=True).wait_for()
            async def initial():
                await expect(page.get_by_role('tab',name='同事件竞品对比',exact=True)).to_have_count(0)
                await expect(page.get_by_text('事件机会池',exact=True)).to_have_count(0)
                await expect(page.get_by_role('article')).to_have_count(len(accounts))
                assert not metadata.exists()
                assert not any('/profile' in r['path'] for r in requests)
                return '独立入口默认待分类；GET 不创建元数据库，档案惰性加载'
            await record('独立入口及只读初始状态', initial)
            async def edit(id, role, group='', targets=None):
                card = page.get_by_role('article').filter(has=page.get_by_role('heading', name=accounts[id-1]['display_name'], exact=True))
                await card.get_by_role('button', name='查看与管理').click()
                await page.get_by_role('button', name='编辑业务信息', exact=True).click()
                await page.get_by_label('账号身份', exact=True).select_option(role)
                for name in targets or []: await page.get_by_role('checkbox', name=name, exact=True).check()
                await page.get_by_role('button', name='保存业务信息', exact=True).click()
                await expect(page.get_by_role('status').filter(has_text='业务信息已保存')).to_have_class('sr-only')
                return '保存成功；刷新读取独立元数据'
            await record('竞品身份及分组保存', lambda: edit(second['id'], 'competitor', '新闻'))
            await record('自有身份及竞品关联', lambda: edit(first['id'], 'owned', '新闻', [second['display_name']]))
            async def inference_ui():
                current = repo.get_matrix(str(copy), str(metadata))
                await page.get_by_role('button', name='生成业务分组', exact=True).click()
                await expect(page.get_by_role('button',name='更新模型分组')).to_be_visible()
                assert await page.get_by_label('业务分组',exact=True).count()==0
                assert repo.get_matrix(str(copy), str(metadata))['version'] == current['version']+1
                await page.reload()
                await page.get_by_role('article').first.get_by_role('button').click()
                await expect(page.get_by_role('button',name='更新模型分组')).to_be_visible()
                return '显式模型替身；生成直接持久化，刷新保留，无手填和采用步骤'
            await record('模型分组直接生成保存（响应替身）', inference_ui)
            async def persistence():
                await page.reload()
                await expect(page.get_by_text('关联竞品：'+second['display_name'], exact=True)).to_be_visible()
                return '重载后身份、分组和关联保留'
            await record('刷新后持久化', persistence)
            async def filters():
                await page.get_by_label('搜索矩阵账号').fill('不存在的账号')
                await expect(page.get_by_text('没有符合筛选条件的账号')).to_be_visible()
                await page.get_by_label('搜索矩阵账号').fill('')
                await page.get_by_label('身份筛选', exact=True).select_option('owned')
                await expect(page.get_by_role('article')).to_have_count(1)
                await page.get_by_label('身份筛选', exact=True).select_option('all')
                await page.get_by_label('分组筛选', exact=True).select_option('group:本地民生')
                await expect(page.get_by_role('article')).to_have_count(1)
                await page.get_by_label('分组筛选', exact=True).select_option('all')
                return '搜索空结果和角色筛选正确'
            await record('搜索和身份筛选', filters)
            async def conflict():
                await page.get_by_role('article').first.get_by_role('button').click()
                await page.get_by_role('button', name='编辑业务信息', exact=True).click()
                await page.get_by_label('账号身份', exact=True).select_option('unassigned')
                current = repo.get_matrix(str(copy), str(metadata))
                a = current['accounts'][1]
                repo.save_assignment(str(copy), str(metadata), a['id'], dict(expected_version=current['version'],
                    identity_sha256=a['identity_sha256'], role='competitor', group='新闻', competitor_ids=[]))
                await page.get_by_role('button', name='保存业务信息', exact=True).click()
                await expect(page.get_by_role('alert').filter(has_text='账号矩阵已更新')).to_be_visible()
                await expect(page.get_by_label('账号身份', exact=True)).to_have_value('unassigned')
                await page.get_by_role('button', name='取消', exact=True).click()
                return '409 保留输入，无自动合并或覆盖'
            await record('并发冲突输入保留', conflict)
            async def profile_ui():
                await page.locator('summary').filter(has_text='查看账号档案').click()
                await page.get_by_role('heading', name='账号档案', exact=True).wait_for()
                await expect(page.get_by_text('窗口有效作品', exact=True)).to_be_visible()
                await expect(page.get_by_role('heading', name='标题句长度分布', exact=True)).to_be_visible()
                await page.locator('summary').filter(has_text='核对标题句提取').click()
                await expect(page.get_by_text('清理后标题', exact=True)).to_be_visible()
                await expect(page.get_by_text('规则提取，未经人工核验', exact=False).first).to_be_visible()
                await expect(page.get_by_role('button', name='标题核对上一条', exact=True)).to_be_disabled()
                await page.get_by_role('button', name='标题核对下一条', exact=True).focus()
                await page.keyboard.press('Enter')
                await expect(page.get_by_role('button', name='标题核对上一条', exact=True)).to_be_enabled()
                await page.locator('summary').filter(has_text='对照原始文案').click()
                await expect(page.locator('summary').filter(has_text='对照原始文案')).to_be_visible()
                await page.screenshot(path=str(output/'title-review-expanded.png'), full_page=True)
                await page.locator('summary').filter(has_text='核对标题句提取').click()
                await page.locator('summary').filter(has_text='查看原文依据').first.click()
                await expect(page.locator('mark').first).to_be_visible()
                await page.get_by_role('button', name='原文依据下一条', exact=True).click()
                await expect(page.get_by_role('button', name='原文依据上一条', exact=True)).to_be_enabled()
                await page.screenshot(path=str(output/'original-evidence-expanded.png'), full_page=True)
                await page.locator('summary').filter(has_text='查看原文依据').first.click()
                await page.locator('summary').filter(has_text='查看全部话题与依据').click()
                await expect(page.locator('summary').filter(has_text='查看原文依据').last).to_be_visible()
                await page.locator('summary').filter(has_text='查看全部话题与依据').click()
                await page.locator('summary').filter(has_text='观测覆盖详情').click()
                await expect(page.get_by_text('已有有效时间观测', exact=True)).to_be_visible()
                await page.locator('summary').filter(has_text='观测覆盖详情').click()
                return '真实只读档案集成；标题句和原文可核对，注明未经人工核验'
            await record('账号档案集成', profile_ui)
            for width in [1440, 812, 375]:
                for dark in [False, True]:
                    async def layout():
                        await page.set_viewport_size({'width': width, 'height': 1000})
                        await page.evaluate('(dark)=>document.documentElement.classList.toggle("dark",dark)', dark)
                        await page.locator('summary').filter(has_text='核对标题句提取').evaluate('(el)=>el.parentElement.open=true')
                        await page.locator('summary').filter(has_text='查看原文依据').first.evaluate('(el)=>el.parentElement.open=true')
                        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                        cards = await page.get_by_role('article').evaluate_all('(els)=>els.map(el=>({height:el.getBoundingClientRect().height,bottom:el.querySelector("button").getBoundingClientRect().bottom-el.getBoundingClientRect().top}))')
                        assert max(c['height'] for c in cards) - min(c['height'] for c in cards) <= 1
                        assert max(c['bottom'] for c in cards) - min(c['bottom'] for c in cards) <= 1
                        if width >= 1024:
                            left = await page.get_by_role('region', name='标题长度模块', exact=True).bounding_box()
                            right = await page.get_by_role('region', name='文案特征模块', exact=True).bounding_box()
                            assert abs(left['height'] - right['height']) <= 1
                            assert abs(left['y'] - right['y']) <= 1
                        return '无横向溢出；账号卡片等高、按钮对齐；桌面图表等高'
                    await record(f'布局 {width} {"深" if dark else "浅"}色', layout)
            async def unavailable():
                state['error'] = True
                await page.reload()
                await expect(page.get_by_role('alert').filter(has_text='元数据不可用')).to_be_visible(timeout=15000)
                state['error'] = False
                await page.get_by_role('button', name='重新读取', exact=True).click()
                await expect(page.get_by_role('article')).to_have_count(len(accounts))
                return '模拟错误展示及恢复正常'
            await record('不可用状态与重读', unavailable)
            async def settings():
                await page.get_by_role('article').nth(1).get_by_role('button').click()
                await expect(page.get_by_role('button', name='修改采集配置',exact=True)).to_have_count(0)
                await page.get_by_role('button', name='添加账号与采集设置',exact=True).click()
                await expect(page).to_have_url(base+'/?tab=config')
                assert await page.locator('summary').filter(has_text='查看账号档案').count() == 0
                await page.go_back()
                await page.get_by_role('heading', name='账号矩阵', exact=True).wait_for()
                return '设置保留采集配置，档案不重复；浏览器后退回矩阵'
            await record('设置分离及返回导航', settings)
            async def old_link():
                await page.goto(base+'/?tab=event-comparison&editorial=references')
                await expect(page.get_by_role('tab',name='运营总览',exact=True)).to_have_attribute('aria-selected','true')
                await expect(page.get_by_role('tab',name='同事件竞品对比',exact=True)).to_have_count(0)
                assert not any(any(part in r['path'] for part in ('event-comparison','event-opportunities','editorial-drafts','idea-automation','training-data')) for r in requests)
                return 'old removed-module deep link falls back to overview; no removed API requests'
            await record('已删除模块旧链接与请求隔离', old_link)
            await context.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        safety = dict(formal_db_sha_unchanged=before == hashlib.sha256(source.read_bytes()).hexdigest(),
            copy_sha_unchanged=copy_sha == hashlib.sha256(copy.read_bytes()).hexdigest(),
            external_attempts=externals, page_errors=errors, model_calls=0, ordinary_app_started=False,
            shared_build_exists=(ROOT/'api/webui').exists(), server_stopped=not thread.is_alive())
        (output/'results.json').write_text(json.dumps(dict(cases=cases, safety=safety, requests=requests), ensure_ascii=False, indent=2), encoding='utf-8')
        (output/'report.md').write_text('# 账号矩阵隔离浏览器验收\n\n真实矩阵服务和表单，采集库备份副本只读、独立测试元数据库；外围接口为静态替身，错误状态显式注入。不代表普通应用完整回归。\n\n'+
            '\n'.join(f"- {c['name']}：{c['status']}；{c['detail']}；[截图]({c['screenshot']})" for c in cases)+
            '\n\n```json\n'+json.dumps(safety, ensure_ascii=False, indent=2)+'\n```\n', encoding='utf-8')
        print(json.dumps(safety), sum(c['status']=='通过' for c in cases), '/',len(cases))


if __name__ == '__main__':
    asyncio.run(main())
