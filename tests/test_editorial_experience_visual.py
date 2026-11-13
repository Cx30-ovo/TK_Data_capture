"""Correction retrieval and visual fallback: temporary SQLite, synthetic media, mocked requests."""
import asyncio
import copy
import hashlib
import io
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import quote

import httpx
import pytest

from api.services.editorial_experience import retrieve_examples
from api.services import editorial_media as media
from api.services.post_editorial_service import PostEditorialService
from api.services.post_editorial_tags import assess_post
from database.monitor_repository import monitor_repository
from database.post_editorial_repository import source_sha256
from tests.test_post_editorial_service import Model, Repository, post


def example(ident="old", **changes):
    return {"aweme_id": ident, "title": "一岁宝宝学步走向妈妈爸爸", "desc": "家庭亲子日常",
            "channel": "民生", "region": "本地", "reason": "亲子生活归民生，地点仅属本例",
            "revision": 1, "source_sha256": "a" * 64, **changes}


class RefRepository(Repository):
    def __init__(self):
        super().__init__()
        self.examples = []

    async def correction_examples(self):
        return copy.deepcopy(self.examples)


class VisualModel(Model):
    def __init__(self):
        super().__init__()
        self.prompts, self.visual_calls = [], []
        self.visual_fail = False

    async def generate_json(self, **kwargs):
        self.calls += 1
        self.prompts.append(kwargs)
        return {"items": [{"aweme_id": row["aweme_id"], "channel": "待判定", "region": "待判定",
                           "channel_confidence": .3, "region_confidence": .3,
                           "channel_evidence": "", "region_evidence": ""}
                          for row in json.loads(kwargs["user_prompt"])["items"]]}

    async def generate_multimodal_json(self, **kwargs):
        self.visual_calls.append(kwargs)
        if self.visual_fail:
            raise RuntimeError("mock unavailable")
        item = json.loads(kwargs["user_prompt"])["items"][0]
        ident = item["aweme_id"]
        return {"items": [{"aweme_id": ident, "channel": "民生", "region": "本地",
                           "channel_confidence": .95, "region_confidence": .95,
                           "channel_evidence": "孩子迈步走向父母", "region_evidence": "厦门",
                           "channel_source_id": f"{ident}:frame:2", "region_source_id": f"{ident}:frame:2",
                           "channel_evidence_type": "scene", "region_evidence_type": "visible_text"}]}


def source(ident="1"):
    return {"id": f"{ident}:frame:2", "kind": "video_frame", "timestamp_seconds": 2.0,
            "sha256": "b" * 64, "url": "data:image/jpeg;base64,dGVzdA=="}


async def frames(item):
    return {"images": [source(item["aweme_id"])], "status": "sampled_video", "limitation": "抽样画面，无语音"}


def sample(**changes):
    return SimpleNamespace(**{"aweme_id": "1", "title": "看这一幕", "desc": "",
                             "canonical_url": "https://www.douyin.com/video/1", "cover_url": None, **changes})


def test_retrieval_relevance_self_exclusion_limit_and_determinism():
    query = {"aweme_id": "current", "title": "萌娃宝宝学步，走向妈妈爸爸", "desc": "亲子生活"}
    refs = [example("current"), example("1"), example("2"), example("3"), example("4"),
            example("unrelated", title="量子芯片研究进展", desc="科学研发")]
    selected = retrieve_examples(query, refs)
    assert [row["aweme_id"] for row in selected] == ["1", "2", "3"]
    assert selected == retrieve_examples(query, list(reversed(refs)))
    assert not retrieve_examples({**query, "title": "", "desc": ""}, refs)


@pytest.mark.asyncio
async def test_classifier_never_uses_experience_or_media_even_if_provider_is_configured():
    model,repo=VisualModel(),RefRepository()
    repo.examples=[example()]
    repo.correction_examples=AsyncMock(side_effect=AssertionError("No correction references"))
    loader=AsyncMock(side_effect=AssertionError("No media"))
    service=PostEditorialService(model,repo,loader)
    for p in [sample(),sample(title="12345678"),sample(title="宝宝学步走向父母")]:
        result=(await service.enrich([p]))[p.aweme_id]
        assert result["tag_method"]=="rules_v3"
        assert result["visual_status"] is None and not result["tag_experience_refs"]
    assert model.calls==0 and not model.visual_calls
    assert not loader.called and not repo.correction_examples.called
    assert service.worker is None and not repo.rows


@pytest.mark.parametrize("url,allowed", [
    ("https://www.douyin.com/video/1", True), ("https://v.douyinvod.com/a.mp4", True),
    ("http://www.douyin.com/video/1", False), ("https://www.douyin.com.evil.test/a", False),
    ("https://user:pass@www.douyin.com/a", False), ("https://localhost/a", False),
    ("https://www.douyin.com:8443/a", False), ("file:///test.mp4", False),
])
def test_media_url_boundary(url, allowed):
    assert bool(media.allowed_url(url)) == allowed


def test_page_parsing_binds_id_and_preserves_signed_urls():
    url = "https://v.douyinvod.com/a.mp4?sign=a%2Fb"
    value = json.dumps({"aweme_id": "1", "video": {"play_addr": {"url_list": [url]}}})
    for raw in (value, quote(value), "window._ROUTER_DATA = " + value + ";"):
        assert media.video_from_page("<script>" + raw + "</script>", "1") == url
    assert not media.video_from_page("<script>" + value + "</script>", "2")
    assert not media.video_from_page('<script>{"aweme_id":"1","video":"bad"}</script>', "1")


@pytest.mark.asyncio
async def test_media_http_bounds_redirects_dns_and_risk_cooldown(monkeypatch):
    original = httpx.AsyncClient
    state = {"mode": "ok", "calls": 0}
    def handler(request):
        state["calls"] += 1
        if state["mode"] == "redirect":
            return httpx.Response(302, headers={"location": "https://private.invalid/media"})
        return httpx.Response(403 if state["mode"] == "risk" else 200, content=b"a" * 12)
    monkeypatch.setattr(media.httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    dns = AsyncMock(return_value=[(2, 1, 6, "", ("1.1.1.1", 443))])
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", dns)
    loader = media.EditorialMediaLoader(RefRepository())
    url = "https://v.douyinvod.com/a.mp4"
    assert await loader.fetch(url, 12) == b"a" * 12
    with pytest.raises(ValueError, match="size limit"):
        await loader.fetch(url, 11)
    state["mode"] = "redirect"
    with pytest.raises(ValueError, match="Unsupported media host"):
        await loader.fetch(url, 100)
    state["mode"] = "risk"
    with pytest.raises(httpx.HTTPStatusError):
        await loader.fetch(url, 100)
    calls = state["calls"]
    assert (await loader({"aweme_id": "1"}))["status"] == "unavailable"
    assert state["calls"] == calls
    dns.return_value = [(2, 1, 6, "", ("127.0.0.1", 443))]
    with pytest.raises(ValueError, match="Nonpublic"):
        await loader.fetch(url, 100)


@pytest.mark.asyncio
async def test_video_unavailable_cover_fallback_and_no_false_watched_claim(monkeypatch):
    from PIL import Image
    output = io.BytesIO(); Image.new("RGB", (20, 20)).save(output, format="PNG")
    repo = RefRepository(); repo.stored_video_url = AsyncMock(return_value="https://v.douyinvod.com/a.mp4")
    loader = media.EditorialMediaLoader(repo)
    loader.fetch = AsyncMock(return_value=output.getvalue())
    monkeypatch.setattr(media, "sample_frames", lambda *args: (_ for _ in ()).throw(ImportError("No decoder")))
    result = await loader({"aweme_id": "1", "cover_url": "https://a.douyinpic.com/a.jpg"})
    assert result["status"] == "cover_only" and result["images"][0]["kind"] == "cover"
    assert "不能代表完整视频" in result["limitation"]
    assert len(result["images"][0]["sha256"]) == 64


@pytest.mark.asyncio
async def test_mismatched_work_url_is_never_fetched():
    repo = RefRepository(); repo.stored_video_url = AsyncMock(return_value="")
    loader = media.EditorialMediaLoader(repo)
    loader.fetch = AsyncMock(side_effect=AssertionError("Must not fetch"))
    result = await loader({"aweme_id": "1", "canonical_url": "https://www.douyin.com/video/2"})
    assert result["status"] == "unavailable" and not loader.fetch.called


def test_actual_video_sampling_has_timestamps_hashes_and_bounded_frames(tmp_path):
    import cv2
    import numpy as np
    target = tmp_path / "generated.avi"
    writer = cv2.VideoWriter(str(target), cv2.VideoWriter_fourcc(*"MJPG"), 10, (48, 48))
    assert writer.isOpened()
    for index in range(31):
        writer.write(np.full((48, 48, 3), index * 7, dtype=np.uint8))
    writer.release()
    frames = media.sample_frames(target.read_bytes(), "1")
    assert len(frames) == 6 and frames[0]["timestamp_seconds"] == 0 and frames[-1]["timestamp_seconds"] == 3
    import base64
    assert all(hashlib.sha256(base64.b64decode(frame["url"].split(",", 1)[1])).hexdigest() == frame["sha256"] for frame in frames)
