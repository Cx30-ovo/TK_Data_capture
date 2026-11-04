"""Small independent metadata store. Never connects writable to collection DB.

GET on an absent store returns defaults without creating files. A user's first
explicit save creates the metadata store. Whole-document version serializes edits
and role/relation validation; account assignments are bound to source identity.
"""
import hashlib
import json
import sqlite3
import time
from pathlib import Path


class MatrixError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(message)


def _identity(account: dict) -> str:
    raw = json.dumps([account["id"], account["platform"], account["sec_user_id"]], ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def read_accounts(source: str) -> list[dict]:
    path = Path(source).resolve()
    if not path.is_file():
        raise MatrixError(503, "账号数据尚未初始化")
    try:
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            now = int(time.time())
            rows = db.execute("""
                SELECT a.id, a.platform, a.sec_user_id, a.display_name, a.enabled,
                  a.snapshots_paused,
                  (SELECT count(*) FROM douyin_posts p WHERE p.platform=a.platform
                    AND p.sec_user_id=a.sec_user_id AND p.status='active'
                    AND p.create_time<? AND p.first_seen_at<=?) AS posts,
                  (SELECT max(create_time) FROM douyin_posts p WHERE p.platform=a.platform
                    AND p.sec_user_id=a.sec_user_id AND p.status='active'
                    AND p.create_time<? AND p.first_seen_at<=?) AS latest_published_at,
                  (SELECT count(*) FROM douyin_posts p WHERE p.platform=a.platform
                    AND p.sec_user_id=a.sec_user_id AND p.status='active'
                    AND p.create_time<? AND p.first_seen_at<=? AND EXISTS
                    (SELECT 1 FROM douyin_post_snapshots s WHERE s.platform=p.platform
                      AND s.aweme_id=p.aweme_id AND s.captured_at<=? AND s.created_at<=?)) AS observed_posts
                FROM douyin_monitored_accounts a ORDER BY a.id
            """, (now,) * 8).fetchall()
            return [{**dict(row), "identity_sha256": _identity(dict(row))} for row in rows]
    except sqlite3.Error as exc:
        raise MatrixError(503, "账号数据暂不可用") from exc


def _load(db: sqlite3.Connection) -> tuple[int, dict]:
    row = db.execute("SELECT version, payload FROM matrix_document WHERE id=1").fetchone()
    if row is None:
        return 0, {}
    payload = json.loads(row[1])
    if not isinstance(payload, dict):
        raise ValueError("Invalid matrix metadata")
    return row[0], payload


def _current(accounts: list[dict], payload: dict) -> dict:
    return {str(a["id"]): payload[str(a["id"])] for a in accounts
            if str(a["id"]) in payload and payload[str(a["id"])].get("identity_sha256") == a["identity_sha256"]}


def _response(accounts: list[dict], version: int, payload: dict) -> dict:
    current = _current(accounts, payload)
    items = []
    for account in accounts:
        entry = current.get(str(account["id"]), {})
        targets = entry.get("competitor_ids", [])
        valid = [target for target in targets if current.get(str(target), {}).get("role") == "competitor"
                 and entry.get("competitor_identities", {}).get(str(target)) == current[str(target)]["identity_sha256"]]
        items.append({k: v for k, v in account.items() if k != "sec_user_id"} | {
            "role": entry.get("role", "unassigned"),
            "group": entry.get("group", "") if entry.get("group_inference") else "",
            "group_inference": entry.get("group_inference"),
            "competitor_ids": valid, "unavailable_competitor_ids": [i for i in targets if i not in valid],
        })
    return {"version": version, "accounts": items, "limits": [
        "作品数量为截至本次读取的全部已采集有效作品，不代表平台全量。",
        "有观测作品仅表示存在截止前采集记录，不代表有效生命周期覆盖或表现优劣。",
        "账号身份和竞品关系由人工维护；业务分组由模型生成并标记为推断，不代表人工核验结论。",
        "业务信息与采集配置独立；修改发现间隔、监控模式请进入该账号的采集配置。",
    ]}


def get_matrix(source: str, metadata: str) -> dict:
    accounts = read_accounts(source)
    path = Path(metadata).resolve()
    if not path.exists():
        return _response(accounts, 0, {})
    try:
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
            version, payload = _load(db)
        return _response(accounts, version, payload)
    except (sqlite3.Error, ValueError, TypeError, KeyError) as exc:
        raise MatrixError(503, "账号矩阵元数据不可用，不会回退覆盖") from exc


def save_assignment(source: str, metadata: str, account_id: int, request: dict, *, generated_group: dict | None = None) -> dict:
    if Path(source).resolve() == Path(metadata).resolve():
        raise MatrixError(503, "元数据存储不能指向采集数据库")
    accounts = read_accounts(source)
    account = next((a for a in accounts if a["id"] == account_id), None)
    if account is None:
        raise MatrixError(404, "账号不存在")
    if request["identity_sha256"] != account["identity_sha256"]:
        raise MatrixError(409, "账号身份已变化，请重新读取")
    path = Path(metadata).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(path, timeout=5) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""CREATE TABLE IF NOT EXISTS matrix_document (
                id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL CHECK(version>=1),
                payload TEXT NOT NULL, updated_at INTEGER NOT NULL)""")
            version, payload = _load(db)
            if version != request["expected_version"]:
                raise MatrixError(409, "账号矩阵已更新，请重新读取后保存；当前输入未被覆盖")
            payload = _current(accounts, payload)
            previous = payload.get(str(account_id), {})
            if generated_group is not None:
                # Only trusted server inference may update grouping; preserve every other field.
                payload[str(account_id)] = {**previous, "identity_sha256": account['identity_sha256'],
                    "group": generated_group['group'], "group_inference": generated_group}
                db.execute("INSERT OR REPLACE INTO matrix_document VALUES (1,?,?,?)",
                           (version + 1, json.dumps(payload, ensure_ascii=False, sort_keys=True), int(time.time())))
                return _response(accounts, version + 1, payload)
            role, targets = request["role"], request["competitor_ids"]
            if targets and role != "owned":
                raise MatrixError(422, "只有自有账号可以配置对比竞品")
            if account_id in targets or any(payload.get(str(i), {}).get("role") != "competitor" for i in targets):
                raise MatrixError(422, "只能关联已标记为竞品的其他账号")
            if role != "competitor" and any(account_id in e.get("competitor_ids", []) for e in payload.values()):
                raise MatrixError(409, "该账号仍被自有账号关联，请先移除对比关系再修改身份")
            # Legacy clients may still send group; never let manual input overwrite model output.
            payload[str(account_id)] = {**previous, "identity_sha256": account["identity_sha256"],
                "role": role, "group": previous.get('group', ''), "competitor_ids": targets,
                "competitor_identities": {str(i): payload[str(i)]["identity_sha256"] for i in targets}}
            db.execute("INSERT OR REPLACE INTO matrix_document VALUES (1,?,?,?)",
                       (version + 1, json.dumps(payload, ensure_ascii=False, sort_keys=True), int(time.time())))
        return _response(accounts, version + 1, payload)
    except (sqlite3.Error, ValueError, TypeError, KeyError) as exc:
        raise MatrixError(503, "账号矩阵元数据不可用，未完成保存") from exc
