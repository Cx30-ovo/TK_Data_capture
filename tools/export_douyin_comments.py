"""Stream TK's comment sidecar as JSONL without modifying either source database.

The destination importer must match external_work_id to an existing Douyin work
and upsert by (platform, external_comment_id). This tool does not deploy or write
to the collection dashboard.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys


def iso_time(value):
    if type(value) not in (int, float) or value <= 0:
        return None
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def export_comments(source_db, work_id=None):
    path = Path(source_db).resolve(strict=True)
    # Do not use immutable=1: live SQLite WAL updates must remain visible.
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        query = 'SELECT aweme_id,comment_id,parent_comment_id,payload FROM comments'
        params = ()
        if work_id is not None:
            query += ' WHERE aweme_id=?'
            params = (str(work_id),)
        query += ' ORDER BY aweme_id,comment_id'
        for row in db.execute(query, params):
            item = json.loads(row['payload'])
            if not isinstance(item, dict) or not isinstance(item.get('content'), str):
                raise ValueError('Invalid comment payload')
            if str(item.get('comment_id')) != row['comment_id']:
                raise ValueError('Comment identity mismatch')
            parent = row['parent_comment_id'] or None
            if (item.get('parent_comment_id') or None) != parent:
                raise ValueError('Comment thread mismatch')
            yield {
                'platform': 'douyin', 'external_work_id': row['aweme_id'],
                'external_comment_id': row['comment_id'],
                'parent_comment_id': parent,
                'root_comment_id': parent or row['comment_id'],
                'reply_to_comment_id': item.get('reply_to_comment_id'),
                'reply_relation_source': item.get('reply_relation_source', 'unknown'),
                'author_name': item.get('nickname', ''),
                'content': item['content'], 'like_count': item.get('like_count', 0),
                'reply_count': item.get('reply_count', 0),
                'published_at': iso_time(item.get('create_time')),
                # Source payload is refreshed in place, so this is latest
                # observation, not necessarily the first collection time.
                'source_captured_at': iso_time(item.get('captured_at')),
                'source': 'tk_monitor_comments',
            }
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-db', required=True, help='Path to monitor_comments.db')
    parser.add_argument('--work-id', help='Optional single Douyin work ID')
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    for item in export_comments(args.source_db, args.work_id):
        print(json.dumps(item, ensure_ascii=False))


if __name__ == '__main__':
    main()
