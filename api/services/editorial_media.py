"""Read a known work's public media and sample actual video frames locally."""
import asyncio
import base64
import hashlib
import io
import json
import math
import re
import socket
import ipaddress
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

import httpx


MEDIA_HOSTS = ("douyin.com", "douyinvod.com", "douyinpic.com", "byteimg.com", "pstatp.com",
               "ibytedtos.com", "bytecdn.cn", "bytedance.com", "bytedance.net", "snssdk.com")


def allowed_url(url):
    try:
        part = urlsplit(url)
        host = (part.hostname or "").lower()
        return (part.scheme == "https" and not part.username and not part.password
                and part.port in (None, 443)
                and any(host == domain or host.endswith("." + domain) for domain in MEDIA_HOSTS))
    except (ValueError, TypeError):
        return False


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.values = []
    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.inside = True
    def handle_endtag(self, tag):
        if tag == "script":
            self.inside = False
    def handle_data(self, data):
        if self.inside:
            self.values.append(data)


def video_from_page(html, aweme_id):
    scripts = Scripts()
    scripts.feed(html)
    for script in scripts.values:
        raw = script.strip()
        candidates = [raw]
        if re.match(r"(?:window\.)?(?:_ROUTER_DATA|__UNIVERSAL_DATA_FOR_REHYDRATION__)\s*=", raw):
            candidates.append(raw.split("=", 1)[1].lstrip())
        # RENDER_DATA is percent encoded. Do not corrupt signed URLs inside plain JSON.
        if raw.startswith("%"):
            candidates.append(unquote(raw))
        for candidate in candidates:
            try:
                value, _ = json.JSONDecoder().raw_decode(candidate)
            except ValueError:
                continue
            stack, visited = [value], 0
            while stack and visited < 10000:
                row = stack.pop(); visited += 1
                if isinstance(row, dict):
                    if str(row.get("aweme_id") or row.get("awemeId") or "") == aweme_id:
                        video = row.get("video") or {}
                        if not isinstance(video, dict):
                            continue
                        for name in ("play_addr", "playAddr", "play_addr_h264", "download_addr", "downloadAddr"):
                            address = video.get(name)
                            urls = [address] if isinstance(address, str) else (
                                address.get("url_list") or address.get("urlList") or [] if isinstance(address, dict) else [])
                            if not isinstance(urls, list):
                                continue
                            for url in urls:
                                if isinstance(url, str) and allowed_url(url):
                                    return url
                    stack.extend(row.values())
                elif isinstance(row, list):
                    stack.extend(row)
    return ""


def sample_frames(content, aweme_id):
    import cv2  # Optional decoder; absence is handled by the cover fallback.
    with tempfile.TemporaryDirectory(prefix="editorial-video-") as folder:
        target = Path(folder) / "source.mp4"
        target.write_bytes(content)
        capture = cv2.VideoCapture(str(target))
        try:
            fps = capture.get(cv2.CAP_PROP_FPS)
            count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
            if not math.isfinite(fps) or not math.isfinite(count) or fps <= 0 or count < 1:
                return []
            frames = []
            for index in sorted({round((count - 1) * fraction / 5) for fraction in range(6)}):
                capture.set(cv2.CAP_PROP_POS_FRAMES, index)
                ok, frame = capture.read()
                if not ok:
                    continue
                height, width = frame.shape[:2]
                ratio = min(1, 768 / max(height, width))
                frame = cv2.resize(frame, (max(1, round(width*ratio)), max(1, round(height*ratio))))
                ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                if ok:
                    content = jpeg.tobytes()
                    frames.append({"id": f"{aweme_id}:frame:{index}", "kind": "video_frame",
                        "timestamp_seconds": round(index/fps, 2), "sha256": hashlib.sha256(content).hexdigest(),
                        "url": "data:image/jpeg;base64," + base64.b64encode(content).decode("ascii")})
            return frames
        finally:
            capture.release()


def cover_image(content, aweme_id):
    from PIL import Image
    with Image.open(io.BytesIO(content)) as image:
        if image.width * image.height > 24000000:
            raise ValueError("Image exceeds pixel limit")
        image = image.convert("RGB")
        image.thumbnail((1024, 1024))
        output = io.BytesIO(); image.save(output, format="JPEG", quality=80)
        jpeg = output.getvalue()
    return {"id": f"{aweme_id}:cover", "kind": "cover", "timestamp_seconds": None,
            "sha256": hashlib.sha256(jpeg).hexdigest(),
            "url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")}


class EditorialMediaLoader:
    def __init__(self, repository):
        self.repository = repository
        self.blocked_until = 0

    async def fetch(self, url, max_bytes):
        """Validate every redirect; ignore environment proxies and bound downloads."""
        async with httpx.AsyncClient(timeout=15, follow_redirects=False, trust_env=False,
                headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.douyin.com/"}) as client:
            for _ in range(4):
                if not allowed_url(url):
                    raise ValueError("Unsupported media host")
                host = urlsplit(url).hostname
                addresses = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
                if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
                    raise ValueError("Nonpublic media destination")
                async with client.stream("GET", url) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        url = urljoin(url, response.headers.get("location", "")); continue
                    if response.status_code in (403, 429):
                        self.blocked_until = asyncio.get_running_loop().time() + 1800
                    response.raise_for_status()
                    chunks, size = [], 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            raise ValueError("Media exceeds size limit")
                        chunks.append(chunk)
                    return b"".join(chunks)
            raise ValueError("Too many media redirects")

    async def __call__(self, item):
        if asyncio.get_running_loop().time() < self.blocked_until:
            return {"images": [], "status": "unavailable", "limitation": "媒体访问冷却中，保留文字分类"}
        images = []
        try:
            video_url = await self.repository.stored_video_url(item["aweme_id"])
        except Exception:
            video_url = ""
        try:
            if not video_url:
                url = item.get("canonical_url") or ""
                part = urlsplit(url)
                if (part.hostname not in ("www.douyin.com", "douyin.com")
                        or part.path != "/video/" + item["aweme_id"] or not allowed_url(url)):
                    raise ValueError("Work URL does not match ID")
                page = await self.fetch(url, 2*1024*1024)
                video_url = video_from_page(page.decode("utf-8", errors="replace"), item["aweme_id"])
            if video_url:
                content = await self.fetch(video_url, 32*1024*1024)
                images = await asyncio.to_thread(sample_frames, content, item["aweme_id"])
        except Exception:
            pass
        if images:
            return {"images": images, "status": "sampled_video", "limitation": "仅分析抽取的视频画面，不包含语音或未抽取画面"}
        try:
            if item.get("cover_url") and asyncio.get_running_loop().time() >= self.blocked_until:
                image = await self.fetch(item["cover_url"], 8*1024*1024)
                images = [await asyncio.to_thread(cover_image, image, item["aweme_id"])]
        except Exception:
            pass
        return {"images": images, "status": "cover_only" if images else "unavailable",
                "limitation": "视频未取得，仅参考封面，不能代表完整视频" if images else "视频及封面未取得，保留文字分类"}
