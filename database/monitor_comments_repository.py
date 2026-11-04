"""Account comment policy, resumable collection queue and sanitized comments.

Independent SQLite sidecar; reads never initialize storage or touch source data.
"""
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

DEFAULTS = {'enabled': False, 'include_replies': True}
DDL = '''
CREATE TABLE policies(account_key TEXT PRIMARY KEY,payload TEXT NOT NULL);
CREATE TABLE collections(aweme_id TEXT PRIMARY KEY,account_key TEXT NOT NULL,state TEXT NOT NULL,
 updated_at INTEGER NOT NULL,next_at INTEGER NOT NULL,payload TEXT NOT NULL);
CREATE INDEX comment_due ON collections(account_key,next_at);
CREATE TABLE comments(aweme_id TEXT NOT NULL,comment_id TEXT NOT NULL,parent_comment_id TEXT NOT NULL,
 payload TEXT NOT NULL,PRIMARY KEY(aweme_id,comment_id));
CREATE INDEX comment_parent ON comments(aweme_id,parent_comment_id);
'''


@contextmanager
def connection(source, write=False):
    source=Path(source).resolve();path=source.with_name('monitor_comments.db')
    if path.is_symlink() or (path.exists() and source.exists() and path.samefile(source)):
        raise ValueError('评论存储路径不可用')
    if not path.exists() and not write:
        yield None;return
    db=sqlite3.connect(str(path) if write else path.as_uri()+'?mode=ro',uri=not write,timeout=5)
    db.row_factory=sqlite3.Row
    try:
        if write and not db.execute("SELECT 1 FROM sqlite_schema WHERE name='policies'").fetchone():
            db.executescript('BEGIN IMMEDIATE;'+DDL+'COMMIT;')
        db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        yield db
        if write:db.commit()
    except BaseException:
        db.rollback();raise
    finally:db.close()


def policy(source, key):
    with connection(source) as db:
        row=db.execute('SELECT payload FROM policies WHERE account_key=?',(key,)).fetchone() if db else None
        saved=json.loads(row[0]) if row else {}
        # Legacy count limits no longer constrain collection, including saved policies.
        return {key:saved.get(key,value) for key,value in DEFAULTS.items()}


def save_policy(source, key, value):
    value={name:value.get(name,default) for name,default in DEFAULTS.items()}
    old=policy(source,key)
    with connection(source,True) as db:
        db.execute('INSERT INTO policies VALUES(?,?) ON CONFLICT(account_key) DO UPDATE SET payload=excluded.payload',
                   (key,json.dumps(value)))
        if value['enabled'] and (not old['enabled'] or value['include_replies'] and not old['include_replies']):
            db.execute("UPDATE collections SET next_at=0 WHERE account_key=? AND state NOT IN ('running','expired')",(key,))
    return value


def enqueue(source,key,ids):
    if not ids:return
    with connection(source,True) as db:
        for ident in ids:
            db.execute('INSERT OR IGNORE INTO collections VALUES(?,?,?,0,0,?)',(ident,key,'pending','{}'))


def request_snapshot_refresh(source,key,ident):
    """A committed snapshot requests another traversal without losing current progress."""
    now=int(time.time())
    with connection(source,True) as db:
        row=db.execute('SELECT * FROM collections WHERE aweme_id=?',(ident,)).fetchone()
        if row and row['account_key']!=key:raise ValueError('评论队列账号不匹配')
        previous=json.loads(row['payload']) if row else {}
        previous['refresh_generation']=previous.get('refresh_generation',0)+1
        state=row['state'] if row and row['state']!='expired' else 'pending'
        # A new snapshot bypasses the six-hour refresh interval, not error backoff
        # or the per-post minimum request interval. Running leases remain intact.
        next_at=(row['next_at'] if row and (state=='running' or previous.get('error_code')) else
                 min(row['next_at'],max(now,row['updated_at']+60)) if row else now)
        db.execute('INSERT INTO collections VALUES(?,?,?,?,?,?) ON CONFLICT(aweme_id) DO UPDATE SET '
                   'state=excluded.state,next_at=excluded.next_at,payload=excluded.payload',
                   (ident,key,state,row['updated_at'] if row else 0,next_at,json.dumps(previous,ensure_ascii=False)))


def due(source,key,limit=3):
    with connection(source) as db:
        if db is None:return []
        now=int(time.time())
        return [r[0] for r in db.execute("SELECT aweme_id FROM collections WHERE state!='expired' AND account_key=? AND next_at<=? "
            "AND (state!='running' OR updated_at<=?) ORDER BY next_at,aweme_id LIMIT ?",(key,now,now-600,limit))]


def next_due(source, account_keys):
    """One fair time slice across enabled accounts, independent of discovery cadence."""
    if not account_keys:return None
    with connection(source) as db:
        if db is None:return None
        now=int(time.time());slots=','.join('?' for _ in account_keys)
        row=db.execute(f"SELECT c.aweme_id FROM collections c JOIN policies p USING(account_key) "
            f"WHERE c.account_key IN ({slots}) AND json_extract(p.payload,'$.enabled')=1 "
            "AND c.state!='expired' AND c.next_at<=? AND (c.state!='running' OR c.updated_at<=?) "
            "ORDER BY c.next_at,c.updated_at,c.aweme_id LIMIT 1",(*account_keys,now,now-600)).fetchone()
        return row[0] if row else None


def progress(source,ident):
    with connection(source) as db:
        row=db.execute('SELECT payload FROM collections WHERE aweme_id=?',(ident,)).fetchone() if db else None
        return json.loads(row[0]) if row else {}


def fully_traversed(source,ident):
    previous=progress(source,ident);checkpoint=previous.get('checkpoint',{})
    return (checkpoint.get('version')==1 and checkpoint.get('roots_done') and checkpoint.get('replies_done')
            and checkpoint.get('generation',0)>=previous.get('refresh_generation',0))


def next_parent(source,ident,after):
    with connection(source) as db:
        # Seek by the existing primary key; don't sort all remaining roots per reply.
        row=db.execute("SELECT comment_id FROM comments INDEXED BY sqlite_autoindex_comments_1 WHERE aweme_id=? AND parent_comment_id='' "
                       'AND comment_id>? ORDER BY comment_id LIMIT 1',(ident,after)).fetchone() if db else None
        return row[0] if row else None


def expire(source,ident):
    with connection(source,True) as db:
        db.execute("UPDATE collections SET state='expired' WHERE aweme_id=?",(ident,))


def claim(source,key,ident,manual=False):
    now=int(time.time())
    with connection(source,True) as db:
        row=db.execute('SELECT * FROM collections WHERE aweme_id=?',(ident,)).fetchone()
        if row and (row['account_key']!=key or (row['updated_at']+60>now if manual else row['next_at']>now)
                    or (row['state']=='running' and row['updated_at']>now-600)):
            return False
        db.execute('INSERT INTO collections VALUES(?,?,?,?,?,?) ON CONFLICT(aweme_id) DO UPDATE SET '
                   "state='running',updated_at=excluded.updated_at",(ident,key,'running',now,now,'{}'))
    return True


def finish(source,ident,comments,summary):
    """Atomically commit a full page together with its resume cursor (no schema change)."""
    now=int(time.time())
    with connection(source,True) as db:
        row=db.execute('SELECT payload FROM collections WHERE aweme_id=?',(ident,)).fetchone()
        previous=json.loads(row[0]) if row else {}
        summary=dict(summary)
        if 'refresh_generation' in previous:
            summary['refresh_generation']=previous['refresh_generation']
            checkpoint=summary.get('checkpoint',{})
            if summary['state']=='completed' and checkpoint.get('generation',0)<previous['refresh_generation']:
                # A snapshot arrived during unfinished traversal: finish it first,
                # then revisit the newest root page in a separate time slice.
                summary.update(state='partial',continuation=True,message='快照已更新，进度已保存，等待补采最新评论',
                    checkpoint={'version':1,'generation':previous['refresh_generation'],'root_cursor':0,
                                'roots_done':False,'reply_after':'','reply_parent':'','reply_cursor':0,'replies_done':False})
        for item in comments:
            old=db.execute('SELECT parent_comment_id FROM comments WHERE aweme_id=? AND comment_id=?',
                           (ident,item['comment_id'])).fetchone()
            if old and old[0]!=item['parent_comment_id']:raise ValueError('评论回复关系冲突')
            db.execute('INSERT INTO comments VALUES(?,?,?,?) ON CONFLICT(aweme_id,comment_id) DO UPDATE SET '
                'parent_comment_id=excluded.parent_comment_id,payload=excluded.payload',
                (ident,item['comment_id'],item['parent_comment_id'],json.dumps(item,ensure_ascii=False)))
        # Count limits do not end traversal: partial work resumes in another slice.
        delay=1800 if summary.get('error_code') else 21600 if summary['state']=='completed' else 60
        db.execute('UPDATE collections SET state=?,updated_at=?,next_at=?,payload=? WHERE aweme_id=?',
            (summary['state'],now,now+delay,json.dumps(summary,ensure_ascii=False),ident))
    return summary


def counts(source,ident):
    with connection(source) as db:
        if db is None:return {'root_comments':0,'replies':0}
        row=db.execute("SELECT count(*),coalesce(sum(parent_comment_id=''),0) FROM comments WHERE aweme_id=?",(ident,)).fetchone()
        return {'root_comments':row[1],'replies':row[0]-row[1]}


def read(source,ident,page=1,parent=''):
    with connection(source) as db:
        if db is None:return {'items':[],'total':0,'total_saved':0,'collection':None}
        row=db.execute('SELECT state,updated_at,payload FROM collections WHERE aweme_id=?',(ident,)).fetchone()
        total=db.execute('SELECT count(*) FROM comments WHERE aweme_id=? AND parent_comment_id=?',(ident,parent)).fetchone()[0]
        items=[json.loads(r[0]) for r in db.execute('SELECT payload FROM comments WHERE aweme_id=? AND parent_comment_id=? '
            "ORDER BY json_extract(payload,'$.like_count') DESC,comment_id LIMIT 20 OFFSET ?",(ident,parent,(page-1)*20))]
        for item in items:
            item['saved_replies']=db.execute('SELECT count(*) FROM comments WHERE aweme_id=? AND parent_comment_id=?',
                                            (ident,item['comment_id'])).fetchone()[0]
        count=db.execute('SELECT count(*) FROM comments WHERE aweme_id=?',(ident,)).fetchone()[0]
        return {'items':items,'total':total,'total_saved':count,
                'collection':json.loads(row['payload'])|{'state':row['state'],'updated_at':row['updated_at']} if row else None}
