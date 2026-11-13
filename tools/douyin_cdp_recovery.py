"""Recover only the registered collection target, before Playwright attaches."""

import asyncio
import json
from urllib.parse import urlsplit

import httpx
from websockets.asyncio.client import connect

from tools import douyin_collection_page as registry
from tools.douyin_browser_coordinator import DouyinTabLease


async def recover_registered_target(port, *, timeout=8):
    """Use browser-level CDP, without initializing any renderer or navigating."""
    async with DouyinTabLease(timeout=0):
        return await _recover_registered_target(port, timeout=timeout)


async def _recover_registered_target(port, *, timeout):
    if not isinstance(port, int) or not 1 <= port <= 65535:
        return "no_endpoint"
    target_id = registry._remembered_target()
    if not isinstance(target_id, str) or not target_id:
        return "no_registered_target"
    async with asyncio.timeout(timeout):
        async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=3) as client:
            response = await client.get(f"http://127.0.0.1:{port}/json/version")
            response.raise_for_status()
            endpoint = response.json()["webSocketDebuggerUrl"]
        parsed = urlsplit(endpoint)
        if (parsed.scheme != "ws" or parsed.hostname not in ("localhost", "127.0.0.1")
                or parsed.port != port or parsed.username or parsed.password or parsed.query
                or parsed.fragment or not parsed.path.startswith("/devtools/browser/")):
            raise ValueError("Unexpected browser debugger identity")
        async with connect(endpoint, proxy=None, open_timeout=3, close_timeout=1, max_size=2**20) as ws:
            async def command(ident, method, params=None):
                await ws.send(json.dumps({"id": ident, "method": method, "params": params or {}}))
                while True:
                    result = json.loads(await ws.recv())
                    if result.get("id") == ident:
                        if "error" in result:
                            raise RuntimeError("Browser recovery command failed")
                        return result.get("result", {})

            targets = (await command(1, "Target.getTargets")).get("targetInfos", [])
            target = next((item for item in targets if item.get("targetId") == target_id), None)
            if target is None:
                return "target_already_gone"
            url = target.get("url", "")
            host = urlsplit(url).hostname or ""
            if (target.get("type") != "page" or not (url == "about:blank"
                    or host == "douyin.com" or host.endswith(".douyin.com"))):
                return "target_identity_mismatch"
            closed = await command(2, "Target.closeTarget", {"targetId": target_id})
            if closed.get("success") is not True:
                raise RuntimeError("Registered collection target could not close")
            # Do not erase a registry replaced by another actor.
            if registry._remembered_target() == target_id:
                registry._TARGET_FILE.unlink(missing_ok=True)
            return "registered_target_closed"
