"""Reply adjacency and tree reads use isolated sidecar storage, no platform calls."""
import json
import sqlite3
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from api.routers import monitor as routes
from api.services import monitor_comments_service as svc
from database import monitor_comments_repository as repo
from tests.test_monitor_comments import env, raw, response, Fetcher, policy, add_post


def normalized(cid, target=None, root='100', **kw):
    fields={} if target is None else {'reply_to_reply_id':target,'reply_id':root}
    return svc.normalize(raw(cid,**fields,**kw),'123',root)


def save(path, rows):
    repo.finish(path,'123',rows,{'state':'completed','message':'test'})


def baseline(path):
    with sqlite3.connect(path) as db:
        return db.execute('SELECT type,name,sql FROM sqlite_schema ORDER BY name').fetchall()


def test_normalize_distinguishes_thread_root_and_immediate_target():
    root=svc.normalize(raw(),'123','')
    assert root['root_comment_id']=='100' and root['reply_to_comment_id'] is None and root['reply_relation_source']=='root'
    direct=normalized('101','0')
    assert direct['root_comment_id']==direct['parent_comment_id']==direct['reply_to_comment_id']=='100'
    assert direct['reply_relation_source']=='platform'
    nested=normalized('102','101')
    assert nested['parent_comment_id']=='100' and nested['reply_to_comment_id']=='101'
    # Root ID alone or a user ID cannot prove which child was replied to.
    unknown=normalized('103',reply_id='100',reply_to_user_id='private-user')
    assert unknown['reply_to_comment_id'] is None and unknown['reply_relation_source']=='unknown'
    assert 'private-user' not in json.dumps(unknown)


@pytest.mark.parametrize('value',[None,True,False,{},[],'bad','-1','１','1'*65])
def test_malformed_target_is_not_guessed(value):
    item=svc.normalize(raw('101',reply_id='100',reply_to_reply_id=value),'123','100')
    assert item['reply_relation_source']=='invalid' and item['reply_to_comment_id'] is None


@pytest.mark.parametrize('changes',[{'reply_to_reply_id':'101'},{'reply_to_reply_id':'102','reply_id':'999'}])
def test_self_reference_and_mismatched_thread_not_accepted(changes):
    item=svc.normalize(raw('101',**changes),'123','100')
    assert item['reply_relation_source']=='invalid' and item['reply_to_comment_id'] is None


@pytest.mark.asyncio
async def test_collection_persists_deep_edges_without_recursive_platform_requests(env):
    path,_,_=env
    fetcher=Fetcher([response(raw())],[response(raw('103',reply_id='100',reply_to_reply_id='102'),
                                               raw('101',reply_id='100',reply_to_reply_id='0'),
                                               raw('102',reply_id='100',reply_to_reply_id='101'))])
    result,error=await svc.collect_one(fetcher,'account-comments','123',policy(env))
    assert not error and result['replies']==3
    assert fetcher._client.get_sub_comments.await_count==1
    assert fetcher._client.get_sub_comments.await_args.args==('123','100',0)
    assert [x['comment_id'] for x in repo.read_tree(path,'123','100')['items']]==['101']
    assert repo.read_tree(path,'123','100',target='101')['items'][0]['comment_id']=='102'
    assert repo.read_tree(path,'123','100',target='102')['items'][0]['comment_id']=='103'


@pytest.mark.asyncio
async def test_legacy_and_partial_objects_reconcile_without_read_writes_or_schema_changes(env):
    path,_,_=env;before=path.read_bytes()
    policy(env)
    root=svc.normalize(raw(),'123','')
    legacy={k:v for k,v in normalized('104').items() if not k.startswith('reply_relation') and k not in ('root_comment_id','reply_to_comment_id')}
    save(path,[root,normalized('103','102'),normalized('101','0'),legacy])
    side=path.with_name('monitor_comments.db');schema=baseline(side);bytes_before=side.read_bytes()
    tree=repo.read_tree(path,'123','100')
    assert tree['thread_total']==3 and tree['unlinked_count']==2
    orphan=repo.read_tree(path,'123','100',target='unlinked')
    statuses={x['comment_id']:x['reply_relation_status'] for x in orphan['items']}
    assert statuses=={'103':'missing_target','104':'unknown'}
    assert side.read_bytes()==bytes_before and path.read_bytes()==before
    # Later page supplies the missing parent, and a refresh supplies the legacy edge.
    save(path,[normalized('102','101'),normalized('104','103')])
    assert repo.read_tree(path,'123','100')['unlinked_count']==0
    assert repo.read_tree(path,'123','100',target='103')['items'][0]['comment_id']=='104'
    assert baseline(side)==schema and path.read_bytes()==before


@pytest.mark.asyncio
async def test_update_omitting_relation_keeps_known_edge(env):
    path,_,_=env;policy(env)
    save(path,[svc.normalize(raw(),'123',''),normalized('101','0')])
    save(path,[normalized('101',text='更新后的文字')])
    item=repo.read_tree(path,'123','100')['items'][0]
    assert item['content']=='更新后的文字' and item['reply_to_comment_id']=='100'
    assert item['reply_relation_source']=='platform'


@pytest.mark.asyncio
async def test_cycles_cross_thread_and_missing_target_remain_visible(env):
    path,_,_=env;policy(env)
    save(path,[svc.normalize(raw(),'123',''),svc.normalize(raw('200'),'123',''),
               normalized('101','102'),normalized('102','101'),normalized('103','101'),
               normalized('104','999'),normalized('105','201'),normalized('201','0',root='200')])
    direct=repo.read_tree(path,'123','100')
    assert direct['total']==0 and direct['unlinked_count']==4
    orphan=repo.read_tree(path,'123','100',target='unlinked')
    status={x['comment_id']:x['reply_relation_status'] for x in orphan['items']}
    assert status=={'101':'cycle','102':'cycle','104':'missing_target','105':'cross_thread'}
    assert repo.read_tree(path,'123','100',target='101')['items'][0]['comment_id']=='103'
    assert not repo.read_tree(path,'123','100',target='201')['items']


@pytest.mark.asyncio
async def test_tree_pages_direct_children_and_does_not_drop_deep_relationships(env):
    path,_,_=env;policy(env)
    save(path,[svc.normalize(raw(),'123','')]+[normalized(str(i),'0',digg_count=i) for i in range(101,146)])
    first=repo.read_tree(path,'123','100');second=repo.read_tree(path,'123','100',page=2)
    assert first['total']==45 and len(first['items'])==len(second['items'])==20
    assert not set(x['comment_id'] for x in first['items'])&set(x['comment_id'] for x in second['items'])
    assert first['items'][0]['comment_id']=='145'
    save(path,[normalized(str(i),str(i-1)) for i in range(1000,2105)])
    # >1000 edges must not use a recursive Python call stack.
    assert repo.read_tree(path,'123','100',target='2103')['items'][0]['comment_id']=='2104'


@pytest.mark.asyncio
async def test_tree_endpoint_compatible_readonly_validated_and_no_collection(env,monkeypatch):
    path,_,_=env;await add_post();policy(env)
    save(path,[svc.normalize(raw(),'123',''),normalized('101','0'),normalized('102','101')])
    app=FastAPI();app.include_router(routes.router,prefix='/api')
    collect=AsyncMock(side_effect=AssertionError('GET cannot collect'))
    monkeypatch.setattr(routes.monitor_service,'collect_post_comments',collect)
    side=path.with_name('monitor_comments.db');before=(path.read_bytes(),side.read_bytes())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        flat=(await client.get('/api/monitor/posts/123/comments',params={'parent_comment_id':'100'})).json()
        assert flat['total']==2 and 'tree_parent_comment_id' not in flat
        result=await client.get('/api/monitor/posts/123/comments',params={'parent_comment_id':'100','view':'tree'})
        assert result.status_code==200 and result.json()['items'][0]['saved_direct_replies']==1
        child=(await client.get('/api/monitor/posts/123/comments',params={'parent_comment_id':'100','view':'tree','reply_to_comment_id':'101'})).json()
        assert child['items'][0]['comment_id']=='102'
        for params in ({'view':'tree'},{'view':'unknown'},{'reply_to_comment_id':'101'},
                       {'view':'tree','parent_comment_id':'100','reply_to_comment_id':'bad'}):
            assert (await client.get('/api/monitor/posts/123/comments',params=params)).status_code==422
        assert (await client.get('/api/monitor/posts/999/comments',params={'view':'tree','parent_comment_id':'100'})).status_code==404
    assert (path.read_bytes(),side.read_bytes())==before and not collect.called


@pytest.mark.asyncio
async def test_absent_tree_read_never_initializes_sidecar(env):
    path,_,_=env
    assert repo.read_tree(path,'123','100')['items']==[]
    assert not path.with_name('monitor_comments.db').exists()


@pytest.mark.parametrize('fields',[
    {'reply_to_username':'测试对象昵称','reply_to_userid':'private-target-user'},
    {'reply_to_user':{'nickname':'测试对象昵称','uid':'private-target-user','sec_uid':'private-secret'}},
    {'reply_to_username':'测试对象昵称','reply_to_user_id':'private-target-user'},
    {'reply_to_username':'测试对象昵称','reply_to_userid':'private-target-user','reply_to_reply_id':None},
])
def test_explicit_reply_person_is_retained_and_sanitized_without_comment_edge(fields):
    from tools.user_hash import anonymize_user_id,mask_nickname
    item=normalized('101',**fields)
    assert item['reply_to_nickname']==mask_nickname('测试对象昵称')
    assert item['reply_to_creator_hash']==anonymize_user_id('private-target-user')
    assert item['reply_object_source']=='platform'
    assert item['reply_relation_source'] in ('unknown','invalid') and item['reply_to_comment_id'] is None
    assert all(value not in json.dumps(item,ensure_ascii=False) for value in ('private-target-user','private-secret','测试对象昵称'))


@pytest.mark.parametrize('fields',[
    {},{'reply_to_username':None,'reply_to_userid':'0'},
    {'reply_to_username':{},'reply_to_userid':True},
    {'reply_to_user':[]}, {'text':'回复 @某个用户：这不是结构化关系'},
])
def test_no_person_is_guessed_for_missing_invalid_or_text_mentions(fields):
    item=normalized('101',**fields)
    assert not item['reply_to_nickname'] and not item['reply_to_creator_hash']
    assert item['reply_object_source']=='unknown'


@pytest.mark.asyncio
async def test_reply_person_visible_even_if_target_comment_not_collected(env):
    path,_,_=env;policy(env)
    save(path,[svc.normalize(raw(),'123',''),normalized('101','999',reply_to_username='对方昵称',reply_to_userid='target-user'),
               normalized('102',reply_to_username='只有用户对象')])
    flat=repo.read(path,'123',parent='100')['items']
    assert all(item['reply_target_display_name'] for item in flat)
    assert all(item['reply_target_display_source']=='platform' for item in flat)
    missing=repo.read_tree(path,'123','100',target='unlinked')['items']
    assert all(item['reply_target_display_name'] for item in missing)
    # User objects never manufacture a comment ID or a tree edge.
    assert repo.read_tree(path,'123','100')['total']==0


@pytest.mark.asyncio
async def test_exact_target_author_is_resolved_across_pages_but_not_cross_thread(env):
    path,_,_=env;policy(env)
    save(path,[svc.normalize(raw(),'123',''),normalized('101','0',user={'nickname':'目标作者名','uid':'target'}),
               normalized('102','101'),normalized('103','999'),normalized('104'),
               svc.normalize(raw('200'),'123',''),normalized('201','0',root='200'),normalized('105','201')])
    items={item['comment_id']:item for item in repo.read(path,'123',parent='100')['items']}
    from tools.user_hash import mask_nickname
    assert items['102']['reply_target_display_name']==mask_nickname('目标作者名')
    assert items['102']['reply_target_display_source']=='collected_comment'
    for cid in ('101','103','104','105'):assert not items[cid]['reply_target_display_name']
    assert repo.read_tree(path,'123','100',target='101')['items'][0]['reply_target_display_name']==mask_nickname('目标作者名')


@pytest.mark.asyncio
async def test_preserve_explicit_reply_person_on_refresh_without_fields(env):
    path,_,_=env;policy(env)
    save(path,[svc.normalize(raw(),'123',''),normalized('101','999',reply_to_username='原回复对象',reply_to_userid='target')])
    original=repo.read(path,'123',parent='100')['items'][0]['reply_target_display_name']
    save(path,[normalized('101',text='新评论文字')])
    item=repo.read(path,'123',parent='100')['items'][0]
    assert item['reply_to_comment_id']=='999' and item['reply_target_display_name']==original
    save(path,[normalized('101','999',reply_to_userid='target')])
    assert repo.read(path,'123',parent='100')['items'][0]['reply_target_display_name']==original
    # An explicit different comment/user target must not inherit the previous name.
    save(path,[normalized('101','888',reply_to_userid='different-target')])
    assert not repo.read(path,'123',parent='100')['items'][0]['reply_target_display_name']


@pytest.mark.asyncio
async def test_legacy_no_label_and_get_object_resolution_is_readonly(env):
    path,_,_=env;policy(env)
    legacy={key:value for key,value in normalized('101').items()
            if key in ('comment_id','parent_comment_id','content','nickname','creator_hash','create_time','like_count','reply_count','captured_at')}
    save(path,[svc.normalize(raw(),'123',''),legacy,normalized('102','999',reply_to_username='测试对象')])
    side=path.with_name('monitor_comments.db');before=(path.read_bytes(),side.read_bytes(),baseline(side))
    flat={item['comment_id']:item for item in repo.read(path,'123',parent='100')['items']}
    assert not flat['101']['reply_target_display_name'] and flat['102']['reply_target_display_name']
    repo.read_tree(path,'123','100',target='unlinked')
    assert (path.read_bytes(),side.read_bytes(),baseline(side))==before


@pytest.mark.asyncio
async def test_reply_user_id_resolves_same_thread_author_without_inventing_comment_edge(env):
    path,_,_=env;policy(env)
    save(path,[svc.normalize(raw(),'123',''),normalized('101','0',user={'uid':'exact-target-user','nickname':'被回复作者'}),
               normalized('102',reply_to_userid='exact-target-user'),normalized('103',reply_to_userid='not-present')])
    values={item['comment_id']:item for item in repo.read(path,'123',parent='100')['items']}
    assert values['102']['reply_target_display_name'] and values['102']['reply_target_display_source']=='collected_user'
    assert values['102']['reply_to_comment_id'] is None and values['102']['reply_relation_source']=='unknown'
    assert not values['103']['reply_target_display_name']
