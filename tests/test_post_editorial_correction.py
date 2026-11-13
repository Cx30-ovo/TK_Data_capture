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
    app = FastAPI()
    app.include_router(routes.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, service, repo, path
    await service.stop()
    for engine in db_session._engines.values():
        await engine.dispose()


@pytest.mark.asyncio
async def test_rule_get_does_not_write_any_table_and_has_provenance(isolated):
    client,service,repo,path=isolated
    before=snapshot(path)
    response=await client.get("/monitor/posts/123/editorial-tags")
    assert response.status_code==200
    value=response.json()
    assert value["classification_mode"]=="automatic_rules" and value["channel"]=="民生"
    assert value["region"]=="待判定" and value["tag_rule_version"]
    assert value["tag_rule_hits"] and value["manual_status"]=="none"
    assert snapshot(path)==before and service.worker is None


@pytest.mark.asyncio
@pytest.mark.parametrize("mode",["manual","automatic"])
async def test_former_correction_endpoint_rejects_without_writes(isolated,mode):
    client,_,_,path=isolated
    before=snapshot(path)
    response=await client.put("/monitor/posts/123/editorial-tags",json={
        "mode":mode,"expected_revision":0,"source_sha256":"a"*64,
        "channel":"文娱","region":"国际","reason":"旧客户端请求"})
    assert response.status_code==410 and "已停用" in response.json()["detail"]
    assert snapshot(path)==before


@pytest.mark.asyncio
async def test_legacy_records_preserved_but_neither_applied_nor_referenced(isolated):
    from api.schemas.monitor import PostEditorialCorrectionRequest
    from database.post_editorial_repository import source_sha256
    client,service,repo,path=isolated
    post=await monitor_repository.get_post("123")
    await repo.correct("123",PostEditorialCorrectionRequest(
        expected_revision=0,source_sha256=source_sha256(post),channel="文娱",region="国际",reason="历史人工记录"))
    await repo.save("legacy-ai","123",{"channel":"教育","region":"本省","tag_method":"rules_ai"})
    before=snapshot(path)
    tags=(await client.get("/monitor/posts/123/editorial-tags")).json()
    assert tags["channel"]=="民生" and tags["region"]=="待判定"
    assert tags["manual_status"]=="none" and not tags["tag_experience_refs"]
    assert snapshot(path)==before
    assert tags==(await service.enrich([post]))["123"]


@pytest.mark.asyncio
async def test_missing_post_returns_404_without_initializing_new_storage(isolated):
    client,_,_,path=isolated
    before=snapshot(path)
    assert (await client.get("/monitor/posts/999/editorial-tags")).status_code==404
    assert snapshot(path)==before


@pytest.mark.asyncio
async def test_dashboard_get_classifies_without_writes_or_background_jobs(isolated,monkeypatch):
    from api.services import monitor_service as module
    client,service,_,path=isolated
    monkeypatch.setattr(module,'post_editorial_service',service)
    before=snapshot(path)
    response=await client.get('/monitor/dashboard?all_accounts=true')
    assert response.status_code==200
    works=response.json()['posts']
    assert len(works)==1 and works[0]['classification_mode']=='automatic_rules'
    assert works[0]['channel']=='民生' and works[0]['tag_rule_version']
    assert service.worker is None and service.queue.empty()
    assert snapshot(path)==before
