"""Bounded inference tests: mocked provider, isolated existing schema, no real model calls."""
import hashlib
import json
import sqlite3

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine

from api.routers.monitor import router
from api.services import account_style_service as style
from config.db_config import sqlite_db_config
from database.models import AIAnalysisResult

NOW = 1800000000


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path/'style.db'
    engine = create_engine('sqlite:///'+str(path))
    AIAnalysisResult.__table__.create(engine)
    engine.dispose()
    with sqlite3.connect(path) as conn:
        conn.executescript('''CREATE TABLE douyin_monitored_accounts(id INTEGER PRIMARY KEY,platform TEXT,sec_user_id TEXT,display_name TEXT);
            CREATE TABLE douyin_posts(aweme_id TEXT,platform TEXT,sec_user_id TEXT,title TEXT,create_time INTEGER,first_seen_at INTEGER,status TEXT);
            INSERT INTO douyin_monitored_accounts VALUES(1,'dy','test','测试账号'),(2,'dy','other','另一账号');''')
        conn.executemany('INSERT INTO douyin_posts VALUES(?,?,?,?,?,?,?)', [(str(i),'dy','test',f'厦门社区新变化{i}！ #民生',NOW-100-i,NOW-90,'active') for i in range(8)])
    monkeypatch.setattr(style.time, 'time', lambda: NOW)
    monkeypatch.setattr(style.config, 'ai_config', {'enabled': True, 'model': 'fixture', 'base_url': 'http://127.0.0.1/fixture', 'api_key': ''})
    return path


def provider(*, unknown=False, error=False, seen=None):
    def respond(request):
        body = json.loads(request.content)
        inputs = json.loads(body['messages'][1]['content'])
        if seen is not None:
            seen.append(body)
        if 'post_id' in inputs[0]:
            result={'notes':{k:'本地民生观察' for k in style.DIMENSIONS},'evidence_indices':{k:[0] for k in style.DIMENSIONS},
                    'topic_labels':['本地民生','其他'],'topic_assignments':[i%2 for i in range(len(inputs))]}
        else:
            result = {k: {'text': '可能偏向本地民生，标题级推断待核实', 'summary': '本地民生为主', 'labels': ['本地','民生'], 'evidence_post_ids': ['unknown' if unknown else inputs[0]['evidence_post_ids'][0]]} for k in style.DIMENSIONS}
            result.update(topic_labels=['本地民生','其他'],topic_mapping={t[0]:i%2 for batch in inputs for i,t in enumerate(batch['topics'])},limitations=['仅标题级样本'])
        return httpx.Response(500 if error else 200, json={'choices':[{'message':{'content':json.dumps(result,ensure_ascii=False)}}]})
    return httpx.MockTransport(respond)


def rows(path):
    with sqlite3.connect(path) as conn:
        return conn.execute('SELECT * FROM ai_analysis_results ORDER BY id').fetchall()


@pytest.mark.asyncio
async def test_saved_style_uses_latest_across_windows_and_ignores_post_changes(db,monkeypatch):
    first=await style.analyze_style(str(db),1,30,transport=provider())
    latest=await style.analyze_style(str(db),1,365,transport=provider())
    with sqlite3.connect(db) as conn:conn.execute('DELETE FROM douyin_posts')
    monkeypatch.setattr(style.time,'time',lambda:NOW+90*86400)
    before=db.read_bytes()
    result=await style.read_saved_style(str(db),1)
    assert result['latest']['id']==latest['id']!=first['id']
    assert result['latest']['input_sha256']==latest['input_sha256']
    assert (await style.read_saved_style(str(db),2))['latest'] is None
    assert db.read_bytes()==before
    # Reassigning account identity must not import snapshots from its old identity.
    with sqlite3.connect(db) as conn:conn.execute("UPDATE douyin_monitored_accounts SET sec_user_id='replacement' WHERE id=1")
    assert (await style.read_saved_style(str(db),1))['latest'] is None


@pytest.mark.asyncio
async def test_latest_malformed_saved_snapshot_never_falls_back(db):
    first=await style.analyze_style(str(db),1,transport=provider())
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE ai_analysis_results SET result_json='{}' WHERE id=?",(first['id'],))
    before=db.read_bytes()
    with pytest.raises(style.ProfileUnavailable,match='不回退'):await style.read_saved_style(str(db),1)
    assert db.read_bytes()==before


@pytest.mark.asyncio
async def test_get_is_readonly_and_stable(db, monkeypatch):
    before = db.read_bytes()
    data = await style.read_style(str(db),1)
    assert data['latest'] is None and data['scope']['sampled']==8
    monkeypatch.setattr(style.time,'time',lambda: NOW+1)
    assert (await style.read_style(str(db),1))['input_sha256']==data['input_sha256']
    assert db.read_bytes()==before


@pytest.mark.asyncio
async def test_snapshot_evidence_cache_and_append(db):
    seen=[]
    first = await style.analyze_style(str(db),1,transport=provider(seen=seen))
    original = rows(db)
    assert first['scope']['sampled']==8 and len(seen)==2
    assert sum(t['count'] for t in first['topics']) == 8
    assert len({id for t in first['topics'] for id in t['post_ids']}) == 8
    assert len(first['input_sha256'])==64
    for key in style.DIMENSIONS:
        ref=first[key]['evidence'][0]
        assert ref['field']=='title' and '#' not in ref['snippet']
        assert ref['snippet_sha256']==hashlib.sha256(ref['snippet'].encode()).hexdigest()
    cached=await style.analyze_style(str(db),1,transport=provider(seen=seen))
    assert cached['cached'] and len(seen)==2 and rows(db)==original
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO douyin_posts VALUES('new','dy','test','新增社区建设？',?,?, 'active')",(NOW-2,NOW-1))
    current=await style.read_style(str(db),1)
    assert current['changed'] and current['new_posts']==1
    second=await style.analyze_style(str(db),1,transport=provider())
    assert second['id']!=first['id'] and rows(db)[:1]==original
    assert len((await style.read_style(str(db),1))['versions'])==2
    assert len(rows(db))==2


@pytest.mark.asyncio
@pytest.mark.parametrize('kind',['unknown','error','disabled','small','busy'])
async def test_failures_preserve_original(db, monkeypatch, kind):
    await style.analyze_style(str(db),1,transport=provider())
    if kind=='disabled':
        monkeypatch.setitem(style.config.ai_config,'enabled',False)
    if kind=='small':
        with sqlite3.connect(db) as conn: conn.execute("DELETE FROM douyin_posts WHERE aweme_id NOT IN ('0','1')")
    else:
        with sqlite3.connect(db) as conn: conn.execute("UPDATE douyin_posts SET title='更正材料' WHERE aweme_id='0'")
    before=rows(db)
    if kind=='busy': await style._lock.acquire()
    try:
        with pytest.raises(style.GroupingError):
            await style.analyze_style(str(db),1,transport=provider(unknown=kind=='unknown',error=kind=='error'))
    finally:
        if kind=='busy': style._lock.release()
    assert rows(db)==before


@pytest.mark.asyncio
async def test_scope_bounded_and_identity(db):
    with sqlite3.connect(db) as conn:
        conn.executemany('INSERT INTO douyin_posts VALUES(?,?,?,?,?,?,?)',[(f'p{i}','dy','test',f'测试标题{i}',NOW-200-i,NOW-1,'active') for i in range(80)])
        conn.execute("INSERT INTO douyin_posts VALUES('other','dy','other','不能引用',?,?, 'active')",(NOW-2,NOW-1))
        conn.execute("INSERT INTO douyin_posts VALUES('future','dy','test','不能引用',?,?, 'active')",(NOW+2,NOW-1))
        conn.execute("INSERT INTO douyin_posts VALUES('late','dy','test','不能引用',?,?, 'active')",(NOW-2,NOW+1))
    data=await style.source(str(db),1,30)
    assert len(data['titles'])==88 and data['scope']['eligible']==88
    assert not {'future','late','other'} & set(data['source_hashes'])
    await style.analyze_style(str(db),1,transport=provider())
    with sqlite3.connect(db) as conn: conn.execute("UPDATE douyin_monitored_accounts SET sec_user_id='new-owner' WHERE id=1")
    assert (await style.read_style(str(db),1))['latest'] is None


@pytest.mark.asyncio
async def test_api_missing_store_no_autocreate(db, monkeypatch):
    monkeypatch.setitem(sqlite_db_config,'db_path',str(db))
    app=FastAPI(); app.include_router(router,prefix='/api')
    before=db.read_bytes()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1') as client:
        assert (await client.get('/api/monitor/accounts/1/style-profile')).status_code==200
        assert (await client.get('/api/monitor/accounts/1/style-profile?days=0')).status_code==422
        assert (await client.get('/api/monitor/accounts/999/style-profile')).status_code==404
    assert db.read_bytes()==before
    with sqlite3.connect(db) as conn: conn.execute('DROP TABLE ai_analysis_results')
    before=db.read_bytes()
    with pytest.raises(style.ProfileUnavailable): await style.read_style(str(db),1)
    assert db.read_bytes()==before


@pytest.mark.parametrize('length,count', [(20,700),(1490,500)])
def test_expanded_sampling_budget_and_whole_titles(length,count):
    inputs=[{'post_id':str(i),'snippet':'字'*length,'published_at':NOW-i} for i in range(count)]
    selected,size=style.sample_titles(inputs)
    assert len(selected)==500
    batches=style.plan_batches(selected)
    assert [p for batch in batches for p in batch]==selected
    for batch in batches:
        assert len(batch)<=style.BATCH_SIZE
        payload=json.dumps(style.model_titles(batch),ensure_ascii=False,separators=(',', ':'))
        assert len(payload)<=style.INPUT_CHAR_BUDGET and len(payload.encode())<=style.model_budget()[2]
    assert selected[0]==inputs[0] and selected[-1]==inputs[-1]
    assert len({p['post_id'] for p in selected})==len(selected)
    assert all(len(p['snippet'])==length for p in selected)
    assert style.sample_titles(inputs)==(selected,size)


@pytest.mark.asyncio
@pytest.mark.parametrize('bad',['missing','unknown','duplicate','boolean','float'])
async def test_topic_coverage_must_validate_before_persist(db,bad):
    def respond(request):
        titles=json.loads(json.loads(request.content)['messages'][1]['content'])
        result={'notes':{k:'本地观察' for k in style.DIMENSIONS},'evidence_indices':{k:[0] for k in style.DIMENSIONS},
                'topic_labels':['本地','其他'],'topic_assignments':[0]*len(titles)}
        if bad=='missing': result['topic_assignments'].pop()
        if bad=='unknown': result['topic_assignments'][0]=2
        if bad=='duplicate': result['topic_labels']=['本地','本地']
        if bad=='boolean': result['topic_assignments'][0]=True
        if bad=='float': result['topic_assignments'][0]=0.2
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(result,ensure_ascii=False)}}]})
    before=db.read_bytes()
    with pytest.raises(style.GroupingError):
        await style.analyze_style(str(db),1,transport=httpx.MockTransport(respond))
    assert db.read_bytes()==before


@pytest.mark.asyncio
async def test_legacy_snapshot_read_preserves_bytes_and_upgrade_appends(db):
    old=await style.analyze_style(str(db),1,transport=provider())
    with sqlite3.connect(db) as conn:
        value=json.loads(conn.execute('SELECT result_json FROM ai_analysis_results WHERE id=?',(old['id'],)).fetchone()[0])
        value['version']='account-style-v0.1'; value['binding_sha256']='legacy-binding'
        value['scope']['sampled']=5
        value.pop('topics')
        for key in style.DIMENSIONS:
            value[key].pop('summary'); value[key].pop('labels')
        conn.execute('UPDATE ai_analysis_results SET result_json=? WHERE id=?',(json.dumps(value,ensure_ascii=False),old['id']))
    original=rows(db)
    before=db.read_bytes()
    read=await style.read_style(str(db),1)
    assert db.read_bytes()==before and rows(db)==original
    assert read['latest']['version']=='account-style-v0.1' and 'topics' not in read['latest']
    new=await style.analyze_style(str(db),1,transport=provider())
    assert new['version']==style.VERSION and rows(db)[:1]==original


@pytest.mark.asyncio
async def test_500_posts_batches_then_single_summary_and_conservation(db):
    with sqlite3.connect(db) as conn:
        conn.executemany('INSERT INTO douyin_posts VALUES(?,?,?,?,?,?,?)',[(f'bulk{i}','dy','test',f'民生完整标题{i}',NOW-1000-i,NOW-1,'active') for i in range(510)])
    seen=[]
    result=await style.analyze_style(str(db),1,transport=provider(seen=seen))
    assert result['scope']['sampled']==500 and result['scope']['batch_count']==10
    assert len(seen)==11 and result['model_requests']==11
    ids=[id for topic in result['topics'] for id in topic['post_ids']]
    assert len(ids)==len(set(ids))==500
    for request in seen:
        items=json.loads(request['messages'][1]['content'])
        assert request['response_format']['type']=='json_schema'
        total=sum(len(message['content'].encode()) for message in request['messages'])+len(json.dumps(request['response_format'],ensure_ascii=False).encode())+request['max_tokens']+1024
        assert total<=32768
        if 'post_id' in items[0]:
            schema=request['response_format']['json_schema']['schema']
            assert schema['properties']['topic_assignments']['minItems']==len(items)
            assert schema['properties']['topic_assignments']['maxItems']==len(items)


@pytest.mark.asyncio
async def test_failure_mid_batch_keeps_snapshot_and_stops_requests(db):
    await style.analyze_style(str(db),1,transport=provider())
    original=rows(db)
    with sqlite3.connect(db) as conn:
        conn.executemany('INSERT INTO douyin_posts VALUES(?,?,?,?,?,?,?)',[(f'new{i}','dy','test',f'民生标题{i}',NOW-2000-i,NOW-1,'active') for i in range(120)])
    inner=provider(); calls=[]
    async def respond(request):
        calls.append(request)
        if len(calls)==3: return httpx.Response(500)
        return await inner.handle_async_request(request)
    with pytest.raises(style.GroupingError,match='第3/3批'):
        await style.analyze_style(str(db),1,transport=httpx.MockTransport(respond))
    assert len(calls)==3 and rows(db)==original


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['context','length','timeout','mapping'])
async def test_actionable_failure_stage_and_no_writes(db,failure):
    inner=provider()
    async def respond(request):
        if failure=='context': return httpx.Response(400,json={'error':{'message':'maximum context length'}})
        if failure=='length': return httpx.Response(200,json={'choices':[{'finish_reason':'length','message':{'content':'{}'}}]})
        if failure=='timeout': raise httpx.ReadTimeout('fixture',request=request)
        response=await inner.handle_async_request(request)
        items=json.loads(json.loads(request.content)['messages'][1]['content'])
        if 'post_id' not in items[0]:
            body=response.json(); result=json.loads(body['choices'][0]['message']['content'])
            result['topic_mapping'].pop(next(iter(result['topic_mapping'])))
            body['choices'][0]['message']['content']=json.dumps(result)
            return httpx.Response(200,json=body)
        return response
    original=db.read_bytes()
    with pytest.raises(style.GroupingError) as exc:
        await style.analyze_style(str(db),1,transport=httpx.MockTransport(respond))
    assert ('汇总' if failure=='mapping' else '第1/1批') in str(exc.value)
    assert db.read_bytes()==original


@pytest.mark.asyncio
async def test_excessive_batch_plan_rejects_before_model(db):
    with sqlite3.connect(db) as conn:
        conn.execute('DELETE FROM douyin_posts')
        conn.executemany('INSERT INTO douyin_posts VALUES(?,?,?,?,?,?,?)',[(f'long{i}','dy','test','字'*1490,NOW-1000-i,NOW-1,'active') for i in range(500)])
    def forbidden(request): raise AssertionError('Must not request model')
    with pytest.raises(style.GroupingError,match='批安全上限'):
        await style.analyze_style(str(db),1,transport=httpx.MockTransport(forbidden))
    assert not rows(db)


@pytest.mark.asyncio
async def test_incremental_reuses_unchanged_posts_and_recounts(db):
    first = await style.analyze_style(str(db),1,transport=provider())
    original = rows(db)
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO douyin_posts VALUES('increment','dy','test','新增完整标题',?,?, 'active')",(NOW-2,NOW-1))
    before=db.read_bytes()
    status=await style.read_style(str(db),1)
    assert db.read_bytes()==before
    assert status['incremental']['reused_posts']==8
    assert status['incremental']['pending_posts']==1
    assert status['incremental']['planned_model_requests']==2
    assert not status['incremental']['automatic_model_calls']
    seen=[]
    result=await style.analyze_style(str(db),1,transport=provider(seen=seen))
    assert len(seen)==2 and result['model_requests']==2
    assert len(json.loads(seen[0]['messages'][1]['content']))==1
    assert sum(t['count'] for t in result['topics'])==9
    assert rows(db)[:1]==original
    assert result['anchor_at']==first['anchor_at']


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['caption','remove','model','monthly'])
async def test_incremental_invalidation(db,monkeypatch,change):
    await style.analyze_style(str(db),1,transport=provider())
    if change=='caption':
        with sqlite3.connect(db) as conn: conn.execute("UPDATE douyin_posts SET title='已修改文案' WHERE aweme_id='0'")
    if change=='remove':
        with sqlite3.connect(db) as conn: conn.execute("DELETE FROM douyin_posts WHERE aweme_id='0'")
    if change=='model': monkeypatch.setitem(style.config.ai_config,'model','another-fixture')
    if change=='monthly':
        # Keep publication dates eligible; horizon is independently scoped.
        monkeypatch.setattr(style.time,'time',lambda:NOW+style.REANCHOR_SECONDS)
        data=await style.source(str(db),1,365)
        saved=await style.history(str(db),await style.source(str(db),1,30,as_of=NOW))
        plan=style.incremental_plan(data,saved,style.config.ai_config)
    else:
        data=await style.source(str(db),1,30)
        plan=style.incremental_plan(data,await style.history(str(db),data),style.config.ai_config)
    assert not plan['cached'] and len(plan['batches'])==1
    if change=='monthly': assert plan['reanchor']


@pytest.mark.asyncio
async def test_incremental_budget_rejects_without_calls_or_writes(db):
    original=db.read_bytes()
    def forbidden(request): raise AssertionError('Budget must reject before model')
    with pytest.raises(style.GroupingError,match='预算'):
        await style.analyze_style(str(db),1,transport=httpx.MockTransport(forbidden),max_model_requests=1)
    assert db.read_bytes()==original


def test_default_style_request_has_no_call_cap():
    assert style.StyleRequest().max_model_requests is None
    assert style.StyleRequest(max_model_requests=30).max_model_requests==30


@pytest.mark.asyncio
async def test_update_recommendation_and_window_isolation(db,monkeypatch):
    await style.analyze_style(str(db),1,transport=provider())
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO douyin_posts VALUES('later','dy','test','新增标题',?,?, 'active')",(NOW-2,NOW-1))
    assert not (await style.read_style(str(db),1))['incremental']['update_recommended']
    monkeypatch.setattr(style.time,'time',lambda:NOW+86400)
    assert (await style.read_style(str(db),1))['incremental']['update_recommended']
    assert (await style.read_style(str(db),1,365))['latest'] is None


@pytest.mark.asyncio
async def test_thirty_new_posts_recommends_update(db):
    await style.analyze_style(str(db),1,transport=provider())
    with sqlite3.connect(db) as conn:
        conn.executemany('INSERT INTO douyin_posts VALUES(?,?,?,?,?,?,?)',
                         [(f'queue{i}','dy','test',f'新增材料{i}',NOW-10-i,NOW-1,'active') for i in range(30)])
    status=(await style.read_style(str(db),1))['incremental']
    assert status['pending_posts']==30 and status['update_recommended']
    assert len(status['pending_queue'])==30
    assert {p['reason'] for p in status['pending_queue']}=={'new'}


@pytest.mark.asyncio
async def test_input_changed_during_inference_not_saved(db):
    original=rows(db)
    inner=provider()
    async def respond(request):
        inputs=json.loads(json.loads(request.content)['messages'][1]['content'])
        if 'post_id' not in inputs[0]:
            with sqlite3.connect(db) as conn: conn.execute("UPDATE douyin_posts SET title='中途变化' WHERE aweme_id='0'")
        return await inner.handle_async_request(request)
    with pytest.raises(style.GroupingError,match='作品发生变化'):
        await style.analyze_style(str(db),1,transport=httpx.MockTransport(respond))
    assert rows(db)==original


@pytest.mark.parametrize('actual_changes,recommended', [(1,False),(29,False),(30,True)])
def test_update_threshold_excludes_passive_batch_recomputation(actual_changes,recommended,monkeypatch):
    monkeypatch.setattr(style.time,'time',lambda:NOW)
    old={str(i):f'hash{i}' for i in range(100)}
    current={**old, **{f'new{i}':f'newhash{i}' for i in range(actual_changes)}}
    members=[{'post_id':str(i),'snippet_sha256':old[str(i)]} for i in range(49)]
    members.append({'post_id':'new0','snippet_sha256':'newhash0'})
    latest={'generated_at':NOW,'input_sha256':'old-input','source_hashes':old,'version':style.VERSION}
    data={'source_hashes':current,'input_sha256':'new-input'}
    plan={'batches':[members],'cached':[],'reanchor':False}
    status=style.plan_status(data,latest,plan)
    assert status['pending_posts']==50
    assert status['changed_posts']==actual_changes
    assert status['update_recommended']==recommended
    assert status['planned_model_requests']==2


@pytest.mark.asyncio
async def test_caption_changes_threshold_and_removals(db):
    await style.analyze_style(str(db),1,transport=provider())
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE douyin_posts SET title='更正文案' WHERE aweme_id='0'")
        conn.execute("DELETE FROM douyin_posts WHERE aweme_id='1'")
    status=(await style.read_style(str(db),1))['incremental']
    assert status['changed_posts']==1
    assert status['pending_posts']==7
    assert not status['update_recommended']
