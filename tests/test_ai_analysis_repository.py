import pytest

from database import db_session
from database.ai_analysis_repository import ai_analysis_repository


@pytest.fixture
def isolated_ai_analysis_db(tmp_path, monkeypatch):
    db_path = tmp_path / "ai_analysis.db"
    monkeypatch.setitem(db_session.sqlite_db_config, "db_path", str(db_path))
    db_session._engines.pop("sqlite", None)
    yield
    db_session._engines.pop("sqlite", None)


def cache_kwargs(**overrides):
    values = {
        "sec_user_id": "sec_ai_user",
        "analysis_type": "topic",
        "scope_key": "30d:all-status",
        "input_hash": "a" * 64,
        "provider": "openai_compatible",
        "model_name": "Qwen3.8-27B-FP8",
        "prompt_version": "topic-v1",
    }
    values.update(overrides)
    return values


@pytest.mark.asyncio
async def test_ai_analysis_cache_roundtrip_and_update(isolated_ai_analysis_db):
    await db_session.create_tables("sqlite")

    created = await ai_analysis_repository.upsert_result(
        **cache_kwargs(),
        result={"summary": "first"},
        usage={"total_tokens": 100},
        scope={"time_range": "30d"},
        expires_at=2_000_000_000,
    )
    assert created.id is not None
    assert created.status == "done"

    cached = await ai_analysis_repository.get_cached_result(
        **cache_kwargs(),
        now=1_900_000_000,
    )
    assert cached is not None
    assert cached.id == created.id
    assert cached.result_json == '{"summary":"first"}'
    assert cached.usage_json == '{"total_tokens":100}'

    updated = await ai_analysis_repository.upsert_result(
        **cache_kwargs(),
        result={"summary": "updated"},
        expires_at=2_000_000_000,
    )
    assert updated.id == created.id

    rows = await ai_analysis_repository.list_results(sec_user_id="sec_ai_user", analysis_type="topic")
    assert len(rows) == 1
    assert rows[0].result_json == '{"summary":"updated"}'


@pytest.mark.asyncio
async def test_ai_analysis_cache_expiration_and_status_transitions(isolated_ai_analysis_db):
    await db_session.create_tables("sqlite")

    await ai_analysis_repository.upsert_result(
        **cache_kwargs(analysis_type="lifecycle", prompt_version="lifecycle-v1"),
        result={"summary": "done"},
        expires_at=1_000,
    )
    assert await ai_analysis_repository.get_cached_result(
        **cache_kwargs(analysis_type="lifecycle", prompt_version="lifecycle-v1"),
        now=1_001,
    ) is None

    running = await ai_analysis_repository.mark_running(
        **cache_kwargs(analysis_type="lifecycle", prompt_version="lifecycle-v1"),
        scope={"time_range": "7d"},
    )
    assert running.status == "running"

    failed = await ai_analysis_repository.mark_failed(
        **cache_kwargs(analysis_type="lifecycle", prompt_version="lifecycle-v1"),
        error="model timeout",
    )
    assert failed.status == "failed"
    assert failed.error == "model timeout"

    latest = await ai_analysis_repository.get_latest_result(
        sec_user_id="sec_ai_user",
        analysis_type="lifecycle",
    )
    assert latest is not None
    assert latest.status == "failed"


@pytest.mark.asyncio
async def test_ai_analysis_cache_delete_and_expiration_cleanup(isolated_ai_analysis_db):
    await db_session.create_tables("sqlite")

    first = await ai_analysis_repository.upsert_result(
        **cache_kwargs(input_hash="b" * 64),
        result={"summary": "expired"},
        expires_at=1_000,
    )
    second = await ai_analysis_repository.upsert_result(
        **cache_kwargs(input_hash="c" * 64),
        result={"summary": "active"},
        expires_at=3_000_000_000,
    )

    assert await ai_analysis_repository.clear_expired(now=1_001) == 1
    assert await ai_analysis_repository.delete_result(first.id) is False
    assert await ai_analysis_repository.delete_result(second.id) is True


@pytest.mark.asyncio
async def test_ai_analysis_repository_rejects_invalid_values(isolated_ai_analysis_db):
    await db_session.create_tables("sqlite")

    with pytest.raises(ValueError):
        await ai_analysis_repository.upsert_result(**cache_kwargs(analysis_type="unknown"))

    with pytest.raises(ValueError):
        await ai_analysis_repository.upsert_result(**cache_kwargs(), status="unknown")
