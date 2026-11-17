"""Response fault injection only; no production DB, browser or platform requests."""
import asyncio
import hashlib
import json
import logging
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.services import monitor_comments_service as svc
from database import monitor_comments_repository as repo
from tools.collection_errors import CommentResponseError, classify_collection_error, record_collection_error


def raw(cid='100', **values):
    return {'cid': cid, 'aweme_id': '123', 'text': '测试评论', 'user': {}} | values


def page(*comments, more=False, cursor=0):
    return {'comments': list(comments), 'has_more': more, 'cursor': cursor}


def fetcher(roots=None, replies=None):
    return SimpleNamespace(should_stop=lambda: False, _client=SimpleNamespace(
        get_aweme_comments=AsyncMock(side_effect=roots or [page(raw())]),
        get_sub_comments=AsyncMock(side_effect=replies or [page()])))


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    source = tmp_path / 'source.db'
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE original(value TEXT)')
        db.execute("INSERT INTO original VALUES('preserved')")
    monkeypatch.setattr(svc, 'source', lambda: source)
    monkeypatch.setattr(svc, 'wait_between_requests', AsyncMock())
    repo.save_policy(source, 'account', {'enabled': True, 'include_replies': True})
    return source


async def collect(source, f):
    return await svc.collect_one(f, 'account', '123', repo.policy(source, 'account'))


def wake(source):
    with repo.connection(source, True) as db:
        db.execute('UPDATE collections SET next_at=0,updated_at=0')


@pytest.mark.parametrize('bad,reason', [
    (None, 'not_object'), ([], 'not_object'),
    ({'has_more': False}, 'invalid_comments'),
    ({'comments': None, 'has_more': False}, 'invalid_comments'),
    ({'comments': 'private-text', 'has_more': False}, 'invalid_comments'),
    ({'comments': [], 'has_more': None}, 'invalid_pagination'),
    ({'comments': []}, 'invalid_pagination'),
    ({'comments': [], 'has_more': 0.0}, 'invalid_pagination'),
    ({'comments': [], 'has_more': '0'}, 'invalid_pagination'),
    ({'comments': None, 'total': False, 'has_more': False}, 'invalid_comments'),
    ({'comments': None, 'total': '0', 'has_more': False}, 'invalid_comments'),
    ({'comments': None, 'total': 0}, 'invalid_pagination'),
    ({'status_code': None}, 'invalid_status'),
    ({'status_code': False}, 'invalid_status'),
    ({'status_code': '0'}, 'invalid_status'),
    ({'status_code': 1}, 'invalid_status'),
    (page(raw('101'), more=True, cursor=0), 'stalled_cursor'),
    (page(more=True, cursor=20), 'stalled_cursor'),
    (page(raw('101'), more=True, cursor=True), 'stalled_cursor'),
])
@pytest.mark.asyncio
async def test_rejected_reply_pages_are_pending_not_empty_success(isolated, bad, reason):
    result, error = await collect(isolated, fetcher(replies=[bad]))
    assert isinstance(error, CommentResponseError)
    assert error.response_shape['reason'] == reason
    assert result['error_code'] == 'invalid_response' and result['state'] == 'partial'
    assert result['checkpoint']['reply_pending'] == ({} if reason in ('not_object', 'invalid_status') else {'100': 0})
    assert not result['checkpoint']['replies_done'] and not repo.fully_traversed(isolated, '123')
    assert repo.read(isolated, '123')['total_saved'] == 1


@pytest.mark.parametrize('value', [page(), {'comments': None, 'total': 0, 'has_more': False},
                                {'total': 0, 'has_more': 0, 'status_code': 0}])
@pytest.mark.asyncio
async def test_explicit_empty_remains_valid(isolated, value):
    result, error = await collect(isolated, fetcher(replies=[value]))
    assert error is None and result['state'] == 'completed'


def test_safe_response_structure_and_stable_thread_correlation(caplog):
    caplog.set_level(logging.WARNING, logger='MediaCrawler')
    response = {'comments': 'secret-comment', 'status_code': 'secret-cookie',
                'has_more': None, 'total': 2**100, 'cursor': {'token': 'secret-token'},
                'secret-extra-key': 'https://private.invalid/signed'}
    exc = CommentResponseError('invalid_comments', response, ident='1234567890123456789',
                               parent='9876543210123456789', cursor=20)
    first = record_collection_error(exc, kind='comments', phase='other')
    assert first == record_collection_error(exc, kind='comments')
    assert len(caplog.records) == 1 and first['phase'] == 'comments_replies'
    record = json.loads(caplog.records[0].message.split('collection_failure ', 1)[1])
    shape = record['exceptions'][0]['comment_response']
    assert shape['fields']['comments'] == {'present': True, 'type': 'string'}
    assert shape['fields']['total'] == {'present': True, 'type': 'integer'}
    assert shape['request_cursor'] == 20
    assert shape['thread_hash'] == CommentResponseError('not_object', None,
        ident='1234567890123456789', parent='9876543210123456789', cursor=40).response_shape['thread_hash']
    assert all(secret not in caplog.text for secret in ('secret-', 'private.invalid',
        '1234567890123456789', '9876543210123456789'))
    # No raw payload survives on the exception for later loggers to serialize.
    assert 'secret-' not in repr(exc.__dict__)


@pytest.mark.asyncio
async def test_failed_thread_does_not_block_healthy_threads_and_retries_exact_page(isolated):
    f = fetcher([page(raw(), raw('200'))], [page(raw('101'), more=True, cursor=20),
                                         {'comments': None, 'has_more': False}, page(raw('201'))])
    result, error = await collect(isolated, f)
    assert error and result['replies'] == 2 and result['state'] == 'partial'
    assert [call.args[1:] for call in f._client.get_sub_comments.await_args_list] == [
        ('100', 0), ('100', 20), ('200', 0)]
    assert result['checkpoint']['reply_pending'] == {'100': 20}
    assert result['checkpoint']['reply_after'] == '200'
    wake(isolated)
    f = fetcher(replies=[page(raw('102'))])
    result, error = await collect(isolated, f)
    f._client.get_aweme_comments.assert_not_awaited()
    assert f._client.get_sub_comments.await_args.args == ('123', '100', 20)
    assert error is None and result['state'] == 'completed' and result['replies'] == 3
    assert not result['checkpoint']['reply_pending'] and repo.fully_traversed(isolated, '123')


@pytest.mark.asyncio
async def test_retry_failure_rotates_and_does_not_repeat_in_same_slice(isolated):
    first, _ = await collect(isolated, fetcher([page(raw(), raw('200'), raw('300'))],
                                             [{'has_more': False}, {'has_more': False}, page()]))
    assert first['checkpoint']['reply_pending'] == {'100': 0, '200': 0}
    wake(isolated)
    f = fetcher(replies=[{'has_more': False}, page(raw('201'))])
    result, error = await collect(isolated, f)
    assert error and result['checkpoint']['reply_pending'] == {'100': 0}
    assert [call.args[1] for call in f._client.get_sub_comments.await_args_list] == ['100', '200']
    assert result['checkpoint']['reply_after'] == '300'


@pytest.mark.asyncio
async def test_pending_pagination_resumes_across_slice_budget(isolated):
    await collect(isolated, fetcher(replies=[{'has_more': False}]))
    wake(isolated)
    f = fetcher(replies=[page(raw(str(1000+i)), more=True, cursor=(i+1)*20) for i in range(10)])
    result, error = await collect(isolated, f)
    assert not error and result['requests'] == 10 and result['state'] == 'partial'
    assert result['checkpoint']['reply_pending'] == {'100': 200}
    assert result['checkpoint']['reply_parent'] == '100'
    wake(isolated)
    f = fetcher(replies=[page(raw('2000'))])
    result, error = await collect(isolated, f)
    assert f._client.get_sub_comments.await_args.args == ('123', '100', 200)
    assert not error and result['state'] == 'completed' and result['replies'] == 11


@pytest.mark.asyncio
async def test_many_bad_threads_obey_budget_and_continue_forward(isolated):
    f = fetcher([page(*[raw(str(100+i)) for i in range(20)])], [{'has_more': False}] * 9)
    result, error = await collect(isolated, f)
    assert error and result['requests'] == 10 and len(result['checkpoint']['reply_pending']) == 9
    wake(isolated)
    f = fetcher(replies=[page()] * 10)
    result, error = await collect(isolated, f)
    assert not error and result['requests'] == 10 and result['state'] == 'partial'
    assert f._client.get_sub_comments.await_args_list[0].args == ('123', '109', 0)
    assert len(result['checkpoint']['reply_pending']) == 9


@pytest.mark.parametrize('failure', [
    {'status_code': 429}, {'status_code': 403}, {'status_code': 8}, {'status_code': 9},
    RuntimeError('评论接口风控'), TimeoutError('network timeout'),
    RuntimeError('browser disconnected'), sqlite3.OperationalError('disk failure'),
])
@pytest.mark.asyncio
async def test_global_failures_stop_without_deferring_or_requesting_siblings(isolated, failure):
    f = fetcher([page(raw(), raw('200'))], [failure, page(raw('201'))])
    result, error = await collect(isolated, f)
    assert error and result['state'] == 'partial' and not result['checkpoint']['reply_pending']
    assert f._client.get_sub_comments.await_count == 1 and not result['checkpoint']['replies_done']
    if isinstance(failure, dict):assert result['error_code'] == 'risk_control'


@pytest.mark.asyncio
async def test_risk_after_deferred_thread_remains_global_failure(isolated):
    f = fetcher([page(raw(), raw('200'), raw('300'))], [{'has_more': False}, {'status_code': 429}])
    result, error = await collect(isolated, f)
    assert result['error_code'] == 'risk_control' and result['checkpoint']['reply_pending'] == {'100': 0}
    assert f._client.get_sub_comments.await_count == 2
    assert classify_collection_error(error).error_code == 'risk_control'


@pytest.mark.asyncio
async def test_wrong_work_identity_does_not_defer_as_format_failure(isolated):
    f = fetcher([page(raw(), raw('200'))], [page(raw('101', aweme_id='999'))])
    result, error = await collect(isolated, f)
    assert error and not result['checkpoint']['reply_pending']
    assert f._client.get_sub_comments.await_count == 1 and result['replies'] == 0


@pytest.mark.asyncio
async def test_cancel_after_deferral_retains_backlog_and_saved_siblings(isolated):
    entered = asyncio.Event()
    f = fetcher([page(raw(), raw('200'))])
    async def replies(ident, parent, cursor):
        if parent == '100':return {'has_more': False}
        entered.set()
        await asyncio.Event().wait()
    f._client.get_sub_comments = AsyncMock(side_effect=replies)
    task = asyncio.create_task(collect(isolated, f))
    await asyncio.wait_for(entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    previous = repo.progress(isolated, '123')
    assert previous['state'] == 'partial' and previous['checkpoint']['reply_pending'] == {'100': 0}
    wake(isolated)
    result, error = await collect(isolated, fetcher(replies=[page(raw('201')), page(raw('101'))]))
    assert not error and result['state'] == 'completed' and result['replies'] == 2


@pytest.mark.asyncio
async def test_format_failure_diagnostics_only_in_logs_not_public_summary(isolated, caplog):
    caplog.set_level(logging.WARNING, logger='MediaCrawler')
    result, error = await collect(isolated, fetcher(replies=[{'comments': None, 'has_more': False}]))
    assert 'comment_response' in caplog.text and 'comment_response' not in json.dumps(result)
    assert 'thread_hash' not in json.dumps(result) and result['diagnostic_id']
    assert result['diagnostic_id'] == error.collection_diagnostic['diagnostic_id']


@pytest.mark.asyncio
async def test_source_data_and_sidecar_schema_unchanged_through_failure_and_recovery(isolated):
    before = hashlib.sha256(isolated.read_bytes()).hexdigest()
    with repo.connection(isolated) as db:
        schema = [tuple(row) for row in db.execute('SELECT type,name,sql FROM sqlite_schema ORDER BY name')]
    await collect(isolated, fetcher(replies=[{'has_more': False}]))
    wake(isolated)
    result, error = await collect(isolated, fetcher(replies=[page(raw('101'))]))
    assert not error and result['state'] == 'completed'
    assert hashlib.sha256(isolated.read_bytes()).hexdigest() == before
    with repo.connection(isolated) as db:
        assert [tuple(row) for row in db.execute('SELECT type,name,sql FROM sqlite_schema ORDER BY name')] == schema
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'


@pytest.mark.asyncio
async def test_failed_deferral_write_cannot_skip_the_failed_thread(isolated, monkeypatch):
    original = repo.finish
    def fail_checkpoint(source, ident, rows, summary):
        if summary['state'] == 'running' and summary.get('checkpoint', {}).get('reply_pending'):
            raise sqlite3.OperationalError('disk unavailable')
        return original(source, ident, rows, summary)
    monkeypatch.setattr(repo, 'finish', fail_checkpoint)
    f = fetcher([page(raw(), raw('200'))], [{'has_more': False}, page(raw('201'))])
    result, error = await collect(isolated, f)
    assert error and result['error_code'] == 'storage_error'
    assert not result['checkpoint']['reply_pending'] and result['checkpoint']['reply_after'] == ''
    assert f._client.get_sub_comments.await_count == 1
    monkeypatch.setattr(repo, 'finish', original)
    wake(isolated)
    f = fetcher(replies=[page(raw('101')), page(raw('201'))])
    result, error = await collect(isolated, f)
    assert not error and result['state'] == 'completed'
    assert [call.args[1] for call in f._client.get_sub_comments.await_args_list] == ['100', '200']


@pytest.mark.asyncio
async def test_legacy_v1_partial_checkpoint_adapts_without_restarting_roots(isolated):
    repo.enqueue(isolated, 'account', ['123'])
    legacy = {'version': 1, 'generation': 3, 'root_cursor': 20, 'roots_done': True,
              'reply_after': '', 'reply_parent': '100', 'reply_cursor': 20, 'replies_done': False}
    repo.finish(isolated, '123', [svc.normalize(raw(), '123', '')],
                {'state': 'partial', 'checkpoint': legacy})
    wake(isolated)
    f = fetcher(replies=[{'has_more': False}])
    result, error = await collect(isolated, f)
    assert error and result['checkpoint']['version'] == 1 and result['checkpoint']['generation'] == 3
    assert result['checkpoint']['reply_pending'] == {'100': 20}
    f._client.get_aweme_comments.assert_not_awaited()
    wake(isolated)
    f = fetcher(replies=[page(raw('101'))])
    result, error = await collect(isolated, f)
    assert not error and result['state'] == 'completed'
    assert f._client.get_sub_comments.await_args.args == ('123', '100', 20)


@pytest.mark.asyncio
async def test_pause_after_deferral_stops_siblings_and_preserves_pending(isolated):
    f = fetcher([page(raw(), raw('200'))])
    stopped = False
    async def replies(*args):
        nonlocal stopped
        stopped = True
        return {'has_more': False}
    f.should_stop = lambda: stopped
    f._client.get_sub_comments = AsyncMock(side_effect=replies)
    result, error = await collect(isolated, f)
    assert error and result['error_code'] == 'user_stop'
    assert result['checkpoint']['reply_pending'] == {'100': 0}
    assert f._client.get_sub_comments.await_count == 1
