"""Manual classification uses temporary SQLite only; no real inference."""
import asyncio
import json
import sqlite3

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from api.routers import monitor as routes
from api.services.post_editorial_service import PostEditorialService
from database import db_session
from database.monitor_repository import monitor_repository
from database.post_editorial_repository import PostEditorialRepository, manual_key


class NoModel:
    def get_status(self):
        return {"enabled": False, "configured": False}

    async def generate_json(self, **kwargs):
        raise AssertionError("Manual classification must not request inference")


def snapshot(path):
    with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as db:
        schema = db.execute("SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY name").fetchall()
        rows = {name: sorted(db.execute(f'SELECT * FROM "{name}"').fetchall(), key=repr)
                for (name,) in db.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    return schema, rows


@pytest_asyncio.fixture
async def isolated(tmp_path, monkeypatch):
    path = tmp_path / "monitor.db"
    monkeypatch.setitem(db_session.sqlite_db_config, "db_path", str(path))
    monkeypatch.setattr(db_session, "_engines", {})
    await db_session.create_tables("sqlite")
    await monitor_repository.upsert_monitored_account("sample-account")
    await monitor_repository.upsert_post(aweme_id="123", sec_user_id="sample-account",
        title="一岁萌娃迈出人生第一步，走向父母", desc="家庭日常生活", create_time=1,
        canonical_url="https://www.douyin.com/video/123")
    repo = PostEditorialRepository()
    service = PostEditorialService(NoModel(), repo)
    monkeypatch.setattr(routes, "post_editorial_service", service)
    monkeypatch.setattr(routes, "post_editorial_repository", repo)
    app = FastAPI()
    app.include_router(routes.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, service, repo, path
    await service.stop()
    for engine in db_session._engines.values():
        await engine.dispose()


async def payload(client):
    current = (await client.get("/monitor/posts/123/editorial-tags")).json()
    return {"expected_revision": current["manual_revision"],
            "source_sha256": current["classification_source_sha256"],
            "channel": "民生", "region": "待判定", "reason": "作品描写萌娃学步和家庭生活。"}


@pytest.mark.asyncio
async def test_readonly_save_priority_persistence_and_only_label_table_changes(isolated, monkeypatch):
    client, service, repo, path = isolated
    baseline = snapshot(path)
    request = await payload(client)
    assert snapshot(path) == baseline
    assert service.worker is None
    response = await client.put("/monitor/posts/123/editorial-tags", json=request)
    assert response.status_code == 200
    tags = response.json()
    assert tags["channel"] == "民生" and tags["region"] == "待判定"
    assert tags["tag_method"] == "manual" and tags["manual_status"] == "active"
    assert tags["manual_revision"] == 1 and tags["tag_confidence"] == {}
    post = await monitor_repository.get_post("123")
    assert (await service.enrich([post]))["123"]["channel"] == "民生"
    assert service.worker is None
    from api.services import post_editorial_service as module
    monkeypatch.setattr(module, "VERSION", "a-future-model-policy")
    restarted = PostEditorialService(NoModel(), PostEditorialRepository())
    assert (await restarted.enrich([post]))["123"]["tag_method"] == "manual"
    after = snapshot(path)
    assert baseline[0] == after[0]
    assert {k: v for k, v in baseline[1].items() if k != "post_editorial_labels"} == {
        k: v for k, v in after[1].items() if k != "post_editorial_labels"}
    assert len(after[1]["post_editorial_labels"]) == 1
    before_get = snapshot(path)
    assert (await client.get("/monitor/posts/123/editorial-tags")).json()["manual_revision"] == 1
    assert snapshot(path) == before_get


@pytest.mark.asyncio
async def test_conflict_preserves_saved_value_and_concurrent_requests_have_one_winner(isolated):
    client, _, _, _ = isolated
    request = await payload(client)
    responses = await asyncio.gather(
        client.put("/monitor/posts/123/editorial-tags", json=request),
        client.put("/monitor/posts/123/editorial-tags", json={**request, "channel": "文旅"}))
    assert sorted(r.status_code for r in responses) == [200, 409]
    saved = (await client.get("/monitor/posts/123/editorial-tags")).json()
    rejected = await client.put("/monitor/posts/123/editorial-tags", json=request)
    assert rejected.status_code == 409 and "分类已更新" in rejected.json()["detail"]
    assert (await client.get("/monitor/posts/123/editorial-tags")).json() == saved


@pytest.mark.asyncio
async def test_restore_automatic_keeps_model_cache_and_monotonic_revision(isolated):
    client, service, repo, _ = isolated
    post = await monitor_repository.get_post("123")
    model_tags = {"channel": "文旅", "region": "待判定", "tag_method": "rules_ai", "tag_status": "uncertain"}
    key = service.cache_key(post)
    await repo.save(key, post.aweme_id, model_tags)
    request = await payload(client)
    assert (await client.put("/monitor/posts/123/editorial-tags", json=request)).status_code == 200
    auto = {"mode": "automatic", "expected_revision": 1, "source_sha256": request["source_sha256"]}
    result = await client.put("/monitor/posts/123/editorial-tags", json=auto)
    assert result.status_code == 200
    assert result.json()["manual_revision"] == 2 and result.json()["manual_status"] == "none"
    assert result.json()["channel"] == "文旅"
    assert (await repo.load([key]))[key]["tags"] == model_tags
    assert (await client.put("/monitor/posts/123/editorial-tags", json={**request, "expected_revision": 1})).status_code == 409
    assert (await client.put("/monitor/posts/123/editorial-tags", json={**request, "expected_revision": 2})).json()["manual_revision"] == 3


@pytest.mark.asyncio
async def test_source_change_invalidates_old_correction_and_rejects_stale_form(isolated):
    client, service, _, _ = isolated
    request = await payload(client)
    await client.put("/monitor/posts/123/editorial-tags", json=request)
    await monitor_repository.upsert_post(aweme_id="123", sec_user_id="sample-account", title="厦门发布科技进展",
        desc="新的作品正文", create_time=1, canonical_url="https://www.douyin.com/video/123")
    stale = await client.put("/monitor/posts/123/editorial-tags", json={**request, "expected_revision": 1})
    assert stale.status_code == 409 and "原文已变化" in stale.json()["detail"]
    current = (await client.get("/monitor/posts/123/editorial-tags")).json()
    assert current["manual_status"] == "outdated" and current["manual_revision"] == 1
    assert current["tag_method"] != "manual" and current["channel"] == "科技"
    request.update(expected_revision=1, source_sha256=current["classification_source_sha256"], channel="科技")
    assert (await client.put("/monitor/posts/123/editorial-tags", json=request)).json()["manual_status"] == "active"


@pytest.mark.asyncio
async def test_inflight_model_result_does_not_overwrite_manual_record(isolated):
    client, _, repo, _ = isolated
    gate = asyncio.Event()
    class PendingModel:
        def get_status(self):
            return {"enabled": True, "configured": True}
        async def generate_json(self, **kwargs):
            await gate.wait()
            return {"items": [{"aweme_id": "123", "channel": "民生", "channel_confidence": .9,
                "channel_evidence": "萌娃", "region": "待判定", "region_confidence": .5, "region_evidence": ""}]}
    service = PostEditorialService(PendingModel(), repo)
    post = await monitor_repository.get_post("123")
    try:
        await service.enrich([post])
        await client.put("/monitor/posts/123/editorial-tags", json={**await payload(client), "channel": "教育"})
        gate.set()
        await asyncio.wait_for(service.worker, 3)
        result = (await service.enrich([post]))["123"]
        assert result["channel"] == "教育" and result["tag_method"] == "manual"
        assert (await repo.load_manual(["123"]))["123"]["revision"] == 1
    finally:
        gate.set()
        await service.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"channel": "推荐"}, {"region": "全部"}, {"reason": "  "}, {"reason": "x" * 1001},
    {"expected_revision": -1}, {"expected_revision": True}, {"source_sha256": "bad"},
    {"tag_method": "rules_ai"}, {"channel": None}, {"region": None}, {"mode": "other"},
])
async def test_invalid_parameters_do_not_write(isolated, changes):
    client, _, _, path = isolated
    request = await payload(client)
    before = snapshot(path)
    response = await client.put("/monitor/posts/123/editorial-tags", json={**request, **changes})
    assert response.status_code == 422
    assert snapshot(path) == before


@pytest.mark.asyncio
async def test_missing_post_and_unicode_length(isolated):
    client, _, _, _ = isolated
    request = await payload(client)
    assert (await client.get("/monitor/posts/missing/editorial-tags")).status_code == 404
    assert (await client.put("/monitor/posts/missing/editorial-tags", json=request)).status_code == 404
    request["reason"] = "字😀" * 500
    assert (await client.put("/monitor/posts/123/editorial-tags", json=request)).status_code == 200
