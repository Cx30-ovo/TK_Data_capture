"""Bound comment-list reads and atomically observe policy changes in isolated SQLite."""
import hashlib
import json
import sqlite3

import pytest

from database import monitor_comments_repository as repo


@pytest.fixture
def storage(tmp_path):
    source = tmp_path / 'source.db'
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE original(value TEXT)')
        db.execute("INSERT INTO original VALUES('unchanged')")
    repo.save_policy(source, 'account', {'enabled': True, 'include_replies': False})
    repo.enqueue(source, 'account', ['123', '456'])
    rows = []
    for index in range(25):
        root = str(100 + index)
        rows.append({'comment_id': root, 'parent_comment_id': '', 'content': '主评论', 'like_count': 100 - index})
        for child in range(index):
            rows.append({'comment_id': str(1000 + index * 100 + child), 'parent_comment_id': root,
                         'content': '子评论', 'like_count': child})
    repo.finish(source, '123', rows, {'state': 'completed'})
    # Reused comment IDs on another work must not contribute to these counts.
    repo.finish(source, '456', [{'comment_id': str(5000 + index), 'parent_comment_id': '100', 'content': '其他作品'}
                              for index in range(30)], {'state': 'completed'})
    return source


@pytest.mark.parametrize('page,parent,expected_ids,total', [
    (1, '', [str(100 + index) for index in range(20)], 25),
    (2, '', [str(100 + index) for index in range(20, 25)], 25),
    (3, '', [], 25),
    (1, '124', [str(3400 + index) for index in reversed(range(4, 24))], 24),
])
def test_comment_pages_keep_exact_counts_with_bounded_read_queries(storage, monkeypatch, page, parent, expected_ids, total):
    source_sha = hashlib.sha256(storage.read_bytes()).digest()
    sidecar = storage.with_name('monitor_comments.db')
    before = sidecar.read_bytes()
    statements = []
    real_connect = sqlite3.connect

    def observe(*args, **kwargs):
        db = real_connect(*args, **kwargs)
        db.set_trace_callback(statements.append)
        return db

    monkeypatch.setattr(repo.sqlite3, 'connect', observe)
    result = repo.read(storage, '123', page=page, parent=parent)
    assert result['total'] == total and result['total_saved'] == 325
    assert result['collection']['state'] == 'completed'
    assert [item['comment_id'] for item in result['items']] == expected_ids
    for item in result['items']:
        assert item['saved_replies'] == (0 if parent else int(item['comment_id']) - 100)
    selects = [statement for statement in statements if statement.lstrip().upper().startswith('SELECT')]
    assert len(selects) <= 5, f'A single list read issued {len(selects)} SELECTs'
    assert hashlib.sha256(storage.read_bytes()).digest() == source_sha
    assert sidecar.read_bytes() == before
    assert not sidecar.with_name(sidecar.name + '-journal').exists()


@pytest.mark.parametrize('initial,competing', [
    ({'enabled': True, 'include_replies': False}, {'enabled': False, 'include_replies': False}),
    ({'enabled': True, 'include_replies': True}, {'enabled': True, 'include_replies': False}),
])
def test_policy_observes_other_writer_before_its_write_lock(storage, monkeypatch, initial, competing):
    repo.save_policy(storage, 'account', initial)
    sidecar = storage.with_name('monitor_comments.db')
    with repo.connection(storage, True) as db:
        db.execute("UPDATE collections SET state='partial',next_at=9999999999 WHERE aweme_id='123'")
        db.execute("UPDATE collections SET state='running',next_at=9999999999 WHERE aweme_id='456'")
        db.execute("INSERT INTO collections VALUES('789','account','expired',0,9999999999,'{}')")
        db.execute("INSERT INTO collections VALUES('999','other','partial',0,9999999999,'{}')")
    source_sha = hashlib.sha256(storage.read_bytes()).digest()
    real_connect = sqlite3.connect
    competed = []

    class InterleavedConnection(sqlite3.Connection):
        def execute(self, statement, *args, **kwargs):
            if statement == 'BEGIN IMMEDIATE' and not competed:
                competed.append(True)
                # Another client commits before our lock is acquired. Decisions
                # must use its committed policy rather than an earlier read.
                other = real_connect(sidecar)
                try:
                    other.execute('UPDATE policies SET payload=? WHERE account_key=?',
                                  (json.dumps(competing), 'account'))
                    other.commit()
                finally:
                    other.close()
            return super().execute(statement, *args, **kwargs)

    monkeypatch.setattr(repo.sqlite3, 'connect', lambda *args, **kw: real_connect(*args, **kw, factory=InterleavedConnection))
    assert repo.save_policy(storage, 'account', initial) == initial
    assert competed == [True]
    with repo.connection(storage) as db:
        times = dict(db.execute('SELECT aweme_id,next_at FROM collections'))
        assert json.loads(db.execute("SELECT payload FROM policies WHERE account_key='account'").fetchone()[0]) == initial
    assert times == {'123': 0, '456': 9999999999, '789': 9999999999, '999': 9999999999}
    assert hashlib.sha256(storage.read_bytes()).digest() == source_sha


def test_atomic_policy_defaults_support_legacy_payload_and_do_not_requeue_unchanged(storage):
    with repo.connection(storage, True) as db:
        db.execute("UPDATE policies SET payload=? WHERE account_key='account'", ('{"enabled":true}',))
        db.execute('UPDATE collections SET next_at=9999999999')
    repo.save_policy(storage, 'account', {'enabled': True, 'include_replies': True})
    with repo.connection(storage) as db:
        assert {row[0] for row in db.execute('SELECT next_at FROM collections')} == {9999999999}
    assert repo.policy(storage, 'account') == {'enabled': True, 'include_replies': True}
