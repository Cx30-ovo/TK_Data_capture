"""Read-only, reproducible title statistics. No model or collector dependencies."""

import hashlib
import json
import re
import statistics
import time
from collections import Counter
from pathlib import Path

import aiosqlite
from api.services.title_sentence import TITLE_SENTENCE_RULE, TITLE_SENTENCE_VERSION, TITLE_LENGTH_BINS, extract_title_sentence


PROFILE_VERSION = "account-title-profile-v0.5"
MAX_SAMPLE = 5000
STAGES = {"1h": (3600, 1800), "6h": (21600, 7200),
          "24h": (86400, 21600), "72h": (259200, 43200), "7d": (604800, 86400)}


class ProfileUnavailable(Exception):
    pass


class AccountNotFound(Exception):
    pass


async def get_account_profile(db_path: str, account_id: int, days: int = 30, *, as_of: int | None = None) -> dict:
    if account_id < 1 or not 1 <= days <= 365:
        raise ValueError("Invalid profile range")
    cutoff = int(time.time()) if as_of is None else as_of
    start = cutoff - days * 86400
    path = Path(db_path).resolve()
    if not path.is_file():
        raise ProfileUnavailable("账号数据尚未初始化")
    try:
        async with aiosqlite.connect(path.as_uri() + "?mode=ro", uri=True) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA query_only=ON")
            await db.execute("BEGIN")
            async with db.execute("SELECT id, platform, sec_user_id, display_name FROM douyin_monitored_accounts WHERE id=?", (account_id,)) as cursor:
                account = await cursor.fetchone()
            if account is None:
                raise AccountNotFound()
            params = (account["platform"], account["sec_user_id"], start, cutoff, cutoff)
            where = "platform=? AND sec_user_id=? AND create_time>=? AND create_time<? AND first_seen_at<=?"
            async with db.execute(f"SELECT count(*) AS total, sum(CASE WHEN status='active' THEN 1 ELSE 0 END) AS active FROM douyin_posts WHERE {where}", params) as cursor:
                counts = await cursor.fetchone()
            async with db.execute(f"SELECT aweme_id, title, create_time, first_seen_at FROM douyin_posts WHERE {where} AND status='active' ORDER BY create_time DESC, aweme_id ASC LIMIT ?", (*params, MAX_SAMPLE)) as cursor:
                posts = [dict(row) for row in await cursor.fetchall()]
            observations = []
            # Chunk IDs to respect older SQLite variable limits; one read transaction.
            for offset in range(0, len(posts), 400):
                ids = [post["aweme_id"] for post in posts[offset:offset + 400]]
                placeholders = ",".join("?" for _ in ids)
                async with db.execute(f"SELECT aweme_id, stage, captured_at, actual_age_seconds FROM douyin_post_snapshots WHERE platform=? AND aweme_id IN ({placeholders}) AND captured_at<=? AND created_at<=? ORDER BY aweme_id, stage, captured_at", (account["platform"], *ids, cutoff, cutoff)) as cursor:
                    observations.extend(dict(row) for row in await cursor.fetchall())
            await db.rollback()
    except aiosqlite.Error as exc:
        raise ProfileUnavailable("账号数据当前不可用，请检查本地数据库结构") from exc
    return build_profile(dict(account), posts, observations, counts["total"], counts["active"] or 0, start, cutoff)


def title_word_count(title: str) -> int:
    return extract_title_sentence(title)["word_count"] or 0


def build_profile(account: dict, posts: list[dict], observations: list[dict], total: int, active: int, start: int, cutoff: int) -> dict:
    titled = [post for post in posts if (post["title"] or "").strip()]
    extracted = [(post, extract_title_sentence(post["title"])) for post in posts]
    usable = [(post, result) for post, result in extracted if result["word_count"] is not None]
    lengths = [result["word_count"] for post, result in usable]
    patterns = {"question": ("问句标点", r"[?？]"), "exclamation": ("感叹标点", r"[!！]"),
                "numbers": ("包含数字", r"\d"), "quote": ("包含引号", r"[“”‘’\"「」『』]")}
    signals = []
    for key, (label, pattern) in patterns.items():
        hits = [post for post in titled if re.search(pattern, post["title"])]
        signals.append({"key": key, "label": label, "count": len(hits),
                        "evidence": [reference(post) for post in hits[:3]]})
    tags: Counter = Counter()
    tag_posts: dict[str, list] = {}
    for post in titled:
        for tag in sorted(set(re.findall(r"#([^\s#，。！？、；：]+)", post["title"]))):
            tags[tag] += 1
            tag_posts.setdefault(tag, []).append(post)
    bins = TITLE_LENGTH_BINS
    post_map = {post["aweme_id"]: post for post in posts}
    observed = set()
    stages = {key: set() for key in STAGES}
    invalid = 0
    for row in observations:
        post = post_map[row["aweme_id"]]
        age = row["captured_at"] - post["create_time"]
        if age < 0 or row["actual_age_seconds"] != age:
            invalid += 1
            continue
        observed.add(row["aweme_id"])
        if row["stage"] in STAGES:
            target, tolerance = STAGES[row["stage"]]
            if abs(age - target) <= tolerance:
                stages[row["stage"]].add(row["aweme_id"])
    digest_input = {"version": PROFILE_VERSION, "account": account, "range": [start, cutoff],
                    "total": total, "active": active, "posts": posts, "observations": observations}
    fingerprint = hashlib.sha256(json.dumps(digest_input, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "version": PROFILE_VERSION, "input_sha256": fingerprint,
        "account": {"id": account["id"], "display_name": account["display_name"] or account["sec_user_id"], "platform": account["platform"]},
        "window": {"start": start, "end": cutoff, "days": (cutoff - start) // 86400},
        "counts": {"eligible": active, "excluded_status": total - active, "sampled": len(posts),
                   "with_title": len(titled), "missing_title": len(posts) - len(titled), "truncated": active > len(posts)},
        "publication": {"earliest": min((p["create_time"] for p in posts), default=None),
                        "latest": max((p["create_time"] for p in posts), default=None),
                        "posts_per_day": round(active / ((cutoff - start) / 86400), 2)},
        "title_length": {"mean": round(statistics.mean(lengths), 1) if lengths else None,
                         "median": statistics.median(lengths) if lengths else None,
                         "sample_count": len(lengths), "excluded_count": len(posts) - len(lengths),
                         "extraction_version": TITLE_SENTENCE_VERSION, "rule": TITLE_SENTENCE_RULE,
                         "evidence": [{**reference(post), "extracted_title": result["text"],
                                       "word_count": result["word_count"], "method": result["method"]}
                                      for post, result in usable[:10]],
                         "histogram": [{"label": label, "count": sum(low <= n <= high for n in lengths)} for label, low, high in bins]},
        "signals": signals,
        "hashtags": [{"tag": tag, "post_count": count, "evidence": [reference(post) for post in tag_posts[tag][:3]]}
                     for tag, count in sorted(tags.items(), key=lambda item: (-item[1], item[0]))[:12]],
        "coverage": {"observed_posts": len(observed), "without_observation": len(posts) - len(observed),
                     "invalid_observations": invalid, "lifecycle": [{"stage": key, "posts": len(ids)} for key, ids in stages.items()]},
        "limits": ["仅分析已采集发布文案及其规则提取标题句，不代表账号全部作品或正文立场。", "标签为发布文案中的原始话题标签，不是语义主题分类。",
                   TITLE_SENTENCE_RULE, "无法提取标题句的作品不纳入标题长度统计；标题句可超过60字，不做定长截断。", "仅展示观测覆盖，不按累计互动判定高表现或预测热度。",
                   "按发布时间筛选，首次采集和观测入库均不得晚于本次统计截止时间；不是历史数据回放。",
                   "当前为统计档案，未调用模型，未训练账号风格模型。"],
    }


def reference(post: dict) -> dict:
    return {"post_id": post["aweme_id"], "field": "title", "snippet": post["title"], "published_at": post["create_time"]}
