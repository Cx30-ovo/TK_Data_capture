"""Rule-only classification: model/cache/correction/media must never be consulted."""
import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from api.services.post_editorial_service import PostEditorialService
from api.services.post_editorial_tags import assess_post
from database.post_editorial_repository import manual_key


def post(id="1", title="日本游客在厦门旅游", desc=""):
    return SimpleNamespace(aweme_id=id, title=title, desc=desc)


class Repository:
    def __init__(self):
        self.rows = {}

    async def load(self, keys):
        return {key: copy.deepcopy(self.rows[key]) for key in keys if key in self.rows}

    async def save(self, key, post_id, tags, retry_at=0):
        self.rows[key] = {"tags": copy.deepcopy(tags), "retry_at": retry_at}

    async def load_manual(self, ids):
        return {ident: copy.deepcopy(self.rows[manual_key(ident)]["tags"])
                for ident in ids if manual_key(ident) in self.rows}


class Model:
    def __init__(self, enabled=True, fail=False):
        self.calls = 0
        self.enabled = enabled
        self.fail = fail
        self.version = "test-model"
        self.gate = None

    def get_status(self):
        return {"enabled": self.enabled, "configured": self.enabled,
                "provider": "test", "model": self.version, "base_url": "http://test"}

    async def generate_json(self, **kwargs):
        self.calls += 1
        if self.gate:
            await self.gate.wait()
        if self.fail:
            raise RuntimeError("provider failure")
        return {"items": [dict(aweme_id=row["aweme_id"], channel="文旅", region="本地",
                    channel_confidence=.95, region_confidence=.95,
                    channel_evidence="旅游", region_evidence="在厦门", reason="事件发生在厦门")
                for row in json.loads(kwargs["user_prompt"])["items"]]}



@pytest.mark.asyncio
@pytest.mark.parametrize("title,channel,region", [
    ("厦门新增公交线路", "民生", "本地"),
    ("日本游客在厦门旅游", "文旅", "本地"),
    ("宝宝迈出第一步走向父母", "民生", "待判定"),
    ("妈妈带宝宝到厦门医院治疗", "健康", "本地"),
    ("这一幕令人感动", "待判定", "待判定"),
    ("1234567890", "待判定", "待判定"),
])
async def test_all_inputs_are_synchronous_rules_without_io(title,channel,region):
    guard=Mock(side_effect=AssertionError("Classification must not use dependencies"))
    model=SimpleNamespace(get_status=guard,generate_json=guard,generate_multimodal_json=guard)
    repo=SimpleNamespace(load=guard,save=guard,load_manual=guard,correction_examples=guard)
    loader=AsyncMock(side_effect=AssertionError("No media"))
    service=PostEditorialService(model,repo,loader)
    sample=post(title=title)
    sample.canonical_url="https://www.douyin.com/video/1"
    sample.cover_url="https://example.invalid/cover.jpg"
    result=(await service.enrich([sample]))["1"]
    assert (result["channel"],result["region"])==(channel,region)
    assert result==await service.read_for_correction(sample)
    assert result["tag_method"]=="rules_v3"
    assert result["classification_mode"]=="automatic_rules"
    assert result["tag_status"] in ("resolved","uncertain")
    assert not result["tag_experience_refs"] and result["manual_status"]=="none"
    assert not guard.called and not loader.called
    assert service.worker is None and service.queue.empty() and not service.pending
    await service.stop()


@pytest.mark.asyncio
async def test_legacy_manual_ai_and_visual_results_stay_untouched_and_ignored():
    repo=Repository()
    sample=post(title="厦门新增公交线路")
    service=PostEditorialService(Model(),repo)
    for key in (manual_key("1"),"legacy-ai-key",service.cache_key(sample)):
        await repo.save(key,"1",{"active":True,"channel":"文娱","region":"国际","tag_method":"rules_ai_visual"})
    before=copy.deepcopy(repo.rows)
    for _ in range(3):
        result=(await service.enrich([sample]))["1"]
        assert result["channel"]=="民生" and result["region"]=="本地"
        assert result["manual_status"]=="none" and result["tag_confidence"]=={}
    assert repo.rows==before


@pytest.mark.asyncio
async def test_empty_batch_and_new_instance_have_no_background_work():
    service=PostEditorialService()
    assert await service.enrich([])=={}
    p=post()
    assert await service.enrich([p])==await PostEditorialService().enrich([p])
    assert service.worker is None


def test_rule_identity_changes_with_content_and_version_not_provider(monkeypatch):
    from api.services import post_editorial_service as module
    model=Model();service=PostEditorialService(model,Repository());p=post()
    key=service.cache_key(p)
    model.version="another-provider"
    assert key==service.cache_key(p)
    assert key!=service.cache_key(post(title="新文案"))
    monkeypatch.setattr(module,"VERSION","editorial-rules-future")
    assert key!=service.cache_key(p)


@pytest.mark.asyncio
async def test_rule_update_is_visible_without_migration_or_backfill(monkeypatch):
    from api.services import post_editorial_service as module
    p=post();repo=Repository();service=PostEditorialService(Model(),repo)
    original=await service.enrich([p])
    monkeypatch.setattr(module,"assess_post",lambda *args:{**assess_post(*args),"tag_rule_version":"future-rules"})
    newer=await service.enrich([p])
    assert newer["1"]["tag_rule_version"]=="future-rules"
    assert original["1"]["tag_rule_version"]!="future-rules"
    assert repo.rows=={}


@pytest.mark.asyncio
async def test_repository_persists_and_upserts_without_duplicate_rows(tmp_path, monkeypatch):
    from database import db_session
    from database.models import PostEditorialLabel
    from database.post_editorial_repository import PostEditorialRepository
    monkeypatch.setitem(db_session.sqlite_db_config, "db_path", str(tmp_path / "tags.db"))
    old = db_session._engines.pop("sqlite", None)
    try:
        engine = db_session.get_async_engine("sqlite")
        async with engine.begin() as conn:
            await conn.run_sync(PostEditorialLabel.__table__.create)
        repo = PostEditorialRepository()
        await repo.save("abc", "1", {"channel": "民生"})
        await repo.save("abc", "1", {"channel": "文旅"})
        assert (await PostEditorialRepository().load(["abc"]))["abc"]["tags"]["channel"] == "文旅"
    finally:
        engine = db_session._engines.pop("sqlite", None)
        if engine:
            await engine.dispose()
        if old:
            db_session._engines["sqlite"] = old
