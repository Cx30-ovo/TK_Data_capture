"""Independent topic metadata, collected works and immutable observations.

Only explicit configuration writes initialize this sidecar. Existing collection
tables are neither initialized nor changed by this module.
"""
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class TopicError(ValueError):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


DDL = '''
CREATE TABLE topic_tasks(id TEXT PRIMARY KEY,version INTEGER NOT NULL,config TEXT NOT NULL,created_at INTEGER NOT NULL,last_attempt INTEGER,last_success INTEGER,error TEXT);
CREATE TABLE topic_works(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
CREATE TABLE topic_members(topic_id TEXT NOT NULL REFERENCES topic_tasks(id),work_id TEXT NOT NULL REFERENCES topic_works(id),first_seen INTEGER NOT NULL,PRIMARY KEY(topic_id,work_id));
CREATE TABLE topic_runs(id TEXT PRIMARY KEY,topic_id TEXT NOT NULL REFERENCES topic_tasks(id),state TEXT NOT NULL,started_at INTEGER NOT NULL,finished_at INTEGER,summary TEXT);
CREATE UNIQUE INDEX topic_one_running ON topic_runs(topic_id) WHERE state='running';
CREATE TABLE topic_observations(run_id TEXT NOT NULL REFERENCES topic_runs(id),work_id TEXT NOT NULL REFERENCES topic_works(id),captured_at INTEGER NOT NULL,metrics TEXT NOT NULL,PRIMARY KEY(run_id,work_id));
CREATE INDEX topic_observations_work_time ON topic_observations(work_id,captured_at);
'''


def path_for(source):
    original = Path(source).resolve()
    path = original.with_name('topic_monitor.db')
    if path.is_symlink() or path == original or (path.exists() and original.exists() and path.samefile(original)):
        raise TopicError('话题存储路径不可用', 503)
    return path


@contextmanager
def connection(source, *, write=False, initialize=False):
    path = path_for(source)
    if not path.exists() and not initialize:
        if write:
            raise TopicError('话题存储尚未初始化', 503)
        yield None
        return
    if initialize:
        path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path) if initialize else path.as_uri()+('?mode=rw' if write else '?mode=ro'),
                         uri=not initialize, timeout=5)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA foreign_keys=ON')
        if initialize and not db.execute("SELECT 1 FROM sqlite_schema WHERE name='topic_tasks'").fetchone():
            db.executescript('BEGIN IMMEDIATE;'+DDL+'COMMIT;')
        db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        yield db
        if write:
            db.commit()
    except sqlite3.Error as exc:
        db.rollback()
        raise TopicError('话题存储不可用，不自动覆盖或修复', 503) from exc
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def task(row):
    config = json.loads(row['config'])
    monitoring_at = config.pop('_monitoring_at', None)
    backfill = config.pop('_backfill', None) or initial_backfill(config, row['created_at'])
    return {'id': row['id'], 'version': row['version'], **config, 'backfill': backfill, 'last_monitoring_at': monitoring_at,
            'created_at': row['created_at'], 'last_attempt': row['last_attempt'],
            'last_success': row['last_success'], 'error': row['error'],
            'running_since':row['running_since'] if 'running_since' in row.keys() else None}


def initial_backfill(config, created_at):
    end = min(created_at, config['end_at'])
    complete = config['start_at'] >= end
    return {'version': 1, 'start_at': config['start_at'], 'end_at': end,
            'status': 'complete' if complete else 'pending',
            'completed_at': created_at if complete else None, 'reason': None,
            'keywords': [{'keyword': keyword, 'offset': 0, 'search_id': '', 'pages': 0,
                          'complete': complete} for keyword in config['keywords']]}


def listing(source):
    with connection(source) as db:
        return [task(r) for r in db.execute("SELECT t.*,(SELECT max(started_at) FROM topic_runs r WHERE r.topic_id=t.id AND r.state='running') AS running_since FROM topic_tasks t ORDER BY created_at DESC,id")] if db else []


def read(source, topic_id):
    with connection(source) as db:
        row = db.execute('SELECT * FROM topic_tasks WHERE id=?', (topic_id,)).fetchone() if db else None
        if not row:
            raise TopicError('话题监控不存在', 404)
        return task(row)


def create(source, config):
    topic_id = uuid.uuid4().hex
    with connection(source, write=True, initialize=True) as db:
        if db.execute('SELECT count(*) FROM topic_tasks').fetchone()[0] >= 50:
            raise TopicError('最多保留50个话题监控，本期不自动删除历史数据')
        db.execute('INSERT INTO topic_tasks(id,version,config,created_at) VALUES(?,1,?,?)',
                   (topic_id, json.dumps(config, ensure_ascii=False), int(time.time())))
    return read(source, topic_id)


def update(source, topic_id, version, config):
    with connection(source, write=True) as db:
        row = db.execute('SELECT * FROM topic_tasks WHERE id=?', (topic_id,)).fetchone()
        if not row:
            raise TopicError('话题监控不存在', 404)
        if row['version'] != version:
            raise TopicError('话题设置已更新，请重新读取后重试', 409)
        old = json.loads(row['config'])
        if any(config[k] != old[k] for k in ('name','keywords','start_at','end_at')):
            raise TopicError('话题与时间范围固定；调整范围请新建监控，旧数据保留')
        if '_backfill' in old:
            config = {**config, '_backfill': old['_backfill']}
        if '_monitoring_at' in old:
            config = {**config, '_monitoring_at': old['_monitoring_at']}
        db.execute('UPDATE topic_tasks SET version=version+1,config=? WHERE id=?',
                   (json.dumps(config, ensure_ascii=False), topic_id))
    return read(source, topic_id)


def claim(source, topic_id, *, manual=False):
    now = int(time.time())
    with connection(source, write=True) as db:
        row = db.execute('SELECT * FROM topic_tasks WHERE id=?', (topic_id,)).fetchone()
        if not row:
            raise TopicError('话题监控不存在', 404)
        value = task(row)
        if not value['enabled']:
            return None
        running = db.execute("SELECT * FROM topic_runs WHERE topic_id=? AND state='running'", (topic_id,)).fetchone()
        if running and running['started_at'] > now-600:
            return None
        if running:
            db.execute("UPDATE topic_runs SET state='interrupted',finished_at=?,summary=? WHERE id=?",
                       (now, json.dumps({'error':'上次采集未完成，不宣称成功'}), running['id']))
        if value['start_at'] > now:
            return None
        backfill = value['backfill']
        if backfill['status'] == 'blocked':
            return None
        interrupted = value['last_attempt'] and db.execute("SELECT 1 FROM topic_runs WHERE topic_id=? AND started_at=? AND state='interrupted'",(topic_id,value['last_attempt'])).fetchone()
        interval = collection_interval(value)
        if not running and not interrupted and not manual and value['last_attempt'] and now-value['last_attempt'] < interval:
            return None
        # One bounded final sweep after the publication window closes, then stop.
        if window_complete(value):
            return None
        run_id = uuid.uuid4().hex
        db.execute('INSERT INTO topic_runs(id,topic_id,state,started_at) VALUES(?,?,?,?)', (run_id,topic_id,'running',now))
        db.execute('UPDATE topic_tasks SET last_attempt=?,error=NULL WHERE id=?', (now,topic_id))
        return {'run_id':run_id,'config':value}


def window_complete(value):
    backfill=value['backfill']
    return backfill['status']=='complete' and (backfill['end_at']>=value['end_at'] or
        (value.get('last_monitoring_at') or 0)>=value['end_at'])


def collection_interval(value):
    initial_live=value['backfill']['status']=='complete' and not value.get('last_monitoring_at')
    return 65 if not value.get('error') and (value['backfill']['status']=='pending' or initial_live) else value['interval_minutes']*60


def delete(source, topic_id, version):
    with connection(source, write=True) as db:
        row = db.execute('SELECT version FROM topic_tasks WHERE id=?',(topic_id,)).fetchone()
        if not row:raise TopicError('话题监控不存在',404)
        if row['version'] != version:raise TopicError('话题设置已更新，请重新读取后重试',409)
        work_ids=[r['work_id'] for r in db.execute('SELECT work_id FROM topic_members WHERE topic_id=?',(topic_id,))]
        db.execute('DELETE FROM topic_observations WHERE run_id IN (SELECT id FROM topic_runs WHERE topic_id=?)',(topic_id,))
        db.execute('DELETE FROM topic_runs WHERE topic_id=?',(topic_id,))
        db.execute('DELETE FROM topic_members WHERE topic_id=?',(topic_id,))
        db.execute('DELETE FROM topic_tasks WHERE id=?',(topic_id,))
        db.executemany('DELETE FROM topic_works WHERE id=? AND NOT EXISTS (SELECT 1 FROM topic_members m WHERE m.work_id=topic_works.id) AND NOT EXISTS (SELECT 1 FROM topic_observations o WHERE o.work_id=topic_works.id)',[(ident,) for ident in work_ids])
    return {'id':topic_id,'deleted':True}


def finish(source, job, works, summary, error=None):
    now = int(time.time());topic_id=job['config']['id'];run_id=job['run_id']
    with connection(source, write=True) as db:
        if not db.execute('SELECT 1 FROM topic_tasks WHERE id=?',(topic_id,)).fetchone():
            return {'saved':0,'error':'话题监控已删除，本轮结果已丢弃'}
        run = db.execute('SELECT * FROM topic_runs WHERE id=?', (run_id,)).fetchone()
        if not run or run['state'] != 'running':
            raise TopicError('话题执行租约已失效，未覆盖结果', 409)
        current = task(db.execute('SELECT * FROM topic_tasks WHERE id=?', (topic_id,)).fetchone())
        if not current['enabled'] or current['version'] != job['config']['version']:
            error = '监控已暂停或设置变化，本轮不保存采集内容'
            works = []
        new_ids={w['id'] for w in works if not db.execute('SELECT 1 FROM topic_works WHERE id=?',(w['id'],)).fetchone()}
        if len(works)>500 or db.execute('SELECT count(*) FROM topic_works').fetchone()[0]+len(new_ids)>50000:
            raise TopicError('话题作品存储达到安全上限，未截断保存')
        for work in works:
            db.execute('INSERT INTO topic_works VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                       (work['id'],json.dumps({k:v for k,v in work.items() if k!='metrics'},ensure_ascii=False)))
            db.execute('INSERT OR IGNORE INTO topic_members VALUES(?,?,?)', (topic_id,work['id'],now))
            db.execute('INSERT OR IGNORE INTO topic_observations VALUES(?,?,?,?)',
                       (run_id,work['id'],now,json.dumps(work['metrics'])))
        result = {**summary,'saved':len(works),'error':error}
        if error is None and (summary.get('backfill_checkpoint') is not None or summary.get('stage')=='monitoring'):
            config = json.loads(db.execute('SELECT config FROM topic_tasks WHERE id=?', (topic_id,)).fetchone()[0])
            if summary.get('backfill_checkpoint') is not None:
                config['_backfill'] = summary['backfill_checkpoint']
            # A round started before the deadline can finish after it. Its
            # publication cutoff, rather than commit time, determines whether
            # the final sweep is still needed.
            if summary.get('stage')=='monitoring':config['_monitoring_at']=summary['observed_until']
            db.execute('UPDATE topic_tasks SET config=? WHERE id=?', (json.dumps(config,ensure_ascii=False),topic_id))
        db.execute('UPDATE topic_runs SET state=?,finished_at=?,summary=? WHERE id=?',
                   ('failed' if error else 'completed',now,json.dumps(result,ensure_ascii=False),run_id))
        db.execute('UPDATE topic_tasks SET error=?,last_success=CASE WHEN ? IS NULL THEN ? ELSE last_success END WHERE id=?',
                   (error,error,now,topic_id))
        return result


def dataset(source, topic_id):
    with connection(source) as db:
        row = db.execute('SELECT * FROM topic_tasks WHERE id=?', (topic_id,)).fetchone() if db else None
        if not row:
            raise TopicError('话题监控不存在', 404)
        works = []
        for record in db.execute('SELECT w.*,m.first_seen FROM topic_works w JOIN topic_members m ON w.id=m.work_id WHERE m.topic_id=?', (topic_id,)):
            observations = [dict(r)|{'metrics':json.loads(r['metrics'])} for r in db.execute(
                'SELECT o.* FROM topic_observations o JOIN topic_runs r ON r.id=o.run_id WHERE o.work_id=? AND r.topic_id=? ORDER BY o.captured_at,o.run_id',
                (record['id'],topic_id))]
            works.append(json.loads(record['payload'])|{'first_seen_at':record['first_seen'],'observations':observations})
        runs = [dict(r)|{'summary':json.loads(r['summary']) if r['summary'] else None} for r in db.execute(
            'SELECT * FROM topic_runs WHERE topic_id=? ORDER BY started_at DESC,id LIMIT 20',(topic_id,))]
        history = db.execute("SELECT count(*) AS rounds,min(started_at) AS first_at,max(started_at) AS last_at FROM topic_runs WHERE topic_id=? AND state='completed'",(topic_id,)).fetchone()
        return task(row)|{'successful_observation_window':dict(history)}, works, runs
