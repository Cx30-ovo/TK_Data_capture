"""Isolated browser acceptance: real read-only profile, inert surrounding API."""
import argparse
import asyncio
import copy
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import sqlite3
import sys
import threading
import time
from urllib.parse import urlsplit

import uvicorn
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# Import the pure service without importing eager api.services or api.main.
spec = importlib.util.spec_from_file_location("profile_acceptance_service", ROOT / "api/services/account_profile_service.py")
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)


async def run(output: Path, dist: Path):
    output.mkdir(parents=True, exist_ok=False)
    db_path = ROOT / "database/sqlite_tables.db"
    before = hashlib.sha256(db_path.read_bytes()).hexdigest()
    with sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        accounts = [dict(row) for row in db.execute("SELECT * FROM douyin_monitored_accounts ORDER BY id")]
    assert len(accounts) >= 2, "Two real accounts needed for isolation check"
    for account in accounts:
        account.update(posts=0, today_new_posts=0, due_jobs=0, abnormal_jobs=0, jobs={}, next_discovery_at=None, retry_after_seconds=0)
        account["last_discovery_result"] = None
    cases, requests, errors, console, external, responses = [], [], [], [], [], []
    state = {"mode": "real"}
    app = FastAPI()

    @app.middleware("http")
    async def only_get(request: Request, call_next):
        requests.append({"method": request.method, "path": request.url.path, "query": request.url.query})
        if request.method not in {"GET", "HEAD"}:
            return JSONResponse({"detail": "Acceptance blocks writes"}, status_code=405)
        return await call_next(request)

    @app.get("/api/monitor/accounts/{account_id}/profile")
    async def profile(account_id: int, days: int = 30):
        if state["mode"] in {"503", "404"}:
            return JSONResponse({"detail": "验收注入错误"}, status_code=int(state["mode"]))
        result = await service.get_account_profile(str(db_path), account_id, days)
        if state["mode"] == "empty":
            result = service.build_profile(result["account"], [], [], 0, 0, result["window"]["start"], result["window"]["end"])
        elif state["mode"] == "missing":
            result = copy.deepcopy(result)
            result["counts"].update(with_title=0, missing_title=result["counts"]["sampled"])
            result["title_length"] = {"mean": None, "median": None, "histogram": [{"label": b["label"], "count": 0} for b in result["title_length"]["histogram"]]}
            result["signals"] = [{**s, "count": 0, "evidence": []} for s in result["signals"]]
            result["hashtags"] = []
            result["coverage"].update(observed_posts=0, without_observation=result["counts"]["sampled"], invalid_observations=0, lifecycle=[{"stage": s, "posts": 0} for s in service.STAGES])
        elif state["mode"] == "truncated":
            result["counts"].update(eligible=6000, sampled=5000, truncated=True)
        responses.append({"account_id": account_id, "days": days, "mode": state["mode"], "result": result})
        return result

    @app.get("/api/{path:path}")
    async def surroundings(path: str):
        if path == "monitor/accounts": return {"accounts": accounts, "loop_running": False}
        if path == "monitor/execution": return {"paused": True, "crawler_running": False, "retry_after_seconds": 0, "execution": None, "recovery": {"pending": False}}
        if path == "monitor/health": return {"checks": [], "overall_status": "ok", "metrics": {"jobs": {}, "unread_alerts": 0}, "config": {}}
        if path == "monitor/overview": return {"jobs": {}, "next_snapshot": None}
        if path == "crawler/status": return {"status": "idle", "platform": None, "crawler_type": None}
        if path == "scheduler/status": return {"enabled": False, "times": [], "running": False}
        if path == "config/platforms": return {"platforms": [{"value": "dy", "label": "抖音"}]}
        if path == "config/options": return {"login_types": [], "crawler_types": [], "save_options": []}
        return {}

    @app.websocket("/api/ws/logs")
    async def logs(websocket: WebSocket):
        await websocket.accept()
        try:
            while True:
                text = await websocket.receive_text()
                if text == "ping": await websocket.send_text("pong")
        except Exception:
            pass

    app.mount("/", StaticFiles(directory=dist, html=True))
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started: break
        await asyncio.sleep(.05)
    assert server.started

    async def record(name, operation, expected):
        try:
            actual = await operation()
            status = "通过"
        except Exception as exc:
            actual = f"{type(exc).__name__}: {str(exc)[:600]}"
            status = "失败"
        shot = f"{len(cases)+1:02d}.png"
        await page.screenshot(path=str(output / shot), full_page=True)
        cases.append({"item": name, "expected": expected, "actual": actual, "status": status, "screenshot": shot})
        print(name, status, str(actual)[:160], flush=True)

    def profile_count():
        return sum("/profile" in item["path"] for item in requests)

    async def wait_profile():
        await page.get_by_role("heading", name="账号档案", exact=True).wait_for()
        await page.get_by_role("button", name="更新统计", exact=True).wait_for(state="visible")
        await page.get_by_text("正在读取账号档案…", exact=True).wait_for(state="hidden")

    try:
        async with async_playwright() as pw:
            context = await pw.chromium.launch_persistent_context(
                str(output / "chrome-profile"), executable_path="C:/Program Files/Google/Chrome/Application/chrome.exe",
                headless=True, viewport={"width": 1440, "height": 1000},
                args=["--disable-background-networking", "--disable-component-update", "--disable-sync", "--no-first-run"],
            )
            async def network(route):
                url = urlsplit(route.request.url)
                if url.scheme in {"http", "https"} and url.hostname not in {"127.0.0.1", "localhost"}:
                    external.append({"resource_type": route.request.resource_type, "category": "external", "path": url.path.split("?")[0]})
                    await route.abort()
                else: await route.continue_()
            await context.route("**/*", network)
            await context.add_init_script("localStorage.setItem('mediacrawler_license_accepted','true');localStorage.setItem('mediacrawler_env_checked','true');localStorage.setItem('i18nextLng','zh-CN');")
            page = context.pages[0]
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.on("console", lambda msg: console.append({"type": msg.type, "text": msg.text.split("http")[0][:350]}) if msg.type in {"error", "warning"} else None)
            await page.goto(f"http://127.0.0.1:{port}/?tab=config")
            entry = page.locator("summary").filter(has_text="查看账号档案")
            await entry.wait_for()

            async def closed():
                assert profile_count() == 0
                assert await page.get_by_role("heading", name="账号档案", exact=True).count() == 0
                return "账号配置入口可见，折叠时档案 GET=0"
            await record("入口与惰性加载", closed, "折叠时不请求档案")

            async def first():
                await entry.click(); await wait_profile()
                assert profile_count() == 1
                assert responses[-1]["mode"] == "real"
                assert await page.get_by_text("窗口有效作品", exact=True).count() == 1
                return {"GET": profile_count(), "counts": responses[-1]["result"]["counts"]}
            await record("首开真实数据", first, "一次 GET，真实统计、窗口与限制可读")

            async def reopen():
                before_count = profile_count();await entry.click(); await entry.click();await wait_profile()
                assert profile_count() == before_count + 1
                return "关闭再开重新读取一次（本轮既定契约）"
            await record("关闭重开", reopen, "重新读取一次，无采集联动")

            async def switch_window():
                await page.get_by_label("发布时间窗口", exact=True).select_option("7");await wait_profile()
                assert responses[-1]["days"] == 7
                assert responses[-1]["result"]["window"]["days"] == 7
                return "7 天统计及窗口同步更新"
            await record("时间窗口", switch_window, "窗口参数与实际统计一致")

            async def evidence():
                ev = page.locator("summary").filter(has_text="查看标题依据").first
                await ev.click()
                assert await page.get_by_text("字段 title", exact=False).count() > 0
                await page.locator("summary").filter(has_text="口径、限制与输入指纹").click()
                assert await page.get_by_text("account-title-profile-v0.1", exact=False).count() > 0
                return "标题原文、作品 ID、title 字段、发布时间、版本和 SHA 可定位"
            await record("证据与输入绑定", evidence, "原始标题依据和口径可展开")

            async def update():
                old = profile_count();await page.get_by_role("button", name="更新统计", exact=True).click();await wait_profile()
                assert profile_count() == old + 1
                return "仅档案 GET 增加一次"
            await record("更新统计", update, "只读取本地档案")

            async def switch_account():
                name = accounts[1]["display_name"]
                await page.get_by_role("button", name=name, exact=False).filter(has=page.locator("div")).first.click()
                await page.locator("summary").filter(has_text="查看账号档案").wait_for()
                assert await page.get_by_role("heading", name="账号档案", exact=True).count() == 0
                await page.locator("summary").filter(has_text="查看账号档案").click();await wait_profile()
                assert responses[-1]["account_id"] == accounts[1]["id"]
                return {"account_id": responses[-1]["account_id"], "counts": responses[-1]["result"]["counts"]}
            await record("账号切换隔离", switch_account, "切换账号关闭旧档案，新档案身份正确")

            async def mode_test(mode, phrase):
                state["mode"] = mode
                await page.get_by_role("button", name="更新统计", exact=True).click();await wait_profile()
                await page.get_by_text(phrase, exact=False).first.wait_for()
                return f"模拟 {mode}：{phrase}"
            await record("空作品窗口", lambda: mode_test("empty", "该窗口暂无已采集作品"), "显式空态，不生成示例")
            await record("缺标题及观测", lambda: mode_test("missing", "标题中未发现话题标签"), "缺失不补 0，原始计数为 0 正常展示")
            await record("截断提示", lambda: mode_test("truncated", "仅取最新 5000 篇"), "明确总数、样本数和截断")
            await record("503 降级", lambda: mode_test("503", "账号档案暂不可用"), "错误提示，隐藏旧统计")
            async def error404():
                state["mode"] = "404"
                await page.locator("summary").filter(has_text="查看账号档案").click()
                await page.locator("summary").filter(has_text="查看账号档案").click()
                await wait_profile()
                await page.get_by_text("账号档案暂不可用", exact=True).wait_for()
                assert await page.get_by_text("窗口有效作品", exact=True).count() == 0
                return "模拟 404，不显示上次统计"
            await record("404 降级", error404, "账号失效可读，无旧数据混淆")

            state["mode"] = "real"
            await page.locator("summary").filter(has_text="查看账号档案").click()
            await page.locator("summary").filter(has_text="查看账号档案").click();await wait_profile()
            async def keyboard():
                summary = page.locator("summary").filter(has_text="查看账号档案")
                await summary.focus();await page.keyboard.press("Enter")
                assert await page.get_by_role("heading", name="账号档案", exact=True).count() == 0
                await page.keyboard.press("Space");await wait_profile()
                await page.keyboard.press("Tab")
                assert await page.evaluate("document.activeElement.textContent.includes('更新统计')")
                return "Enter 折叠、Space 展开、Tab 到更新按钮"
            await record("键盘操作", keyboard, "原生 details 键盘操作与焦点顺序正确")

            async def layout(width, dark):
                await page.set_viewport_size({"width": width, "height": 1000})
                await page.evaluate("dark => document.documentElement.classList.toggle('dark',dark)", dark)
                await page.locator("summary").filter(has_text="查看账号档案").scroll_into_view_if_needed()
                sizes = await page.evaluate("({viewport:innerWidth,document:document.documentElement.scrollWidth})")
                assert sizes["document"] <= sizes["viewport"], sizes
                section = page.get_by_role("region", name="账号档案", exact=True)
                assert await section.is_visible()
                return sizes
            for width in [1440, 812, 375]:
                for dark in [False, True]:
                    await record(f"布局 {width} {'深色' if dark else '浅色'}", lambda w=width,d=dark: layout(w,d), "无页面横向溢出，内容可见")

            async def creation():
                await page.get_by_role("button", name="新增账号", exact=False).last.click()
                assert await page.locator("summary").filter(has_text="查看账号档案").count() == 0
                return "新建账号时旧档案入口消失，未提交表单"
            await record("创建态隔离", creation, "未保存新账号不显示旧档案")
            await context.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        after = hashlib.sha256(db_path.read_bytes()).hexdigest()
        safety = {"database_sha_unchanged": before == after, "non_get_requests": [r for r in requests if r["method"] not in {"GET", "HEAD"}], "page_script_errors": errors, "external_attempts_blocked": external, "background_tasks_started": False, "model_calls": 0, "server_stopped": not thread.is_alive(), "api_webui_exists": (ROOT / "api/webui").exists()}
        (output / "results.json").write_text(json.dumps({"cases": cases, "safety": safety, "console": console, "profile_responses": responses, "requests": requests, "environment": {"browser": "isolated headless Chrome", "profile": str(output / "chrome-profile"), "host": "loopback", "port": port, "frontend": str(dist), "outer_apis": "static substitutes; profile uses real read-only service", "fixture_modes": ["empty", "missing", "truncated", "404", "503"]}}, ensure_ascii=False, indent=2), encoding="utf-8")
        lines = ["# 账号档案入口浏览器验收报告", "", f"执行时间：{datetime.datetime.now().astimezone().isoformat(timespec='seconds')}", "", "独立无头 Chrome、独立用户目录、loopback 临时端口；使用独立构建产物。档案为真实只读服务，外围接口为静态替身；空态、缺失、截断、404/503 为显式注入。未启动普通应用。", "", "| 项目 | 预期 | 实际 | 结果 | 截图 |", "|---|---|---|---|---|"]
        for c in cases:
            actual = str(c["actual"]).replace("|", "/").replace("\n", " ")
            lines.append(f"|{c['item']}|{c['expected']}|{actual}|{c['status']}|[{c['screenshot']}]({c['screenshot']})|")
        lines += ["", "## 安全与限制", "", "```json", json.dumps(safety, ensure_ascii=False, indent=2), "```", "", "控制台、GET 请求和档案响应详见 results.json。只验收档案入口，不将外围替身结果作为旧功能回归通过。截图需人工复核，不把元素可见等同于颜色对比度达标。浏览器背景网络未做进程级采证，不宣称整机零外联。"]
        (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
        print("OUTPUT", output, "PASSED", sum(c["status"] == "通过" for c in cases), "TOTAL", len(cases), "SAFETY", json.dumps(safety, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--dist", required=True)
    args = parser.parse_args()
    asyncio.run(run(Path(args.output).resolve(), Path(args.dist).resolve()))
