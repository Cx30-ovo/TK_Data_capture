import json
from pathlib import Path

import httpx
import pytest

from api.services import account_grouping_service as grouping
from api.services.account_profile_service import build_profile


@pytest.fixture
def sample(monkeypatch):
    profile = build_profile({'id':1,'display_name':'test','platform':'dy','sec_user_id':'test'},
        [{'aweme_id':str(i),'title':f'厦门民生{i}？ #新闻','create_time':100+i,'first_seen_at':100+i} for i in range(5)], [], 5, 5, 0, 86400)
    async def read(*args): return profile
    monkeypatch.setattr(grouping, 'get_account_profile', read)
    monkeypatch.setattr(grouping.config, 'ai_config', dict(enabled=True, base_url='http://model.test/v1', model='test', api_key='secret'))
    grouping._cache.clear()
    return profile


def transport(result, calls):
    def request(req):
        calls.append(json.loads(req.content))
        assert req.url.path == '/v1/chat/completions'
        assert calls[-1]['max_tokens'] == 1200
        return httpx.Response(200, json={'choices':[{'message':{'content':json.dumps(result,ensure_ascii=False)}}]})
    return httpx.MockTransport(request)


@pytest.mark.asyncio
async def test_inference_bound_evidence_cache_no_write(sample, tmp_path):
    calls=[]
    path=tmp_path/'absent.db'
    result={'group':'本地民生','rationale':'标题提及厦门和民生','evidence_post_ids':['0'],'limitations':['仅标题']}
    first=await grouping.infer_group(str(path),1,30,transport=transport(result,calls))
    second=await grouping.infer_group(str(path),1,30,transport=transport(result,calls))
    assert first['evidence'][0]['snippet'] == '厦门民生0？ #新闻'
    assert first['input_sha256']==sample['input_sha256']
    assert second['cached'] and len(calls)==1
    assert not path.exists()
    assert len(json.loads(calls[0]['messages'][1]['content'])['titles'])<=24


@pytest.mark.asyncio
@pytest.mark.parametrize('result', [dict(group='x',rationale='x',evidence_post_ids=['fake']),
    dict(group='',rationale='x',evidence_post_ids=['0']),dict(group='x',rationale='x',evidence_post_ids=[]),
    dict(group='x',rationale='x',evidence_post_ids=['0'],automatic_role='owned')])
async def test_unverifiable_output_rejected(sample,result):
    with pytest.raises(grouping.GroupingError) as err:
        await grouping.infer_group('unused',1,30,transport=transport(result,[]))
    assert err.value.status==502
    assert not grouping._cache


@pytest.mark.asyncio
async def test_disabled_no_call(sample,monkeypatch):
    monkeypatch.setitem(grouping.config.ai_config,'enabled',False)
    with pytest.raises(grouping.GroupingError) as err:
        await grouping.infer_group('unused',1,30)
    assert err.value.status==503


@pytest.mark.asyncio
async def test_insufficient_titles_no_call(sample):
    sample['signals']=[]
    sample['hashtags']=[]
    with pytest.raises(grouping.GroupingError) as err:
        await grouping.infer_group('unused',1,30)
    assert err.value.status==422


@pytest.mark.asyncio
async def test_failure_sanitized_no_retry(sample):
    calls=[]
    def fail(req):
        calls.append(req)
        return httpx.Response(401,text='secret provider credentials')
    with pytest.raises(grouping.GroupingError) as err:
        await grouping.infer_group('unused',1,30,transport=httpx.MockTransport(fail))
    assert 'secret' not in str(err.value)
    assert len(calls)==1


@pytest.mark.asyncio
async def test_reasoning_only_output_not_a_result(sample):
    mock=httpx.MockTransport(lambda req: httpx.Response(200,json={'choices':[{'message':{'content':None,'reasoning_content':'not final'}}]}))
    with pytest.raises(grouping.GroupingError) as err:
        await grouping.infer_group('unused',1,30,transport=mock)
    assert err.value.status==502


@pytest.mark.asyncio
async def test_concurrent_limit(sample):
    async with grouping._lock:
        with pytest.raises(grouping.GroupingError) as err:
            await grouping.infer_group('unused',1,30)
        assert err.value.status==429


@pytest.mark.asyncio
async def test_routes_status_get_never_calls_model(sample,monkeypatch):
    from fastapi import FastAPI
    from api.routers.monitor import router
    app=FastAPI(); app.include_router(router,prefix='/api')
    async def never(*a,**kw): raise AssertionError('GET must not infer')
    monkeypatch.setattr(grouping,'infer_group',never)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
        result=await c.get('/api/monitor/account-matrix/model-status')
        assert result.status_code==200
        assert 'secret' not in result.text and 'model.test' not in result.text
        assert (await c.post('/api/monitor/account-matrix/1/infer-group',json={'days':0})).status_code==422
