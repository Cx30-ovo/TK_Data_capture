"""Real rollback-journal lock competition; never touch production databases."""
from concurrent.futures import ThreadPoolExecutor
import asyncio
import hashlib
import json
import logging
import sqlite3
import threading
import time

import pytest

from database import monitor_comments_repository as repo
from tools.collection_errors import classify_collection_error, record_collection_error


@pytest.fixture
def storage(tmp_path, monkeypatch):
    source = tmp_path / 'source.db'
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE original(value TEXT)')
        db.execute("INSERT INTO original VALUES('untouched')")
    repo.save_policy(source, 'account', {'enabled': True, 'include_replies': True})
    repo.enqueue(source, 'account', ['123'])
    repo.finish(source, '123', [], {'state': 'partial', 'checkpoint': {'version': 1, 'root_cursor': 20}})
    with repo.connection(source, True) as db:
        db.execute('UPDATE collections SET updated_at=0,next_at=0')
    monkeypatch.setattr(repo, 'WRITE_TIMEOUT_SECONDS', .02)
    monkeypatch.setattr(repo, 'WRITE_RETRY_DELAYS', (.05, .05))
    return source


def snapshot(path):
    with sqlite3.connect(path) as db:
        return (db.execute('SELECT type,name,sql FROM sqlite_schema ORDER BY name').fetchall(),
                {name: db.execute('SELECT * FROM ' + name + ' ORDER BY 1,2').fetchall()
                 for name in ('policies', 'collections', 'comments')})


def hold_reader(source):
    reader = sqlite3.connect(source.with_name('monitor_comments.db'))
    assert reader.execute('PRAGMA journal_mode').fetchone()[0] == 'delete'
    reader.execute('BEGIN')
    reader.execute('SELECT * FROM collections').fetchall()
    return reader


@pytest.mark.parametrize('operation', ['claim', 'finish', 'enqueue', 'refresh', 'policy', 'expire'])
def test_real_commit_contention_replays_whole_transaction_once(storage, monkeypatch, operation):
    source = storage
    original_sha = hashlib.sha256(source.read_bytes()).digest()
    schema_before = snapshot(source.with_name('monitor_comments.db'))[0]
    busy_seen = threading.Event()
    attempts = []
    real_connect = sqlite3.connect

    class ObservedConnection(sqlite3.Connection):
        def commit(self):
            try:
                result = super().commit()
                attempts.append('committed')
                return result
            except sqlite3.OperationalError:
                attempts.append('busy')
                busy_seen.set()
                raise

    def connect(*args, **kwargs):
        return real_connect(*args, **kwargs, factory=ObservedConnection)

    reader = hold_reader(source)
    monkeypatch.setattr(repo.sqlite3, 'connect', connect)
    comment = {'comment_id': '10', 'parent_comment_id': '', 'content': 'saved once'}
    actions = {
        'claim': lambda: repo.claim(source, 'account', '123'),
        'finish': lambda: repo.finish(source, '123', (item for item in [comment]),
                                      {'state': 'partial', 'error_code': 'invalid_response',
                                       'checkpoint': {'version': 1, 'root_cursor': 40}}),
        'enqueue': lambda: repo.enqueue(source, 'account', (item for item in ['456', '789'])),
        'refresh': lambda: repo.request_snapshot_refresh(source, 'account', '123'),
        'policy': lambda: repo.save_policy(source, 'account', {'enabled': True, 'include_replies': False}),
        'expire': lambda: repo.expire(source, '123'),
    }
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(actions[operation])
        try:
            assert busy_seen.wait(2), 'Expected a real COMMIT lock failure'
        finally:
            reader.close()
        result = future.result(timeout=3)
    assert attempts.count('busy') >= 1 and attempts.count('committed') == 1
    assert hashlib.sha256(source.read_bytes()).digest() == original_sha
    assert snapshot(source.with_name('monitor_comments.db'))[0] == schema_before
    with real_connect(source.with_name('monitor_comments.db')) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        state = db.execute("SELECT state,payload FROM collections WHERE aweme_id='123'").fetchone()
        payload = json.loads(state[1])
        if operation == 'claim':
            assert result is True and state[0] == 'running'
            assert payload['checkpoint']['root_cursor'] == 20
        elif operation == 'finish':
            assert payload['failure_count'] == 1 and payload['checkpoint']['root_cursor'] == 40
            assert db.execute('SELECT count(*) FROM comments').fetchone()[0] == 1
        elif operation == 'enqueue':
            assert db.execute('SELECT count(*) FROM collections').fetchone()[0] == 3
        elif operation == 'refresh':
            assert payload['refresh_generation'] == 1 and payload['checkpoint']['root_cursor'] == 20
        elif operation == 'policy':
            assert not json.loads(db.execute('SELECT payload FROM policies').fetchone()[0])['include_replies']
        else:
            assert state[0] == 'expired'


def test_persistent_commit_contention_is_bounded_and_preserves_page_and_cursor(storage, caplog):
    reader = hold_reader(storage)
    before = snapshot(storage.with_name('monitor_comments.db'))
    started = time.monotonic()
    try:
        with pytest.raises(sqlite3.OperationalError) as raised:
            repo.finish(storage, '123', [{'comment_id': '11', 'parent_comment_id': '', 'content': 'uncommitted'}],
                        {'state': 'completed', 'checkpoint': {'version': 1, 'root_cursor': 40}})
    finally:
        reader.close()
    error = raised.value
    assert time.monotonic() - started < 2
    assert error.sqlite_errorcode == sqlite3.SQLITE_BUSY
    assert error.storage_phase == 'storage_commit' and error.storage_attempts == 3
    assert classify_collection_error(error).error_code == 'storage_busy'
    caplog.set_level(logging.WARNING, logger='MediaCrawler')
    diagnostic = record_collection_error(error, kind='comments', phase='connecting')
    assert diagnostic['phase'] == 'storage_commit'
    assert 'SQLITE_BUSY' in caplog.text and 'sqlite_errorcode' in caplog.text
    assert snapshot(storage.with_name('monitor_comments.db')) == before
    assert not storage.with_name('monitor_comments.db-journal').exists()


def test_begin_contention_does_not_claim_or_touch_a_fresh_running_task(storage):
    with repo.connection(storage, True) as db:
        db.execute("UPDATE collections SET state='running',updated_at=?,next_at=0", (int(time.time()),))
    before = snapshot(storage.with_name('monitor_comments.db'))
    writer = sqlite3.connect(storage.with_name('monitor_comments.db'))
    writer.execute('BEGIN IMMEDIATE')
    try:
        with pytest.raises(sqlite3.OperationalError) as raised:
            repo.claim(storage, 'account', '123')
        assert raised.value.storage_phase == 'storage_begin'
        assert raised.value.storage_attempts == 3
    finally:
        writer.close()
    assert repo.claim(storage, 'account', '123') is False
    assert snapshot(storage.with_name('monitor_comments.db')) == before


def test_stale_running_reclaim_keeps_cursor_and_obeys_account_boundary(storage):
    with repo.connection(storage, True) as db:
        db.execute("UPDATE collections SET state='running',updated_at=?,next_at=0", (int(time.time()) - 601,))
    assert not repo.claim(storage, 'other', '123')
    assert repo.claim(storage, 'account', '123')
    assert not repo.claim(storage, 'account', '123')
    assert repo.progress(storage, '123')['checkpoint']['root_cursor'] == 20


@pytest.mark.parametrize('code,name,expected', [
    (sqlite3.SQLITE_READONLY, 'SQLITE_READONLY', 'storage_error'),
    (sqlite3.SQLITE_FULL, 'SQLITE_FULL', 'storage_error'),
    (sqlite3.SQLITE_IOERR, 'SQLITE_IOERR', 'storage_error'),
    (sqlite3.SQLITE_LOCKED, 'SQLITE_LOCKED', 'storage_busy'),
    (sqlite3.SQLITE_BUSY | (2 << 8), 'SQLITE_BUSY_SNAPSHOT', 'storage_busy'),
])
def test_only_explicit_contention_is_retried(storage, monkeypatch, caplog, code, name, expected):
    calls = []
    error = sqlite3.OperationalError('secret-cookie http 429 https://private.invalid')
    error.sqlite_errorcode, error.sqlite_errorname = code, name

    def fail(*args, **kwargs):
        calls.append(1)
        raise error

    monkeypatch.setattr(repo.sqlite3, 'connect', fail)
    with pytest.raises(sqlite3.OperationalError):
        repo.expire(storage, '123')
    assert len(calls) == (3 if expected == 'storage_busy' else 1)
    assert classify_collection_error(error).error_code == expected
    caplog.set_level(logging.WARNING, logger='MediaCrawler')
    record_collection_error(error, kind='comments', phase='connecting')
    assert 'secret-cookie' not in caplog.text and 'private.invalid' not in caplog.text and 'http 429' not in caplog.text
    assert name in caplog.text and 'storage_connect' in caplog.text


def test_business_validation_not_retried_or_written(storage):
    before = snapshot(storage.with_name('monitor_comments.db'))
    with pytest.raises(ValueError):
        repo.request_snapshot_refresh(storage, 'other', '123')
    assert snapshot(storage.with_name('monitor_comments.db')) == before


def test_missing_reads_do_not_create_storage_or_cache(tmp_path):
    source = tmp_path / 'missing.db'
    assert repo.progress(source, '123') == {}
    assert not list(tmp_path.iterdir())


def test_schema_creation_rolls_back_atomically(tmp_path, monkeypatch):
    monkeypatch.setattr(repo, 'DDL', repo.DDL + 'INVALID SQL;')
    with pytest.raises(sqlite3.OperationalError):
        repo.save_policy(tmp_path / 'source.db', 'account', {'enabled': True})
    with sqlite3.connect(tmp_path / 'monitor_comments.db') as db:
        assert db.execute('SELECT name FROM sqlite_schema').fetchall() == []


@pytest.mark.asyncio
async def test_cancel_during_claim_retry_releases_committed_claim_and_preserves_cursor(storage, monkeypatch):
    from api.services import monitor_comments_service as service
    monkeypatch.setattr(service, 'source', lambda: storage)
    busy_seen = threading.Event()
    real_connect = sqlite3.connect

    class ObservedConnection(sqlite3.Connection):
        def commit(self):
            try:
                return super().commit()
            except sqlite3.OperationalError:
                busy_seen.set()
                raise

    reader = hold_reader(storage)
    monkeypatch.setattr(repo.sqlite3, 'connect', lambda *a, **kw: real_connect(*a, **kw, factory=ObservedConnection))
    task = asyncio.create_task(service.claim_one('account', '123'))
    try:
        assert await asyncio.to_thread(busy_seen.wait, 2)
        task.cancel()
    finally:
        reader.close()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 3)
    saved = repo.read(storage, '123')['collection']
    assert saved['state'] == 'partial' and saved['error_code'] == 'user_stop'
    assert saved['checkpoint']['root_cursor'] == 20


@pytest.mark.asyncio
async def test_page_retry_cancellation_commits_rows_and_cursor_together(storage, monkeypatch):
    from types import SimpleNamespace
    from api.services import monitor_comments_service as service
    monkeypatch.setattr(service, 'source', lambda: storage)
    busy_seen = threading.Event()
    real_connect = sqlite3.connect

    class ObservedConnection(sqlite3.Connection):
        def commit(self):
            try:
                return super().commit()
            except sqlite3.OperationalError:
                busy_seen.set()
                raise

    reader = hold_reader(storage)
    monkeypatch.setattr(repo.sqlite3, 'connect', lambda *a, **kw: real_connect(*a, **kw, factory=ObservedConnection))
    previous = repo.progress(storage, '123')
    collector = service.CommentCollector(SimpleNamespace(), {'include_replies': True}, 'account', previous)
    checkpoint = {'version': 1, 'root_cursor': 40, 'roots_done': False}
    task = asyncio.create_task(collector.save_page('123', [{'comment_id': '10', 'parent_comment_id': '', 'content': 'retained'}], checkpoint))
    try:
        assert await asyncio.to_thread(busy_seen.wait, 2)
        task.cancel()
    finally:
        reader.close()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 3)
    await service.close_cancelled('123')
    saved = repo.read(storage, '123')
    assert saved['total_saved'] == 1 and saved['collection']['checkpoint'] == checkpoint
    assert saved['collection']['state'] == 'partial' and collector.checkpoint == checkpoint
