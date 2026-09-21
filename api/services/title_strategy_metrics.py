# -*- coding: utf-8 -*-
"""Deterministic preprocessing and statistics for title strategy analysis."""

from __future__ import annotations

import math
import re
import statistics
from collections import Counter
from datetime import datetime
from typing import Any, Iterable, Mapping

import jieba


DATA_LIMIT = "无曝光/播放数据，结论仅反映互动表现"
LENGTH_GROUPS = ("≤20字", "21-25字", "26-30字", "31-40字", ">40字")
STOP_WORDS = {
    "一个", "一些", "一种", "这个", "那个", "这些", "那些", "我们", "你们", "他们",
    "什么", "怎么", "如何", "为什么", "可以", "就是", "还是", "已经", "没有", "不是",
    "进行", "通过", "以及", "因为", "所以", "如果", "但是", "而且", "真的", "今天",
    "视频", "作品", "发布", "来源", "编辑", "记者", "现场", "网友", "表示", "相关",
}

_HASHTAG_RE = re.compile(r"#[^#\s]+")
_MENTION_RE = re.compile(r"@[^@\s]+")
_BRACKET_RE = re.compile(r"（[^）]*）|\([^)]*\)|【[^】]*】|\[[^\]]*\]")
_CHINESE_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_CHINESE_TOKEN_RE = re.compile(r"^[\u3400-\u4dbf\u4e00-\u9fff]{2,}$")


def clean_title(value: Any) -> str:
    """Remove topics, mentions and bracketed metadata, keeping Chinese characters only."""
    text = str(value or "")
    text = _HASHTAG_RE.sub(" ", text)
    text = _MENTION_RE.sub(" ", text)
    text = _BRACKET_RE.sub(" ", text)
    return "".join(_CHINESE_RE.findall(text))


def normalize_title_template(value: Any) -> str:
    text = str(value or "")
    text = _HASHTAG_RE.sub("{话题}", text)
    text = _MENTION_RE.sub("", text)
    text = _BRACKET_RE.sub("", text)
    text = re.sub(r"\d+(?:\.\d+)?", "{数字}", text)
    text = re.sub(r"[^\u3400-\u4dbf\u4e00-\u9fff{}]", "", text)
    return text[:120]


def interaction_score(likes: Any, comments: Any, collects: Any, shares: Any) -> int:
    return (
        int(likes or 0)
        + 2 * int(comments or 0)
        + 2 * int(collects or 0)
        + 3 * int(shares or 0)
    )


def _percentile(values: list[int], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _round(value: float, digits: int = 2) -> float:
    return round(float(value), digits)


def _ratio(numerator: int, denominator: int) -> float:
    return _round(numerator / denominator, 4) if denominator else 0.0


def _length_group(length: int) -> str:
    if length <= 20:
        return "≤20字"
    if length <= 25:
        return "21-25字"
    if length <= 30:
        return "26-30字"
    if length <= 40:
        return "31-40字"
    return ">40字"


def _latest_snapshot(snapshots: Iterable[Any]) -> Any | None:
    rows = list(snapshots)
    if not rows:
        return None
    return max(rows, key=lambda row: (int(getattr(row, "actual_age_seconds", 0) or 0), int(getattr(row, "captured_at", 0) or 0)))


def build_rows(posts: list[Any], snapshots_by_post: Mapping[str, list[Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for post in posts:
        latest = _latest_snapshot(snapshots_by_post.get(post.aweme_id, []))
        likes = int(getattr(latest, "liked_count", 0) or 0)
        comments = int(getattr(latest, "comment_count", 0) or 0)
        collects = int(getattr(latest, "collected_count", 0) or 0)
        shares = int(getattr(latest, "share_count", 0) or 0)
        cleaned = clean_title(post.title or post.desc or "")
        length = len(cleaned)
        rows.append({
            "aweme_id": str(post.aweme_id),
            "title": str(post.title or post.desc or post.aweme_id),
            "title_clean": cleaned,
            "title_len": length,
            "len_group": _length_group(length),
            "create_time": int(post.create_time or 0),
            "publish_time": datetime.fromtimestamp(int(post.create_time or 0)).isoformat(timespec="seconds"),
            "likes": likes,
            "comments": comments,
            "collects": collects,
            "shares": shares,
            "interaction": interaction_score(likes, comments, collects, shares),
            "template": normalize_title_template(post.title or post.desc or ""),
        })
    return rows


def _tokenize(title: str) -> set[str]:
    return {
        token.strip()
        for token in jieba.lcut(title, cut_all=False)
        if _CHINESE_TOKEN_RE.fullmatch(token.strip()) and token.strip() not in STOP_WORDS
    }


def _group_statistics(group: str, rows: list[dict[str, Any]], total: int) -> dict[str, Any]:
    interactions = [int(row["interaction"]) for row in rows]
    return {
        "len_group": group,
        "count": len(rows),
        "ratio": _ratio(len(rows), total),
        "avg_interaction": _round(statistics.fmean(interactions)) if interactions else 0.0,
        "median_interaction": _round(statistics.median(interactions)) if interactions else 0.0,
        "avg_likes": _round(statistics.fmean(row["likes"] for row in rows)) if rows else 0.0,
        "avg_comments": _round(statistics.fmean(row["comments"] for row in rows)) if rows else 0.0,
        "avg_collects": _round(statistics.fmean(row["collects"] for row in rows)) if rows else 0.0,
        "avg_shares": _round(statistics.fmean(row["shares"] for row in rows)) if rows else 0.0,
        "hit_count": sum(1 for row in rows if row["is_hit"]),
        "hit_rate": _ratio(sum(1 for row in rows if row["is_hit"]), len(rows)),
    }


def _long_short_statistics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def summarize(name: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        values = [row["interaction"] for row in items]
        return {
            "group": name,
            "count": len(items),
            "avg_interaction": _round(statistics.fmean(values)) if values else 0.0,
            "median_interaction": _round(statistics.median(values)) if values else 0.0,
            "hit_rate": _ratio(sum(1 for row in items if row["is_hit"]), len(items)),
            "avg_shares": _round(statistics.fmean(row["shares"] for row in items)) if items else 0.0,
        }

    short = summarize("短标题", [row for row in rows if row["title_len"] <= 20])
    long = summarize("长标题", [row for row in rows if row["title_len"] >= 21])
    baseline = short["avg_interaction"]
    lift = _round((long["avg_interaction"] - baseline) / baseline * 100) if baseline else None
    return {"short": short, "long": long, "long_vs_short_lift_percent": lift}


def compute_title_strategy(posts: list[Any], snapshots_by_post: Mapping[str, list[Any]]) -> dict[str, Any]:
    """Return all model-independent title strategy metrics and compact samples."""
    rows = build_rows(posts, snapshots_by_post)
    interactions = [row["interaction"] for row in rows]
    mean = statistics.fmean(interactions) if interactions else 0.0
    deviation = statistics.pstdev(interactions) if len(interactions) > 1 else 0.0
    p90 = _percentile(interactions, 0.90)
    threshold = max(p90, mean + 2 * deviation)
    for row in rows:
        row["is_hit"] = row["interaction"] >= threshold

    total = len(rows)
    hit_count = sum(1 for row in rows if row["is_hit"])
    overall_hit_rate = hit_count / total if total else 0.0

    token_rows: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        for token in _tokenize(row["title_clean"]):
            token_rows.setdefault(token, []).append(row)
    top_keywords = []
    for keyword, items in token_rows.items():
        if len(items) < 3:
            continue
        keyword_hit_rate = sum(1 for row in items if row["is_hit"]) / len(items)
        top_keywords.append({
            "keyword": keyword,
            "count": len(items),
            "ratio": _ratio(len(items), total),
            "avg_interaction": _round(statistics.fmean(row["interaction"] for row in items)),
            "hit_rate": _round(keyword_hit_rate, 4),
            "lift": _round(keyword_hit_rate / overall_hit_rate, 2) if overall_hit_rate else 0.0,
        })
    top_keywords.sort(key=lambda row: (row["count"], row["avg_interaction"]), reverse=True)

    length_stats = [
        _group_statistics(group, [row for row in rows if row["len_group"] == group], total)
        for group in LENGTH_GROUPS
    ]
    hit_samples = sorted((row for row in rows if row["is_hit"]), key=lambda row: row["interaction"], reverse=True)[:20]
    normal_samples = sorted((row for row in rows if not row["is_hit"]), key=lambda row: row["interaction"], reverse=True)[:20]

    template_counts = Counter(row["template"] for row in rows if row["template"])
    templates = [
        {"template": template, "count": count, "ratio": _ratio(count, total)}
        for template, count in template_counts.most_common(10)
        if count >= 2
    ]

    sample_keys = ("aweme_id", "title", "title_clean", "publish_time", "title_len", "interaction", "likes", "comments", "collects", "shares")
    compact = lambda row: {key: row[key] for key in sample_keys}
    return {
        "overview": {
            "total_works": total,
            "hit_count": hit_count,
            "overall_hit_rate": _round(overall_hit_rate, 4),
            "hit_threshold": _round(threshold),
            "interaction_mean": _round(mean),
            "interaction_p90": _round(p90),
            "interaction_stddev": _round(deviation),
        },
        "top_keywords": top_keywords[:10],
        "title_length_groups": length_stats,
        "long_vs_short": _long_short_statistics(rows),
        "hit_samples": [compact(row) for row in hit_samples],
        "normal_samples": [compact(row) for row in normal_samples],
        "title_templates": templates,
        "source_post_ids": [row["aweme_id"] for row in rows],
        "data_limit": DATA_LIMIT,
    }


__all__ = [
    "DATA_LIMIT",
    "LENGTH_GROUPS",
    "build_rows",
    "clean_title",
    "compute_title_strategy",
    "interaction_score",
    "normalize_title_template",
]
