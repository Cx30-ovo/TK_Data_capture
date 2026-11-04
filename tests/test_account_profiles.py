"""Account profiles read isolated SQLite only. No app lifespan or network."""

import socket
import sqlite3
from contextlib import contextmanager

import httpx
import pytest
from fastapi import FastAPI

from api.routers.monitor import router
from api.services import account_profile_service as profiles
from config.db_config import sqlite_db_config


NOW = 1800000000


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "profiles.db"
    with sqlite3.connect(path) as db:
        db.executescript("""
        CREATE TABLE douyin_monitored_accounts (id INTEGER PRIMARY KEY, platform TEXT, sec_user_id TEXT, display_name TEXT);
        CREATE TABLE douyin_posts (aweme_id TEXT, platform TEXT, sec_user_id TEXT, title TEXT, create_time INTEGER, first_seen_at INTEGER, status TEXT);
        CREATE TABLE douyin_post_snapshots (aweme_id TEXT, platform TEXT, stage TEXT, captured_at INTEGER, actual_age_seconds INTEGER, created_at INTEGER);
        INSERT INTO douyin_monitored_accounts VALUES (1,'dy','account-a','自有测试'),(2,'dy','account-b','竞品测试');
        """)
        db.executemany("INSERT INTO douyin_posts VALUES (?,?,?,?,?,?,?)", [
            ("one", "dy", "account-a", "今天😀？ #厦门 #厦门", NOW - 7200, NOW - 7100, "active"),
            ("two", "dy", "account-a", "“更新2！”", NOW - 3600, NOW - 3500, "active"),
            ("missing", "dy", "account-a", None, NOW - 1800, NOW - 1700, "active"),
            ("deleted", "dy", "account-a", "排除", NOW - 2000, NOW - 1900, "deleted"),
            ("future", "dy", "account-a", "未来", NOW, NOW, "active"),
            ("late", "dy", "account-a", "后补采", NOW - 5000, NOW + 1, "active"),
            ("old", "dy", "account-a", "过期", NOW - 31 * 86400, NOW - 31 * 86400, "active"),
            ("other", "dy", "account-b", "竞品不应进入", NOW - 4000, NOW - 3900, "active"),
        ])
        db.executemany("INSERT INTO douyin_post_snapshots VALUES (?,?,?,?,?,?)", [
            ("one", "dy", "1h", NOW - 3600, 3600, NOW - 3600),
            ("two", "dy", "24h", NOW - 100, 3500, NOW - 100),
            ("missing", "dy", "1h", NOW - 100, 1, NOW - 100),
            ("missing", "dy", "first_seen", NOW + 1, 1801, NOW + 1),
            ("missing", "dy", "first_seen", NOW - 100, 1700, NOW + 1),
        ])
    return path


@contextmanager
def unchanged(path):
    before = path.read_bytes()
    yield
    assert path.read_bytes() == before
    assert not path.with_name(path.name + "-journal").exists()


@pytest.mark.asyncio
async def test_scope_evidence_unicode_and_readonly(source, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("Network forbidden")
    monkeypatch.setattr(socket.socket, "connect", no_network)
    with unchanged(source):
        result = await profiles.get_account_profile(str(source), 1, as_of=NOW)
    assert result["counts"] == {"eligible": 3, "excluded_status": 1, "sampled": 3, "with_title": 2, "missing_title": 1, "truncated": False}
    assert result["title_length"]["mean"] == 2.5
    assert result["hashtags"][0]["post_count"] == 1  # repeated tag is one work
    assert result["hashtags"][0]["evidence"][0]["post_id"] == "one"
    for signal in result["signals"]:
        for evidence in signal["evidence"]:
            assert evidence["field"] == "title"
            assert evidence["post_id"] in {"one", "two"}
    assert len(result["input_sha256"]) == 64


@pytest.mark.parametrize("title,expected", [
    ("今天😀？ #厦门 #厦门", 2), ("“更新2！”", 3),
    ("AI新闻 2026！", 8), ("#厦门 😀！？", 0),
    ("", 0), ("你好，世界！", 4),
])
def test_title_word_count(title, expected):
    assert profiles.title_word_count(title) == expected


def test_symbol_only_title_excluded_from_length_statistics():
    result = profiles.build_profile(
        {"id": 1, "display_name": "测试", "platform": "dy", "sec_user_id": "a"},
        [{"aweme_id": "one", "title": "#厦门 😀！？", "create_time": NOW - 1}],
        [], 1, 1, NOW - 86400, NOW,
    )
    assert result["title_length"]["mean"] is None
    assert result["title_length"]["sample_count"] == 0
    assert result["title_length"]["excluded_count"] == 1
    assert sum(bin["count"] for bin in result["title_length"]["histogram"]) == 0


@pytest.mark.asyncio
async def test_observation_cutoff_and_lifecycle_windows(source):
    result = await profiles.get_account_profile(str(source), 1, as_of=NOW)
    assert result["coverage"] == {
        "observed_posts": 2, "without_observation": 1, "invalid_observations": 1,
        "lifecycle": [{"stage": stage, "posts": 1 if stage == "1h" else 0} for stage in profiles.STAGES],
    }


@pytest.mark.asyncio
async def test_fingerprint_is_reproducible_and_changes_with_input(source):
    first = await profiles.get_account_profile(str(source), 1, as_of=NOW)
    same = await profiles.get_account_profile(str(source), 1, as_of=NOW)
    assert first == same
    with sqlite3.connect(source) as db:
        db.execute("UPDATE douyin_posts SET title='已更新' WHERE aweme_id='one'")
    changed = await profiles.get_account_profile(str(source), 1, as_of=NOW)
    assert changed["input_sha256"] != first["input_sha256"]


@pytest.mark.asyncio
async def test_account_isolation_empty_and_missing(source):
    other = await profiles.get_account_profile(str(source), 2, as_of=NOW)
    assert other["counts"]["eligible"] == 1
    assert other["title_length"]["mean"] == len("竞品不应进入")
    empty = await profiles.get_account_profile(str(source), 1, as_of=NOW - 365 * 86400)
    assert empty["counts"]["eligible"] == 0
    assert empty["title_length"]["mean"] is None
    assert empty["publication"]["earliest"] is None
    with pytest.raises(profiles.AccountNotFound):
        await profiles.get_account_profile(str(source), 999, as_of=NOW)


@pytest.mark.asyncio
async def test_sample_limit_explicit_and_count_conservation(source, monkeypatch):
    monkeypatch.setattr(profiles, "MAX_SAMPLE", 1)
    result = await profiles.get_account_profile(str(source), 1, as_of=NOW)
    assert result["counts"]["eligible"] == 3
    assert result["counts"]["sampled"] == 1
    assert result["counts"]["truncated"]
    assert sum(b["count"] for b in result["title_length"]["histogram"]) == result["counts"]["with_title"]


@pytest.mark.asyncio
async def test_missing_db_and_schema_do_not_create_or_migrate(tmp_path):
    missing = tmp_path / "absent.db"
    with pytest.raises(profiles.ProfileUnavailable):
        await profiles.get_account_profile(str(missing), 1)
    assert not missing.exists()
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    with unchanged(empty), pytest.raises(profiles.ProfileUnavailable):
        await profiles.get_account_profile(str(empty), 1)


@pytest.mark.asyncio
async def test_route_contract_and_error_statuses(source, monkeypatch, tmp_path):
    monkeypatch.setitem(sqlite_db_config, "db_path", str(source))
    monkeypatch.setattr(profiles.time, "time", lambda: NOW)
    app = FastAPI()
    app.include_router(router, prefix="/api")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        with unchanged(source):
            response = await client.get("/api/monitor/accounts/1/profile")
        assert response.status_code == 200
        assert response.json()["version"] == profiles.PROFILE_VERSION
        assert (await client.get("/api/monitor/accounts/999/profile")).status_code == 404
        for url in ["/api/monitor/accounts/0/profile", "/api/monitor/accounts/1/profile?days=0", "/api/monitor/accounts/1/profile?days=366"]:
            assert (await client.get(url)).status_code == 422
        monkeypatch.setitem(sqlite_db_config, "db_path", str(tmp_path / "missing.db"))
        assert (await client.get("/api/monitor/accounts/1/profile")).status_code == 503
