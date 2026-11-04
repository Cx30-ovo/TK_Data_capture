"""Independent metadata writes; collection database must remain byte-identical."""
import sqlite3

import httpx
import pytest
from fastapi import FastAPI

from api.routers import monitor
from database import account_matrix_repository as matrix
from api.schemas.account_matrix import MatrixAssignment


@pytest.fixture
def stores(tmp_path):
    source, metadata = tmp_path / "source.db", tmp_path / "metadata.db"
    with sqlite3.connect(source) as db:
        db.executescript("""
        CREATE TABLE douyin_monitored_accounts (id INTEGER PRIMARY KEY, platform TEXT,
          sec_user_id TEXT, display_name TEXT, enabled INTEGER, snapshots_paused INTEGER);
        INSERT INTO douyin_monitored_accounts VALUES
          (1,'dy','own','测试自有',1,0),(2,'dy','rival','测试竞品',0,1);
        CREATE TABLE douyin_posts (platform TEXT, sec_user_id TEXT, aweme_id TEXT,
          status TEXT, create_time INTEGER, first_seen_at INTEGER);
        INSERT INTO douyin_posts VALUES ('dy','own','p1','active',1,1),
          ('dy','own','p2','deleted',2,2),('dy','rival','p3','active',1,1),
          ('dy','own','future','active',9999999999,1);
        CREATE TABLE douyin_post_snapshots (platform TEXT, aweme_id TEXT,
          captured_at INTEGER, created_at INTEGER);
        INSERT INTO douyin_post_snapshots VALUES ('dy','p1',2,2),('dy','p1',3,3),
          ('dy','p3',9999999999,9999999999);
        """)
    baseline = source.read_bytes()
    yield str(source), str(metadata)
    assert source.read_bytes() == baseline


def save(stores, id, version, role, targets=None, group="新闻"):
    accounts = matrix.read_accounts(stores[0])
    account = next(a for a in accounts if a['id'] == id)
    request = MatrixAssignment(expected_version=version, identity_sha256=account['identity_sha256'],
                               role=role, group=group, competitor_ids=targets or [])
    return matrix.save_assignment(*stores, id, request.model_dump())


def test_get_no_create_and_coverage(stores):
    from pathlib import Path
    result = matrix.get_matrix(*stores)
    assert result['version'] == 0
    assert not Path(stores[1]).exists()
    assert [a['role'] for a in result['accounts']] == ['unassigned', 'unassigned']
    assert result['accounts'][0]['posts'] == 1
    assert result['accounts'][0]['observed_posts'] == 1
    assert result['accounts'][1]['observed_posts'] == 0
    assert 'sec_user_id' not in result['accounts'][0]


def test_roles_groups_relations_and_restart(stores):
    save(stores, 2, 0, 'competitor')
    result = save(stores, 1, 1, 'owned', [2], ' 本地新闻 ')
    assert result['version'] == 2
    assert result['accounts'][0]['group'] == ''  # Legacy manual group ignored.
    assert matrix.get_matrix(*stores)['accounts'][0]['competitor_ids'] == [2]
    with sqlite3.connect(stores[1]) as db:
        assert db.execute("SELECT name FROM sqlite_schema WHERE type='table'").fetchall() == [('matrix_document',)]


def test_model_group_saved_and_manual_edits_preserve_it(stores):
    first=save(stores,1,0,'owned')
    request={'expected_version':first['version'],'identity_sha256':first['accounts'][0]['identity_sha256']}
    inference={'group':'模型民生','rationale':'标题依据','generated_at':123,'evidence':[]}
    result=matrix.save_assignment(*stores,1,request,generated_group=inference)
    assert result['accounts'][0]['group']=='模型民生'
    assert result['accounts'][0]['role']=='owned'
    result=save(stores,1,2,'owned',group='manual overwrite')
    assert result['accounts'][0]['group']=='模型民生'
    assert matrix.get_matrix(*stores)['accounts'][0]['group_inference']==inference
    with pytest.raises(matrix.MatrixError):
        matrix.save_assignment(*stores,1,request,generated_group={'group':'stale'})
    assert matrix.get_matrix(*stores)['accounts'][0]['group']=='模型民生'


def test_conflict_does_not_overwrite(stores):
    save(stores, 2, 0, 'competitor')
    from pathlib import Path
    before = Path(stores[1]).read_bytes()
    with pytest.raises(matrix.MatrixError) as err:
        save(stores, 1, 0, 'owned')
    assert err.value.status == 409
    assert Path(stores[1]).read_bytes() == before


@pytest.mark.parametrize('role,targets', [('competitor',[2]),('owned',[1]),('owned',[2]),('owned',[999])])
def test_invalid_relations(stores, role, targets):
    with pytest.raises(matrix.MatrixError) as err:
        save(stores, 1, 0, role, targets)
    assert err.value.status == 422


def test_referenced_role_change_requires_explicit_unlink(stores):
    save(stores, 2, 0, 'competitor')
    save(stores, 1, 1, 'owned', [2])
    with pytest.raises(matrix.MatrixError) as err:
        save(stores, 2, 2, 'owned')
    assert err.value.status == 409
    save(stores, 1, 2, 'owned')
    assert save(stores, 2, 3, 'owned')['version'] == 4


def test_identity_reuse_not_inherited(stores):
    from pathlib import Path
    original = Path(stores[0]).read_bytes()
    save(stores, 2, 0, 'competitor')
    save(stores, 1, 1, 'owned', [2])
    # Deliberate source mutation only inside this test fixture; restore it before final guard.
    with sqlite3.connect(stores[0]) as db:
        db.execute("UPDATE douyin_monitored_accounts SET sec_user_id='different' WHERE id=2")
    result = matrix.get_matrix(*stores)
    assert result['accounts'][1]['role'] == 'unassigned'
    assert result['accounts'][0]['competitor_ids'] == []
    assert result['accounts'][0]['unavailable_competitor_ids'] == [2]
    Path(stores[0]).write_bytes(original)


@pytest.mark.parametrize('kwargs', [dict(group='😀'*51), dict(competitor_ids=[2,2]),
    dict(competitor_ids=[0]),dict(role='admin'),dict(unexpected=True)])
def test_validation(stores, kwargs):
    base = dict(expected_version=0, identity_sha256='0'*64, role='owned')
    base.update(kwargs)
    with pytest.raises(ValueError):
        MatrixAssignment(**base)
    assert MatrixAssignment(expected_version=0, identity_sha256='0'*64, role='owned', group='😀'*50)


def test_corrupt_metadata_no_fallback(stores):
    from pathlib import Path
    Path(stores[1]).write_bytes(b'not sqlite')
    before = Path(stores[1]).read_bytes()
    with pytest.raises(matrix.MatrixError) as err:
        matrix.get_matrix(*stores)
    assert err.value.status == 503
    with pytest.raises(matrix.MatrixError):
        save(stores, 1, 0, 'owned')
    assert Path(stores[1]).read_bytes() == before


@pytest.mark.asyncio
async def test_routes_and_source_unavailable(stores, monkeypatch):
    monkeypatch.setitem(monitor.sqlite_db_config, 'db_path', stores[0])
    monkeypatch.setattr(monitor, 'matrix_metadata_path', lambda: stores[1])
    app = FastAPI()
    app.include_router(monitor.router, prefix='/api')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        result = (await client.get('/api/monitor/account-matrix')).json()
        request = dict(expected_version=0, identity_sha256=result['accounts'][0]['identity_sha256'],
                       role='owned', group='', competitor_ids=[])
        assert (await client.put('/api/monitor/account-matrix/1', json=request)).status_code == 200
        assert (await client.put('/api/monitor/account-matrix/1', json=request)).status_code == 409
        request['expected_version'] = 1
        assert (await client.put('/api/monitor/account-matrix/999', json=request)).status_code == 404
        request['identity_sha256'] = '0'*64
        assert (await client.put('/api/monitor/account-matrix/1', json=request)).status_code == 409
        monkeypatch.setitem(monitor.sqlite_db_config, 'db_path', stores[0]+'missing')
        assert (await client.get('/api/monitor/account-matrix')).status_code == 503
