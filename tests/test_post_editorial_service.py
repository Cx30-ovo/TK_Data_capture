import asyncio
import copy
import json
from types import SimpleNamespace

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


def test_ambiguity_detection():
    assert not assess_post("厦门新增公交线路")["ambiguous_fields"]
    assert not assess_post("福建发布经济发展数据")["ambiguous_fields"]
    assert "region" in assess_post("日本游客在厦门旅游")["ambiguous_fields"]
    assert assess_post("厦门动物居民的生物圈")["channel"] == "环境生态"
    assert not assess_post("厦门动物居民的生物圈")["ambiguous_fields"]
    assert "region" in assess_post("韩国瑜出席活动")["ambiguous_fields"]
    assert "region" in assess_post("这个故事令人感动")["ambiguous_fields"]
    assert assess_post("厦门经济舱服务升级")["channel"] == "民生"
    assert "channel" in assess_post("厦门这一幕令人感动")["ambiguous_fields"]


@pytest.mark.asyncio
async def test_clear_rules_never_call_ai():
    model, repo = Model(), Repository()
    service = PostEditorialService(model, repo)
    tags = await service.enrich([post(title="福建发布经济发展数据")])
    assert tags["1"]["tag_status"] == "resolved"
    assert tags["1"]["region"] == "本省"
    assert model.calls == 0 and service.worker is None


@pytest.mark.asyncio
async def test_background_dedup_cache_and_clear_fields_preserved():
    model, repo = Model(), Repository()
    model.gate = asyncio.Event()
    service = PostEditorialService(model, repo)
    p = post()
    try:
        initial = await asyncio.wait_for(service.enrich([p]), .5)
        assert initial["1"]["tag_status"] == "pending"
        await service.enrich([p])
        assert len(service.pending) == 1
        model.gate.set()
        await asyncio.wait_for(service.worker, 2)
        result = (await service.enrich([p]))["1"]
        assert model.calls == 1
        assert result["region"] == "本地"
        assert result["channel"] == "文旅"
        assert result["tag_method"] == "rules_ai"
        assert result["tag_status"] == "resolved"
        # Persisted result survives a new service instance.
        other = PostEditorialService(Model(), repo)
        assert (await other.enrich([p]))["1"] == result
        assert other.worker is None
        # Title edits and model changes invalidate cache.
        assert service.cache_key(p) != service.cache_key(post(title="不同标题"))
        key = service.cache_key(p)
        model.version = "new-model"
        assert key != service.cache_key(p)
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_unavailable_model_does_not_queue_or_fake_ai_result():
    service = PostEditorialService(Model(enabled=False), Repository())
    result = (await service.enrich([post()]))["1"]
    assert result["tag_status"] == "ai_unavailable"
    assert result["tag_method"] == "rules_v2"
    assert service.worker is None


@pytest.mark.asyncio
@pytest.mark.parametrize("title,channel", [
    ("妈妈：叫妈妈！宝宝：爸爸！我不仅叫爸，我还字正腔圆", "民生"),
    ("一岁萌娃迈出人生第一步，跌跌撞撞走向父母", "民生"),
    ("厦门幼儿园萌娃向爸爸展示自己的玩具", "民生"),
    ("妈妈带宝宝到厦门医院治疗", "健康"),
    ("厦门幼儿园向父母公布招生安排", "教育"),
    ("厦门法院审理父母抚养权诉讼", "法治"),
    ("电视剧里的妈妈和宝宝迎来大结局", "文娱"),
    ("厦门双十中学的旧日风华，泛黄画里有青春", "文旅"),
    ("厦门中学公开旧照用于历史课堂教学", "教育"),
    ("野生动物与幼崽相依的亲情", "环境生态"),
])
async def test_semantic_review_can_resolve_context_and_preserve_independent_location(title, channel):
    class AnswerModel(Model):
        async def generate_json(self, **kwargs):
            self.calls += 1
            self.system_prompt = kwargs["system_prompt"]
            rows = json.loads(kwargs["user_prompt"])["items"]
            return {"items": [{"aweme_id": row["aweme_id"], "channel": channel,
                               "channel_confidence": .95, "channel_evidence": row["title"],
                               "region": "待判定", "region_confidence": .5,
                               "region_evidence": "", "reason": "按核心内容区分频道，地点单独判断。"}
                              for row in rows]}

    model, repo = AnswerModel(), Repository()
    service = PostEditorialService(model, repo)
    sample = post(title=title)
    initial = assess_post(title)
    try:
        assert (await service.enrich([sample]))["1"]["tag_status"] == "pending"
        await asyncio.wait_for(service.worker, 2)
        result = (await service.enrich([sample]))["1"]
        assert result["channel"] == channel
        assert result["channel_evidence"] == title
        assert result["ai_reviewed_fields"] == ["channel"]
        assert result["region"] == initial["region"]
        assert result["tag_status"] == ("uncertain" if initial["region"] == "待判定" else "resolved")
        assert "频道和地域独立判断" in model.system_prompt
        assert "不以是否属于硬新闻" in model.system_prompt
        assert model.calls == 1
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_updated_policy_requeues_old_unknown_cache_without_rewriting_it(monkeypatch):
    from api.services import post_editorial_service as module

    model, repo = Model(), Repository()
    service = PostEditorialService(model, repo)
    sample = post()
    with monkeypatch.context() as old:
        old.setattr(module, "VERSION", "editorial-hybrid-v4.2-marine-ecology")
        old_key = service.cache_key(sample)
    await repo.save(old_key, sample.aweme_id, {**assess_post(sample.title), "tag_status": "uncertain"})
    original = copy.deepcopy(repo.rows[old_key])
    try:
        assert old_key != service.cache_key(sample)
        assert (await service.enrich([sample]))["1"]["tag_status"] == "pending"
        await asyncio.wait_for(service.worker, 2)
        assert (await service.enrich([sample]))["1"]["region"] == "本地"
        assert model.calls == 1
        assert repo.rows[old_key] == original
    finally:
        await service.stop()


@pytest.mark.parametrize("confidence,accepted", [(.79, False), (.8, True), (.95, True)])
def test_clear_channel_is_independent_of_unknown_location_and_keeps_acceptance_threshold(confidence, accepted):
    title = "宝宝迈出第一步走向父母"
    item = {"aweme_id": "1", "title": title, "desc": "", "rules": assess_post(title),
            "ambiguous_fields": ["channel", "region"]}
    row = {"aweme_id": "1", "channel": "民生", "channel_confidence": confidence,
           "channel_evidence": "宝宝迈出第一步", "region": "待判定",
           "region_confidence": .5, "region_evidence": ""}
    result = PostEditorialService.validate({"items": [row]}, [("key", item)])["1"]
    assert result["channel"] == ("民生" if accepted else "待判定")
    assert result["region"] == "待判定"
    assert result["tag_status"] == "uncertain"


def test_prompt_example_cannot_replace_evidence_from_current_post():
    title = "孩子在客厅开心地笑了"
    item = {"aweme_id": "1", "title": title, "desc": "", "rules": assess_post(title),
            "ambiguous_fields": ["channel"]}
    row = {"aweme_id": "1", "channel": "民生", "channel_confidence": .99,
           "channel_evidence": "一岁萌娃迈出人生第一步，跌跌撞撞走向父母"}
    result = PostEditorialService.validate({"items": [row]}, [("key", item)])["1"]
    assert result["channel"] == "待判定"
    assert result["channel_evidence"] == ""


def batch_and_answer(**changes):
    p = post()
    batch = [("key", {"aweme_id": "1", "title": p.title, "desc": "",
                      "rules": assess_post(p.title), "ambiguous_fields": ["region"]})]
    row = dict(aweme_id="1", channel="经济", region="本地", channel_confidence=.99,
               region_confidence=.95, region_evidence="在厦门", channel_evidence="虚构内容")
    row.update(changes)
    return batch, {"items": [row]}


def test_ai_only_overrides_ambiguous_fields():
    batch, payload = batch_and_answer()
    result = PostEditorialService.validate(payload, batch)["1"]
    assert result["channel"] == "文旅"  # Ignores attempted overwrite of clear rule field.
    assert result["region"] == "本地"


@pytest.mark.parametrize("channel", ["科技", "体育", "教育", "法治", "文娱"])
def test_new_channel_requires_verbatim_evidence(channel):
    title = "厦门发布新内容"
    batch = [("key", {"aweme_id": "1", "title": title, "desc": "",
                       "rules": assess_post(title), "ambiguous_fields": ["channel"]})]
    row = {"aweme_id": "1", "channel": channel, "channel_confidence": .95,
           "channel_evidence": "发布新内容"}
    assert PostEditorialService.validate({"items": [row]}, batch)["1"]["channel"] == channel
    row["channel_evidence"] = "虚构的原文"
    assert PostEditorialService.validate({"items": [row]}, batch)["1"]["channel"] == "待判定"
    row["channel"] = "综合"
    with pytest.raises(ValueError):
        PostEditorialService.validate({"items": [row]}, batch)


def test_one_bad_row_does_not_discard_other_valid_reviews():
    batch, payload = batch_and_answer()
    other = copy.deepcopy(batch[0][1])
    other["aweme_id"] = "2"
    batch.append(("key2", other))
    payload["items"].append({"aweme_id": "2", "region": "无效标签"})
    result = PostEditorialService.validate_partial(payload, batch)
    assert set(result) == {"1"}
    assert result["1"]["region"] == "本地"
    payload["items"].append(payload["items"][0])
    assert PostEditorialService.validate_partial(payload, batch) == {}


def test_missing_row_can_be_retried_independently():
    batch, payload = batch_and_answer()
    other = copy.deepcopy(batch[0][1])
    other["aweme_id"] = "2"
    assert set(PostEditorialService.validate_partial(payload, batch + [("key2", other)])) == {"1"}


@pytest.mark.asyncio
async def test_id_only_content_does_not_spend_model_calls():
    model = Model()
    service = PostEditorialService(model, Repository())
    tags = await service.enrich([post(title="7703159627600530698")])
    assert tags["1"]["tag_status"] == "insufficient"
    assert model.calls == 0 and service.worker is None


def test_ai_cannot_infer_province_from_dialect_or_event_name_alone():
    title = "微信输入法支持闽南话识别"
    rules = assess_post(title)
    batch = [("key", {"aweme_id": "1", "title": title, "desc": "", "rules": rules,
                       "ambiguous_fields": ["region"]})]
    payload = {"items": [{"aweme_id": "1", "region": "本省", "region_confidence": .99,
                          "region_evidence": "闽南话"}]}
    result = PostEditorialService.validate(payload, batch)["1"]
    assert result["region"] == "待判定"


@pytest.mark.parametrize("changes", [
    {"region_confidence": .7}, {"region_evidence": "不在原文里的证据"},
    {"region_evidence": ""}, {"region": "待判定"},
])
def test_low_confidence_or_invented_evidence_remains_unknown(changes):
    batch, payload = batch_and_answer(**changes)
    result = PostEditorialService.validate(payload, batch)["1"]
    assert result["region"] == "待判定"
    assert result["tag_status"] == "uncertain"


@pytest.mark.parametrize("changes", [
    {"region": "火星"}, {"region_confidence": 2}, {"region_confidence": True},
    {"aweme_id": "invented-id"}, {"region_confidence": float("nan")},
])
def test_invalid_structured_output_rejected(changes):
    batch, payload = batch_and_answer(**changes)
    with pytest.raises(ValueError):
        PostEditorialService.validate(payload, batch)


@pytest.mark.asyncio
async def test_provider_failure_retains_rules_and_does_not_repeat_on_refresh():
    model, repo = Model(fail=True), Repository()
    service = PostEditorialService(model, repo)
    try:
        await service.enrich([post()])
        await asyncio.wait_for(service.worker, 2)
        result = (await service.enrich([post()]))["1"]
        assert result["tag_status"] == "retry"
        assert result["tag_method"] == "rules_v2"
        assert model.calls == 1
        assert service.queue.empty()
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_shutdown_cancels_inference_and_releases_dedup_keys():
    model = Model()
    model.gate = asyncio.Event()
    service = PostEditorialService(model, Repository())
    await service.enrich([post()])
    await asyncio.sleep(0)
    await service.stop()
    assert not service.pending and service.queue.empty()


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
