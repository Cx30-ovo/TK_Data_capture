import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.services.post_editorial_tags import classify_post, RULE_VERSION
from api.services.post_editorial_service import PostEditorialService
from api.services.editorial_rule_cache import EditorialRuleCache

FIXTURE = json.loads((Path(__file__).parent / "fixtures/editorial_classification_golden.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda case: case["id"])
def test_golden_classification(case):
    result = classify_post(case["text"])
    assert result["channel"] == case["channel"]
    assert result["region"] == case["region"]
    if "subtopic" in case:
        assert case["subtopic"] in result["channel_subtopics"]
    for hit in result["tag_rule_hits"] + result["channel_subtopic_hits"] + result["region_locations"]:
        assert hit["snippet"] in case["text"]
    assert result["tag_rule_version"] == RULE_VERSION


@pytest.mark.parametrize("text,role,place", [
    ("来自福建的菌草，在斐济种植", "material_origin", "福建"),
    ("祖籍福建的人士在北京开展活动", "person_origin", "福建"),
    ("福建记者报道斐济菌草种植", "reporting_source", "福建"),
    ("中国驻日本大使馆发布消息", "institution_location", "日本"),
    ("新闻（来源/福建日报）", "reporting_source", "福建"),
    ("日本游客在厦门旅游", "event_location", "厦门"),
])
def test_locations_have_roles_without_using_background(text, role, place):
    result = classify_post(text)
    location = next(row for row in result["region_locations"] if row["place"] == place and row["role"] == role)
    if role != "event_location":
        assert location["used"] is False


@pytest.mark.parametrize("text,field,code", [
    ("这一幕令人感动", "channel", "insufficient_clues"),
    ("厦门和福州同步举办活动", "region", "rule_conflict"),
    ("来自福建的人士发言", "region", "location_role_unclear"),
    ("在格陵兰岛开展活动", "region", "lexicon_gap"),
    ("一段没有词典覆盖的独特题材", "channel", "lexicon_gap"),
])
def test_diagnostic_codes(text, field, code):
    assert any(row["field"] == field and row["code"] == code
               for row in classify_post(text)["tag_pending_reasons"])


def sample(ident=1, title="厦门新增公交线路", modified=10):
    return SimpleNamespace(id=ident, aweme_id=str(ident), title=title, desc="", last_modify_ts=modified)


class Source:
    def __init__(self, posts):
        self.posts = posts
        self.calls = []

    async def list_editorial_sources(self, **kw):
        self.calls.append(kw)
        return [copy.copy(p) for p in self.posts if p.id > kw["after_id"]
                and (kw["modified_since"] is None or p.last_modify_ts >= kw["modified_since"])
                and p.last_modify_ts <= kw["modified_until"]][:kw["limit"]]


@pytest.mark.asyncio
async def test_background_cache_reuse_invalidation_and_readonly_get(tmp_path, monkeypatch):
    service = PostEditorialService()
    service.cache = EditorialRuleCache(tmp_path / "rules", RULE_VERSION)
    posts = [sample(), sample(2)]
    source = Source(posts)
    await service.enrich(posts)
    assert not (tmp_path / "rules").exists()  # GET never creates the cache.
    await service.refresh_once(source, batch_size=1)
    assert service.progress["recomputed"] == 2
    assert len(source.calls) == 3
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.json")}
    monkeypatch.setattr(service, "classify", lambda p: pytest.fail("must use current cache"))
    tags = await service.enrich(posts)
    assert all(row["classification_cache_status"] == "current" for row in tags.values())
    await service.refresh_once(source)
    assert service.progress["reused"] == 2 and service.progress["recomputed"] == 0
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*.json")}
    monkeypatch.undo()
    posts[0].title = "北京发布管理办法"
    tags = await service.enrich(posts)
    assert tags["1"]["channel"] == "政策文件" and tags["1"]["classification_cache_status"] == "pending"
    await service.refresh_once(source)
    assert service.progress["recomputed"] == 1
    fresh = PostEditorialService()
    fresh.cache = EditorialRuleCache(tmp_path / "rules", RULE_VERSION)
    monkeypatch.setattr(fresh, "classify", lambda p: pytest.fail("restart should reuse files"))
    assert (await fresh.enrich(posts))["1"]["channel"] == "政策文件"


@pytest.mark.asyncio
async def test_incremental_sweep_and_version_isolation(tmp_path):
    service = PostEditorialService()
    service.cache = EditorialRuleCache(tmp_path, RULE_VERSION)
    source = Source([sample(), sample(2, modified=20)])
    await service.refresh_once(source, modified_since=15, batch_size=1)
    assert service.progress["scanned"] == 1
    assert (await service.enrich(source.posts))["1"]["classification_cache_status"] == "pending"
    future = EditorialRuleCache(tmp_path, "future-version")
    assert future.read_many([("2", service.classify(source.posts[1])["classification_source_sha256"])]) == {}


@pytest.mark.asyncio
async def test_corrupt_cache_falls_back_without_repair_or_mutation(tmp_path):
    service = PostEditorialService()
    service.cache = EditorialRuleCache(tmp_path, RULE_VERSION)
    source = Source([sample()])
    await service.refresh_once(source)
    path = next(tmp_path.rglob("*.json"))
    row = json.loads(path.read_text(encoding="utf-8"))
    row["tags"]["channel"] = "伪造分类"
    path.write_text(json.dumps(row), encoding="utf-8")
    before = path.read_bytes()
    service.cache = EditorialRuleCache(tmp_path, RULE_VERSION)
    assert (await service.enrich(source.posts))["1"]["channel"] == "民生"
    assert path.read_bytes() == before
    path.write_text("not-json", encoding="utf-8")
    assert (await service.enrich(source.posts))["1"]["channel"] == "民生"


@pytest.mark.asyncio
async def test_failure_health_and_lifecycle(tmp_path):
    service = PostEditorialService()
    source = Source([sample()])
    async def failure(**kw):
        raise RuntimeError("private details must not reach UI")
    source.list_editorial_sources = failure
    service.cache = EditorialRuleCache(tmp_path, RULE_VERSION)
    with pytest.raises(RuntimeError):
        await service.refresh_once(source)
    assert service.progress["state"] == "error"
    assert "private" not in service.progress["last_error"]
    await service.start(source, tmp_path, interval=.01)
    worker = service.worker
    await service.start(source, tmp_path)
    assert worker is service.worker
    await asyncio.sleep(.03)
    await service.stop()
    assert worker.done()


@pytest.mark.asyncio
async def test_health_account_scope_and_empty_state():
    service = PostEditorialService()
    posts = [sample(), sample(2, "这一幕令人感动")]
    health = service.health(posts, await service.enrich(posts))
    assert health["total"] == 2 and health["channel_resolved"] == 1
    assert health["pending_posts"] == 1 and health["cached_posts"] == 0
    assert health["pending_reasons"]["insufficient_clues"] == 2
    assert service.health([], {})["total"] == 0


@pytest.mark.asyncio
async def test_real_repository_scan_cache_and_dashboard_are_db_readonly(tmp_path, monkeypatch):
    import httpx
    import sqlite3
    from fastapi import FastAPI
    from database import db_session
    from database.monitor_repository import monitor_repository
    from api.routers import monitor as routes
    from api.services import monitor_service as module

    path = tmp_path / "isolated.db"
    monkeypatch.setitem(db_session.sqlite_db_config, "db_path", str(path))
    monkeypatch.setattr(db_session, "_engines", {})
    await db_session.create_tables("sqlite")
    service = PostEditorialService()
    service.cache = EditorialRuleCache(tmp_path / "cache", RULE_VERSION)
    monkeypatch.setattr(routes, "post_editorial_service", service)
    monkeypatch.setattr(module, "post_editorial_service", service)
    app = FastAPI()
    app.include_router(routes.router)
    def snapshot():
        with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as conn:
            conn.execute("PRAGMA query_only=ON")
            schema = conn.execute("select type,name,sql from sqlite_schema order by name").fetchall()
            return schema, {name: conn.execute(f'SELECT * FROM "{name}"').fetchall()
                            for name, in conn.execute("select name from sqlite_schema where type='table'")}
    try:
        for ident, title in [("1", "厦门新增公交线路"), ("2", "这一幕令人感动")]:
            await monitor_repository.upsert_post(aweme_id=ident, sec_user_id="account", title=title,
                desc="", create_time=1, canonical_url="https://example.invalid/video/" + ident)
        before = snapshot()
        await service.refresh_once(monitor_repository, batch_size=1)
        assert service.progress["scanned"] == 2 and snapshot() == before
        assert not await monitor_repository.list_editorial_sources(modified_since=9999999999)
        files_before = {p: p.read_bytes() for p in (tmp_path / "cache").rglob("*.json")}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            result = await client.get("/monitor/dashboard?all_accounts=true")
            assert result.status_code == 200
            health = result.json()["classification_health"]
            assert health["total"] == 2 and health["cached_posts"] == 2 and health["pending_posts"] == 1
            result = await client.get("/monitor/posts/1/editorial-tags")
            assert result.json()["channel_subtopics"] == ["公共服务"]
            assert snapshot() == before
            assert files_before == {p: p.read_bytes() for p in (tmp_path / "cache").rglob("*.json")}
        # Cover-only refresh reuses classification, caption change invalidates.
        await monitor_repository.update_post_cover_url("1", "https://example.invalid/cover.jpg")
        await service.refresh_once(monitor_repository)
        assert service.progress["recomputed"] == 0
        await monitor_repository.upsert_post(aweme_id="1", sec_user_id="account", title="北京发布管理办法",
            desc="", create_time=1, canonical_url="https://example.invalid/video/1")
        before = snapshot()
        await service.refresh_once(monitor_repository)
        assert service.progress["recomputed"] == 1 and snapshot() == before
    finally:
        for engine in db_session._engines.values():
            await engine.dispose()
