import json
import sqlite3

import pytest

from tools.export_douyin_comments import export_comments


def test_readonly_export_preserves_threads_and_source(tmp_path):
    path = tmp_path / 'monitor_comments.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE comments(aweme_id TEXT,comment_id TEXT,parent_comment_id TEXT,payload TEXT)')
        for work, cid, parent, target in [('123', '10', '', None), ('123', '11', '10', '10'),
                                           ('123', '12', '10', '11'), ('456', '20', '', None)]:
            item = {'comment_id': cid, 'parent_comment_id': parent, 'reply_to_comment_id': target,
                    'content': '评论正文', 'nickname': '已脱敏', 'create_time': 1794268800,
                    'captured_at': 1794268860, 'like_count': 5}
            db.execute('INSERT INTO comments VALUES(?,?,?,?)', (work, cid, parent, json.dumps(item)))
    before = path.read_bytes()
    rows = list(export_comments(path, '123'))
    assert len(rows) == 3
    assert rows[0]['parent_comment_id'] is None and rows[0]['root_comment_id'] == '10'
    assert rows[2]['parent_comment_id'] == rows[2]['root_comment_id'] == '10'
    assert rows[2]['reply_to_comment_id'] == '11'
    assert rows[0]['platform'] == 'douyin' and rows[0]['external_work_id'] == '123'
    assert rows[0]['published_at'].endswith('+00:00')
    assert 'first_seen_at' not in rows[0]
    assert list(export_comments(path, 'missing')) == []
    assert len(list(export_comments(path))) == 4
    assert before == path.read_bytes()


def test_missing_source_is_not_created(tmp_path):
    path = tmp_path / 'missing.db'
    with pytest.raises(FileNotFoundError):
        list(export_comments(path))
    assert not path.exists()
