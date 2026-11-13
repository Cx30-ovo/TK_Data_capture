"""Real isolated Chrome fault acceptance. No platform requests or application startup."""

import argparse
import asyncio
from contextlib import ExitStack, suppress
from contextvars import Context
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
import time
import traceback
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit

import httpx
from playwright.async_api import async_playwright
from websockets.asyncio.client import connect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

HTML = '''<!doctype html><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<style>body{margin:70px;font:22px system-ui;background:#f1f5f9;color:#172033}
main{padding:40px;border-radius:20px;background:white;max-width:800px}small{color:#64748b}</style>
<main><small>本机隔离验收 · 合成测试材料</small><h1>人工阅读页 · 请保留</h1>
<p id="sentinel">这段未提交内容必须在恢复前后保持一致。</p></main>'''


async def browser_command(endpoint, method, params=None):
    async with connect(endpoint, proxy=None, open_timeout=4, close_timeout=1) as ws:
        await ws.send(json.dumps({'id':1,'method':method,'params':params or {}}))
        while True:
            result = json.loads(await asyncio.wait_for(ws.recv(), 5))
            if result.get('id') == 1:
                if 'error' in result:
                    raise RuntimeError('Isolated browser command failed')
                return result.get('result', {})


async def main(args):
    run_id = args.run_id or datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3)
    if not re.fullmatch(r'[a-zA-Z0-9-]{1,80}', run_id):
        raise ValueError('Invalid run id')
    out = ROOT / 'tmp' / ('monitor-browser-acceptance-' + run_id)
    out.mkdir(parents=True, exist_ok=False)
    profile = out / 'chrome-profile'
    profile.mkdir()
    report = {'run_id':run_id,'mode':'real headless Chrome + isolated local fixtures',
              'cases':[],'observations':{},'page_errors':[],'page_external_requests':0,
              'network':{'local_fixture_requests':0,'denied_proxy_requests':0,'forwarded_requests':0},
              'model_requests':0,'formal_database_access':False,'remote_operations':False}
    processes = []
    browser = None
    playwright = None
    endpoint = None
    current_case = 'environment'
    frozen_tasks = []

    class Boundary(BaseHTTPRequestHandler):
        def log_message(self, *unused):
            pass

        def send_error(self, *args, **kwargs):
            # Chrome may close rejected CONNECT sockets before reading the body.
            with suppress(ConnectionError, OSError):
                return super().send_error(*args, **kwargs)

        def do_CONNECT(self):
            report['network']['denied_proxy_requests'] += 1
            self.send_error(503, 'External connections disabled')

        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path == '/fixture' and parsed.hostname in (None,'localhost','127.0.0.1'):
                report['network']['local_fixture_requests'] += 1
                body = HTML.encode()
                self.send_response(200)
                self.send_header('Content-Type','text/html; charset=utf-8')
                self.send_header('Content-Length',str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                report['network']['denied_proxy_requests'] += 1
                self.send_error(503, 'External connections disabled')

    boundary = ThreadingHTTPServer(('127.0.0.1', 0), Boundary)
    boundary_thread = threading.Thread(target=boundary.serve_forever, daemon=True)
    boundary_thread.start()
    proxy_port = boundary.server_address[1]

    def passed(name, expected, actual, screenshot=None):
        report['cases'].append({'name':name,'status':'pass','expected':expected,
                                'actual':actual,'screenshot':screenshot})

    async def capture(page, name):
        target = out / (name + '.png')
        await page.screenshot(path=str(target), timeout=5000)
        return target.name

    try:
        command = [str(args.chrome), '--headless=new', '--remote-debugging-address=127.0.0.1',
                   '--remote-debugging-port=0', '--user-data-dir='+str(profile),
                   '--proxy-server=http://127.0.0.1:'+str(proxy_port), '--proxy-bypass-list=<-loopback>',
                   '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1',
                   '--disable-background-networking','--disable-component-update','--disable-sync',
                   '--disable-default-apps','--disable-extensions','--disable-domain-reliability',
                   '--disable-quic','--metrics-recording-only','--no-first-run','--no-default-browser-check',
                   '--disable-features=OptimizationHints,MediaRouter,AutofillServerCommunication', 'about:blank']
        current_case = 'chrome-launch'
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        processes.append(process)
        active = profile / 'DevToolsActivePort'
        for _ in range(100):
            if active.exists():
                break
            if process.poll() is not None:
                raise RuntimeError('Isolated Chrome exited before exposing CDP')
            await asyncio.sleep(.1)
        if not active.exists():
            raise TimeoutError('Isolated Chrome did not expose CDP')
        port = int(active.read_text().splitlines()[0])
        current_case = 'cdp-http-readiness'
        async with httpx.AsyncClient(trust_env=False, timeout=1) as client:
            last_error = None
            for _ in range(30):
                try:
                    response = await client.get(f'http://127.0.0.1:{port}/json/version')
                    response.raise_for_status()
                    version = response.json()
                    break
                except (httpx.HTTPError, ValueError) as error:
                    last_error = error
                    await asyncio.sleep(.1)
            else:
                raise RuntimeError('Isolated CDP HTTP endpoint unavailable') from last_error
        endpoint = version['webSocketDebuggerUrl']
        report['browser_version'] = version.get('Browser')
        passed('独立环境','全新目录、独立 Chrome 档案、本机调试端点','目录原子创建；使用系统分配端点；未读取日常档案')

        from tools import douyin_collection_page as registry
        from tools import douyin_cdp_recovery as recovery
        from tools.douyin_browser_coordinator import DouyinTabLease, DouyinBrowserBusyError
        from tools.cdp_browser import CDPBrowserManager
        from tools.collection_errors import classify_collection_error
        from api.services import monitor_service as service_module

        # Existing project log handlers are not used for acceptance evidence.
        logger = logging.getLogger('MediaCrawler')
        with ExitStack() as stack:
            stack.enter_context(patch.object(logger,'disabled',True))
            lease_file = out / 'isolated-tab.lock'
            lease = lambda **kw: DouyinTabLease(path=lease_file, **kw)
            for module in (registry,recovery,service_module):
                stack.enter_context(patch.object(module,'DouyinTabLease',lease))
            stack.enter_context(patch.object(registry,'_TARGET_FILE',out/'collection-target.json'))
            playwright = await async_playwright().start()
            current_case = 'playwright-attachment'
            browser = await playwright.chromium.connect_over_cdp(endpoint, timeout=10000)
            context = browser.contexts[0]

            def page_request(request):
                parsed = urlsplit(request.url)
                if parsed.scheme in ('http','https') and parsed.hostname not in ('localhost','127.0.0.1'):
                    report['page_external_requests'] += 1
            context.on('request',page_request)
            context.on('page',lambda page:page.on('pageerror',lambda error:report['page_errors'].append(type(error).__name__)))
            async def block_external(route):
                parsed = urlsplit(route.request.url)
                if parsed.hostname not in ('127.0.0.1','localhost'):
                    await route.abort('blockedbyclient')
                else:
                    await route.continue_()
            await context.route('**/*',block_external)
            reader = context.pages[0]
            await reader.set_viewport_size({'width':1200,'height':800})
            await reader.set_content(HTML)
            await reader.evaluate("window.name = 'isolated-human-reader'")
            sentinel = await reader.locator('#sentinel').inner_text()
            before = await capture(reader,'01-reader-before')
            passed('真实 CDP 连接','Playwright 可连接独立 Chrome','成功读取真实页面及正文',before)

            current_case = 'registered-target'
            target = await registry.get_collection_page(context)
            assert target is not reader and target.url == 'about:blank'
            ident = registry._remembered_target()
            assert ident and await registry.get_collection_page(context) is target
            passed('受管页登记与复用','创建独立后台页并复用，不导航人工页','真实页签 ID 已登记，重复获取返回同一页')

            async def freeze(page):
                session = await context.new_cdp_session(page)
                task = asyncio.create_task(session.send('Runtime.evaluate',{'expression':'while (true) {}'}))
                frozen_tasks.append(task)
                await asyncio.sleep(.3)
                assert not task.done()
                return task

            current_case = 'hung-renderer'
            await freeze(target)
            await browser_command(endpoint,'Browser.getVersion')
            started = time.monotonic()
            try:
                probe = await playwright.chromium.connect_over_cdp(endpoint, timeout=2000)
                report['observations']['attach_while_frozen'] = 'succeeded; production attachment hang not reproduced'
                await probe.close()
            except Exception as exc:
                report['observations']['attach_while_frozen'] = type(exc).__name__
            report['observations']['frozen_attach_probe_seconds'] = round(time.monotonic()-started,3)
            passed('真实脚本线程冻结','测试页脚本停滞时浏览器级 CDP 仍可诊断','脚本任务未结束，Browser.getVersion 可响应')

            current_case = 'raw-recovery'
            outcome = await recovery.recover_registered_target(port)
            report['observations']['raw_recovery_outcome'] = outcome
            assert outcome == 'registered_target_closed'
            close_started = time.monotonic()
            for _ in range(50):
                targets = (await browser_command(endpoint,'Target.getTargets'))['targetInfos']
                present = any(item['targetId'] == ident for item in targets)
                if not present and target.is_closed():
                    break
                await asyncio.sleep(.1)
            report['observations']['raw_recovery_target_still_present'] = present
            report['observations']['raw_recovery_playwright_target_closed'] = target.is_closed()
            report['observations']['raw_recovery_reader_closed'] = reader.is_closed()
            report['observations']['raw_recovery_close_observed_seconds'] = round(time.monotonic()-close_started,3)
            assert not present and not reader.is_closed()
            assert await reader.locator('#sentinel').inner_text() == sentinel
            passed('冻结页原始 CDP 恢复','不依赖页面 JS，关闭登记页且保留人工页','真实冻结目标已关闭，阅读内容不变',await capture(reader,'02-reader-after-raw-recovery'))
            replacement = await registry.get_collection_page(context)
            assert replacement is not target and not replacement.is_closed()
            fresh = await playwright.chromium.connect_over_cdp(endpoint, timeout=5000)
            await fresh.close()
            passed('恢复后重新连接','可重新附着并创建新采集页','新页创建成功，新的 Playwright CDP 连接成功')

            current_case = 'missing-and-stale-registration'
            registry._TARGET_FILE.unlink()
            assert await recovery.recover_registered_target(port) == 'no_registered_target'
            assert not replacement.is_closed()
            passed('无登记保护','无登记时不关闭任何页','返回 no_registered_target，原页面保留')
            registry._TARGET_FILE.write_text(json.dumps({'target_id':ident}))
            assert await recovery.recover_registered_target(port) == 'target_already_gone'
            assert not replacement.is_closed() and not reader.is_closed()
            passed('过期登记保护','旧目标不存在时不关闭其他页','返回 target_already_gone，新页和人工页均保留')
            assert await registry.get_collection_page(context) is replacement

            current_case = 'foreign-url-protection'
            await replacement.goto(f'http://127.0.0.1:{proxy_port}/fixture',timeout=5000)
            assert await recovery.recover_registered_target(port) == 'target_identity_mismatch'
            await registry.reset_collection_page(context)
            assert not replacement.is_closed()
            passed('已导航页面保护','登记页变为其他网站时，原始和常规恢复均不得关闭','本机测试页面被完整保留',await capture(replacement,'03-foreign-url-preserved'))
            replacement = await registry.get_collection_page(context)

            current_case = 'cross-task-lock'
            async with lease():
                task = asyncio.create_task(recovery.recover_registered_target(port),context=Context())
                try:
                    await task
                    raise AssertionError('Expected browser lease conflict')
                except DouyinBrowserBusyError:
                    pass
            assert not replacement.is_closed()
            passed('独立任务锁冲突','其他执行上下文持锁时拒绝关闭页','返回 browser_busy，登记页保留')

            current_case = 'service-recovery'
            log_events = []
            async def log(message,level='info'):
                log_events.append({'level':level,'recovered':'浏览器已恢复' in message})
            stack.enter_context(patch.object(service_module.crawler_manager,'add_log',log))
            stack.enter_context(patch.object(service_module.config,'CDP_CONNECT_EXISTING',False))
            stack.enter_context(patch.object(service_module.config,'AUTO_CLOSE_BROWSER',False))
            stack.enter_context(patch.object(service_module.config,'BROWSER_RECOVERY_TIMEOUT_SECONDS',20))
            port_file = out/'isolated-cdp-endpoint.txt'
            port_file.write_text(str(port))
            async def forbid_launch(*unused,**kwargs):
                raise AssertionError('Acceptance must never launch a second browser profile')
            def manager(**kwargs):
                value = CDPBrowserManager(**kwargs)
                value._port_file = port_file
                value._launch_browser = forbid_launch
                return value
            stack.enter_context(patch.object(service_module,'CDPBrowserManager',manager))
            fixture = {'login':True}
            class LocalCrawler:
                index_url = 'about:blank'
                async def _get_or_create_context_page(self):
                    return await registry.get_collection_page(self.browser_context)
                async def create_douyin_client(self,unused):
                    async def pong(**kwargs):
                        if fixture.get('login_gate'):
                            fixture['login_entered'].set()
                            await fixture['login_gate'].wait()
                        return fixture['login']
                    async def close():pass
                    return SimpleNamespace(pong=pong,close_browser_pages=close)
            stack.enter_context(patch.object(service_module,'DouYinCrawler',LocalCrawler))
            service = service_module.MonitorService(out/'runtime-state.json')
            service._crawler_is_busy = lambda: False
            service.prepare_runtime_state()
            error = TimeoutError()
            error.error_code = 'browser_connection_timeout'
            await freeze(replacement)
            service._recovery.observe(classify_collection_error(error))
            service._recovery.retry_at = 0
            await asyncio.wait_for(service._recover_browser_if_due(),25)
            assert not service._recovery.pending and service._recovery.last_recovered_at
            assert replacement.is_closed() and not reader.is_closed()
            assert await reader.locator('#sentinel').inner_text() == sentinel
            passed('真实浏览器服务恢复链','服务执行原始恢复、真实附着和页签初始化','真实冻结页被替换；本机登录桩通过；恢复状态 healthy',await capture(reader,'04-reader-after-service-recovery'))

            current_case = 'guards'
            for label in ('paused','cooldown'):
                service._recovery.observe(classify_collection_error(error))
                service._recovery.retry_at = 0
                attempts = service._recovery.attempts
                service._paused = label == 'paused'
                service._risk_control_until = time.time()+10800 if label == 'cooldown' else 0
                await service._recover_browser_if_due()
                assert service._recovery.attempts == attempts
                assert service._recovery.pending
                passed('暂停保护' if label=='paused' else '冷却保护','不发起浏览器恢复，不清除控制状态','恢复次数不变，控制状态保留')
            service._paused = False
            service._risk_control_until = 0

            current_case = 'login-fixture'
            fixture['login'] = False
            service._recovery.retry_at = 0
            await service._recover_browser_if_due()
            assert service._paused and service._recovery.state == 'login_required'
            attempts = service._recovery.attempts
            await service._recover_browser_if_due()
            assert service._recovery.attempts == attempts
            passed('模拟登录失效','真实浏览器正常连接但登录桩失败时暂停，不自动绕过','状态 login_required，重复检查未自动恢复')

            current_case = 'state-and-content'
            restored = service_module.MonitorService(out/'runtime-state.json')
            restored.prepare_runtime_state()
            assert restored._paused and restored._recovery.state == 'login_required'
            assert await reader.locator('#sentinel').inner_text() == sentinel
            passed('控制状态落盘','恢复链执行后，重建服务仍保留暂停和登录状态','隔离状态文件可读取；人工页正文始终一致',await capture(reader,'05-reader-final'))

            current_case = 'initialization-cancellation'
            fixture.update(login=True,login_gate=asyncio.Event(),login_entered=asyncio.Event())
            cancelled_fetcher = service_module.DouyinMonitorFetcher()
            entering = asyncio.create_task(cancelled_fetcher.__aenter__())
            try:
                await asyncio.wait_for(fixture['login_entered'].wait(),15)
            finally:
                entering.cancel()
                with suppress(asyncio.CancelledError):
                    await asyncio.wait_for(entering,20)
            assert cancelled_fetcher._lease is None
            assert cancelled_fetcher._playwright is None and cancelled_fetcher._crawler is None
            async def independent_claim():
                async with lease(timeout=0):
                    return True
            assert await asyncio.create_task(independent_claim(),context=Context())
            await browser_command(endpoint,'Browser.getVersion')
            assert not reader.is_closed() and await reader.locator('#sentinel').inner_text() == sentinel
            passed('初始化取消与清理','取消释放连接和页签锁，保留独立 Chrome 及人工内容','真实连接初始化已取消；独立任务重新获得锁，浏览器仍响应')
            assert report['page_external_requests'] == 0
            assert not report['page_errors']
            passed('页面网络及脚本检查','测试页面无外部请求，无非预期脚本错误','页面请求只涉及本机；未发现页面脚本异常')
            report['observations']['login_scope'] = 'local fixture only; no real platform login tested'
            report['observations']['no_platform_collection'] = True
            report['observations']['service_logs'] = log_events
            await browser.close()
            browser = None
            await playwright.stop()
            playwright = None
        report['status'] = 'passed'
    except BaseException as exc:
        report['status'] = 'failed'
        report['cases'].append({'name':current_case,'status':'fail','exception_type':type(exc).__name__,
            'frames':[{'file':Path(f.filename).name,'function':f.name,'line':f.lineno} for f in traceback.extract_tb(exc.__traceback__)[-6:]]})
        # Exception text is intentionally omitted: browser errors embed endpoints.
        raise
    finally:
        if endpoint:
            with suppress(Exception):
                await browser_command(endpoint,'Browser.close')
        for process in processes:
            try:
                await asyncio.to_thread(process.wait,timeout=6)
            except subprocess.TimeoutExpired:
                process.terminate()
                await asyncio.to_thread(process.wait,timeout=4)
        for task in frozen_tasks:
            if not task.done():task.cancel()
        if frozen_tasks:
            await asyncio.gather(*frozen_tasks,return_exceptions=True)
        if browser:
            with suppress(Exception):await asyncio.wait_for(browser.close(),3)
        if playwright:
            with suppress(Exception):await asyncio.wait_for(playwright.stop(),3)
        boundary.shutdown()
        boundary.server_close()
        report['cleanup'] = {'owned_chrome_exited':all(p.poll() is not None for p in processes),'fixture_server_stopped':True}
        (out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'output':str(out),'status':report.get('status'),'passed':sum(c['status']=='pass' for c in report['cases']),
                          'failed':sum(c['status']=='fail' for c in report['cases'])},ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id')
    parser.add_argument('--chrome',type=Path,default=Path('C:/Program Files/Google/Chrome/Application/chrome.exe'))
    options = parser.parse_args()
    try:
        asyncio.run(asyncio.wait_for(main(options),180))
    except Exception as error:
        print('acceptance_failed:',type(error).__name__)
        sys.exit(1)
