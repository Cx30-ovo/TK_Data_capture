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
from tests.test_post_editorial_correction import isolated, payload, snapshot
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
async def test_only_active_current_corrections_are_retrieved_without_writes(isolated):
    client, _, repo, path = isolated
    request = await payload(client)
    await client.put("/monitor/posts/123/editorial-tags", json=request)
    baseline = snapshot(path)
    refs = await repo.correction_examples()
    assert len(refs) == 1 and refs[0]["channel"] == "民生"
    assert snapshot(path) == baseline
    await client.put("/monitor/posts/123/editorial-tags", json={"mode": "automatic", "expected_revision": 1,
                                                             "source_sha256": request["source_sha256"]})
    assert not await repo.correction_examples()
    await client.put("/monitor/posts/123/editorial-tags", json={**request, "expected_revision": 2})
    await monitor_repository.upsert_post(aweme_id="123", sec_user_id="sample-account", title="改后的标题",
                                        desc="已改变", create_time=1, canonical_url="https://www.douyin.com/video/123")
    assert not await repo.correction_examples()


@pytest.mark.asyncio
async def test_reference_prompt_cache_revision_reset_and_no_copying_location():
    model, repo = VisualModel(), RefRepository()
    repo.examples = [example()]
    p = post(title="宝宝学步走向妈妈爸爸")
    service = PostEditorialService(model, repo)
    await service.enrich([p]); await service.worker
    refs = json.loads(model.prompts[0]["user_prompt"])["items"][0]["reference_examples"]
    assert refs[0]["aweme_id"] == "old"
    result = (await service.enrich([p]))["1"]
    assert result["region"] == "待判定"
    assert result["tag_experience_refs"][0]["revision"] == 1
    key = service.cache_key(p)
    repo.examples[0]["revision"] = 2
    await service.enrich([p]); await service.worker
    assert service.cache_key(p) != key and model.calls == 2
    repo.examples = []
    await service.enrich([p]); await service.worker
    assert not (await service.enrich([p]))["1"]["tag_experience_refs"]
    await service.stop()


@pytest.mark.asyncio
async def test_text_then_same_model_visual_cached_and_no_image_bytes_persisted():
    model, repo = VisualModel(), RefRepository()
    loader = AsyncMock(side_effect=frames)
    service = PostEditorialService(model, repo, loader)
    p = sample()
    await service.enrich([p]); await service.worker
    result = (await service.enrich([p]))["1"]
    assert result["channel"] == "民生" and result["region"] == "本地"
    assert model.calls == len(model.visual_calls) == loader.await_count == 1
    assert model.visual_calls[0]["images"][0]["url"].startswith("data:image/")
    assert result["region_evidence_source"]["sha256"] == "b" * 64
    assert result["channel_evidence_source"]["timestamp_seconds"] == 2
    assert result["visual_status"] == "sampled_video" and result["tag_status"] == "resolved"
    assert "data:image/" not in json.dumps(repo.rows)
    assert "canonical_url" not in model.prompts[0]["user_prompt"]
    assert "不代表当前作品的事实" in model.prompts[0]["system_prompt"]
    await service.stop()


@pytest.mark.asyncio
async def test_visual_failure_preserves_valid_text_and_other_batch_results():
    class TextModel(VisualModel):
        async def generate_json(self, **kwargs):
            result = await super().generate_json(**kwargs)
            for row in result["items"]:
                row.update(channel="民生", channel_confidence=.95, channel_evidence="宝宝学步")
            return result
    model, repo = TextModel(), RefRepository()
    model.visual_fail = True
    service = PostEditorialService(model, repo, frames)
    works = [sample(title="宝宝学步"), sample(aweme_id="2", title="宝宝学步", canonical_url=None)]
    await service.enrich(works); await service.worker
    result = await service.enrich(works)
    assert all(value["channel"] == "民生" for value in result.values())
    assert result["1"]["visual_status"] == "analysis_failed"
    assert result["1"]["region"] == "待判定" and "visual_status" not in result["2"]
    assert len(model.visual_calls) == 1
    await service.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["disabled", "manual", "resolved"])
async def test_no_media_or_model_calls_for_protected_or_unnecessary_work(mode):
    from database.post_editorial_repository import manual_key
    model, repo, loader = VisualModel(), RefRepository(), AsyncMock(side_effect=AssertionError("No media"))
    p = sample(title="厦门新增公交线路" if mode == "resolved" else "这一幕")
    if mode == "disabled":
        model.enabled = False
    if mode == "manual":
        await repo.save(manual_key("1"), "1", {"active": True, "source_sha256": source_sha256(p),
                                               "channel": "民生", "region": "待判定", "reason": "已纠正", "revision": 1})
    service = PostEditorialService(model, repo, loader)
    await service.enrich([p])
    assert service.worker is None and model.calls == 0 and not loader.called


@pytest.mark.asyncio
async def test_unavailable_media_retries_are_throttled_and_url_changes_invalidate():
    model, repo = VisualModel(), RefRepository()
    loader = AsyncMock(return_value={"images": [], "status": "unavailable", "limitation": "未取得"})
    service = PostEditorialService(model, repo, loader)
    p = sample()
    await service.enrich([p]); await service.worker
    result = (await service.enrich([p]))["1"]
    assert result["visual_status"] == "unavailable" and result["channel"] == "待判定"
    assert model.calls == loader.await_count == 1
    assert service.cache_key(p) != service.cache_key(sample(cover_url="https://a.douyinpic.com/a.jpg"))
    await service.stop()


@pytest.mark.asyncio
async def test_contrary_channel_experience_reviews_clear_rule_without_copying_example_region():
    model, repo = VisualModel(), RefRepository()
    p = post(title="厦门发布科技进展")
    assert not assess_post(p.title)["ambiguous_fields"]
    repo.examples = [example(title=p.title, desc="", channel="经济", region="国际")]
    service = PostEditorialService(model, repo)
    await service.enrich([p]); await service.worker
    sent = json.loads(model.prompts[0]["user_prompt"])["items"][0]
    assert sent["ambiguous_fields"] == ["channel"]
    assert (await service.enrich([p]))["1"]["region"] == "本地"
    await service.stop()


@pytest.mark.asyncio
async def test_resolved_text_skips_visual_even_when_url_exists():
    model, repo = Model(), RefRepository()
    loader = AsyncMock(side_effect=AssertionError("Unnecessary media"))
    service = PostEditorialService(model, repo, loader)
    await service.enrich([sample(title="日本游客在厦门旅游")]); await service.worker
    assert (await service.enrich([sample(title="日本游客在厦门旅游")]))["1"]["tag_status"] == "resolved"
    assert not loader.called
    await service.stop()


@pytest.mark.asyncio
async def test_numeric_title_with_media_can_use_actual_frames():
    model, repo = VisualModel(), RefRepository()
    service = PostEditorialService(model, repo, frames)
    p = sample(title="12345678")
    await service.enrich([p]); await service.worker
    assert (await service.enrich([p]))["1"]["channel"] == "民生"
    assert len(model.visual_calls) == 1
    await service.stop()


@pytest.mark.asyncio
async def test_outdated_manual_correction_does_not_block_visual_but_current_one_does():
    from database.post_editorial_repository import manual_key
    model, repo = VisualModel(), RefRepository()
    p = sample()
    await repo.save(manual_key("1"), "1", {"active": True, "source_sha256": "c" * 64,
                                           "channel": "教育", "region": "本省", "reason": "旧文案", "revision": 1})
    loader = AsyncMock(side_effect=frames)
    service = PostEditorialService(model, repo, loader)
    await service.enrich([p]); await service.worker
    assert (await service.enrich([p]))["1"]["channel"] == "民生" and loader.await_count == 1
    item = {"aweme_id": "1", "title": p.title, "desc": "", "source_sha256": source_sha256(p),
            "canonical_url": p.canonical_url}
    await repo.save(manual_key("1"), "1", {"active": True, "source_sha256": source_sha256(p),
                                           "channel": "教育", "region": "本省", "reason": "已核对", "revision": 2})
    await service.review_visual(item, assess_post(p.title))
    assert loader.await_count == 1
    await service.stop()


def visual_case(**changes):
    item = {"aweme_id": "1", "title": "这一幕", "desc": "", "ambiguous_fields": ["channel", "region"]}
    tags = {**assess_post(item["title"]), "channel": "待判定", "region": "待判定",
            "ambiguous_fields": ["channel", "region"]}
    row = {"aweme_id": "1", "channel": "民生", "channel_confidence": .95,
           "channel_evidence": "孩子走向父母", "channel_source_id": "1:frame:2", "channel_evidence_type": "scene",
           "region": "本地", "region_confidence": .95, "region_evidence": "厦门",
           "region_source_id": "1:frame:2", "region_evidence_type": "visible_text", **changes}
    manifest = [{key: value for key, value in source().items() if key != "url"}]
    return PostEditorialService.validate_visual({"items": [row]}, item, tags, manifest)


@pytest.mark.parametrize("changes", [
    {"region_source_id": "old:frame:2"}, {"region_source_id": "made-up"},
    {"region_evidence_type": "scene"}, {"region_evidence": "闽南话"},
    {"region_source_id": "text"}, {"region_confidence": .79}, {"region_confidence": True},
    {"region_confidence": float("nan")}, {"region_evidence": ""},
])
def test_visual_location_requires_current_image_visible_place_and_threshold(changes):
    result = visual_case(**changes)
    assert result["region"] == "待判定" and result["channel"] == "民生"


def test_visual_cannot_change_already_resolved_text_fields():
    item = {"aweme_id": "1", "title": "民生", "desc": ""}
    tags = {"channel": "民生", "region": "待判定", "ambiguous_fields": ["region"], "ai_reviewed_fields": ["channel"]}
    row = {"aweme_id": "1", "channel": "经济", "channel_confidence": 1,
           "channel_evidence": "经济", "channel_source_id": "1:frame:2", "channel_evidence_type": "scene"}
    assert PostEditorialService.validate_visual({"items": [row]}, item, tags, [source()])["channel"] == "民生"


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
