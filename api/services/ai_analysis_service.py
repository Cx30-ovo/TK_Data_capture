# -*- coding: utf-8 -*-
"""Orchestration for cached topic and lifecycle analysis."""

import asyncio
import hashlib
import json
import re
import statistics
import time
from datetime import datetime
from typing import Any, Mapping, Optional

import config
from database.ai_analysis_repository import ai_analysis_repository
from database.monitor_repository import monitor_repository

from .ai_model_service import AIServiceError, ai_model_service


TOPIC_PROMPT_VERSION = "topic-v1"
LIFECYCLE_PROMPT_VERSION = "lifecycle-v2"
TIME_RANGE_SECONDS = {
    "24h": 24 * 60 * 60,
    "7d": 7 * 24 * 60 * 60,
    "30d": 30 * 24 * 60 * 60,
}
LIFECYCLE_STAGES = ("1h", "6h", "24h", "72h")


TOPIC_SYSTEM_PROMPT = """
你是抖音内容研究分析师。你只能使用输入中已有的作品 ID、标题、正文、标签和互动数据。

任务要求：
1. 将作品归纳为 3 到 6 个主题聚类，描述保持简洁。
2. 每个聚类必须返回主题名称、简短说明、作品 ID 列表、关键词和 0 到 1 之间的置信度。
3. 不允许编造作品 ID、互动数字或发布时间。
4. 不允许把相关性表述为确定因果。
5. 信息不足时写入 data_limits，不要猜测。
6. summary 必须比较表现最好和较低的主题。
7. recommendations 只输出行动建议，不要直接罗列互动数字。
8. representative_insight 用一句话总结代表作的内容特征，不要列作品标题或数字。

输出 JSON 结构：
{
  "summary": "整体主题与表现摘要",
  "clusters": [
    {
      "name": "主题名称",
      "description": "主题内容说明",
      "post_ids": ["作品ID"],
      "keywords": ["关键词"],
      "representative_insight": "代表作特征总结",
      "confidence": 0.9
    }
  ],
  "tag_groups": [
    {"name": "标签组名称", "tags": ["标签"], "summary": "标签共同表达的内容"}
  ],
  "recommendations": ["基于输入数据的建议"],
  "data_limits": ["数据限制"]
}
""".strip()


LIFECYCLE_SYSTEM_PROMPT = """
你是抖音内容传播节奏分析师。你只能使用输入中已有的作品、快照阶段和互动数据。

任务要求：
1. 解释作品在 1h、6h、24h、72h 阶段的传播变化。
2. 区分早爆、快速衰退、长尾和持续型节奏。
3. 每条 post_insights 都必须填写 aweme_id 字段，但不要在 pattern、evidence 或其他文字中直接写作品 ID；需要指向作品时使用作品标题，post_insights 最多返回 5 条。
4. 不允许编造数字、发布时间、缺失快照或因果关系。
5. 数据不完整时写入 caveats。
6. overall_summary 不得为空，必须用业务语言描述主要增长阶段。
7. pattern 使用一句话，控制在 30 个汉字以内。

输出 JSON 结构：
{
  "overall_summary": "整体生命周期摘要",
  "post_insights": [
    {
      "aweme_id": "作品ID",
      "pattern": "传播节奏判断",
      "evidence": ["包含具体阶段或数据增量的依据"],
      "possible_factors": ["可能相关的内容因素"],
      "confidence": 0.8
    }
  ],
  "content_patterns": ["跨作品内容规律"],
  "anomaly_notes": ["异常增长说明"],
  "recommendations": ["运营建议"],
  "caveats": ["数据缺失或不确定性说明"]
}
""".strip()


def _safe_text(value: Any, limit: int = 500) -> str:
    return str(value or "").strip()[:limit]


def _string_list(value: Any, limit: int = 20) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        text = _safe_text(item, 300)
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


class AIAnalysisService:
    """Build deterministic analysis input, call the model and cache the result."""

    def __init__(
        self,
        model_service=None,
        analysis_repository=None,
        monitor_repository_instance=None,
    ) -> None:
        self._model_service = model_service or ai_model_service
        self._repository = analysis_repository or ai_analysis_repository
        self._monitor_repository = monitor_repository_instance or monitor_repository
        self._lock = asyncio.Lock()

    async def analyze_topics(
        self,
        *,
        sec_user_id: str,
        scope: Optional[Mapping[str, Any]] = None,
        force: bool = False,
    ) -> dict[str, Any]:
        normalized_scope = self._normalize_scope(scope, default_limit=100)
        normalized_scope["post_limit"] = min(int(normalized_scope["post_limit"]), 20)
        posts, snapshots_by_post = await self._load_source(sec_user_id, normalized_scope)
        if len(posts) < 3:
            return self._insufficient_data(
                analysis_type="topic",
                scope=normalized_scope,
                message="主题分析至少需要 3 篇作品数据。",
            )

        topic_posts = self._build_topic_posts(posts, snapshots_by_post)
        return await self._run_cached_analysis(
            sec_user_id=sec_user_id,
            analysis_type="topic",
            scope=normalized_scope,
            source_data={"posts": topic_posts},
            prompt_version=TOPIC_PROMPT_VERSION,
            system_prompt=TOPIC_SYSTEM_PROMPT,
            max_tokens=int(config.AI_MAX_TOKENS),
            force=force,
            normalizer=lambda result: self._normalize_topic_result(result, topic_posts),
        )

    async def analyze_lifecycle(
        self,
        *,
        sec_user_id: str,
        scope: Optional[Mapping[str, Any]] = None,
        force: bool = False,
    ) -> dict[str, Any]:
        normalized_scope = self._normalize_scope(scope, default_limit=12)
        normalized_scope["post_limit"] = min(int(normalized_scope["post_limit"]), 12)
        load_scope = {**normalized_scope, "post_limit": 50}
        posts, snapshots_by_post = await self._load_source(sec_user_id, load_scope)
        posts = [
            post for post in posts
            if any(snapshot.stage in LIFECYCLE_STAGES for snapshot in snapshots_by_post.get(post.aweme_id, []))
        ]
        posts.sort(
            key=lambda post: self._interaction((snapshots_by_post.get(post.aweme_id) or [None])[-1]),
            reverse=True,
        )
        posts = posts[:int(normalized_scope["post_limit"])]
        if len(posts) < 2:
            return self._insufficient_data(
                analysis_type="lifecycle",
                scope=normalized_scope,
                message="生命周期分析至少需要 2 篇作品数据。",
            )

        lifecycle_posts = self._build_lifecycle_posts(posts, snapshots_by_post)
        if sum(1 for post in lifecycle_posts if post.get("snapshots")) < 2:
            return self._insufficient_data(
                analysis_type="lifecycle",
                scope=normalized_scope,
                message="生命周期分析至少需要 2 篇带快照数据的作品。",
            )
        return await self._run_cached_analysis(
            sec_user_id=sec_user_id,
            analysis_type="lifecycle",
            scope=normalized_scope,
            source_data={"posts": lifecycle_posts},
            prompt_version=LIFECYCLE_PROMPT_VERSION,
            system_prompt=LIFECYCLE_SYSTEM_PROMPT,
            max_tokens=int(config.AI_MAX_TOKENS),
            force=force,
            normalizer=lambda result: self._normalize_lifecycle_result(result, lifecycle_posts),
        )

    @staticmethod
    def _normalize_scope(scope: Optional[Mapping[str, Any]], default_limit: int) -> dict[str, Any]:
        values = dict(scope or {})
        time_range = str(values.get("time_range") or "30d")
        if time_range not in {*TIME_RANGE_SECONDS.keys(), "all"}:
            time_range = "30d"
        try:
            post_limit = int(values.get("post_limit") or default_limit)
        except (TypeError, ValueError):
            post_limit = default_limit
        return {
            "time_range": time_range,
            "post_limit": max(1, min(post_limit, 200)),
        }

    async def _load_source(self, sec_user_id: str, scope: Mapping[str, Any]):
        posts = await self._monitor_repository.list_posts(
            sec_user_id=sec_user_id,
            limit=int(scope["post_limit"]),
        )
        time_range = str(scope["time_range"])
        if time_range != "all":
            cutoff = int(time.time()) - TIME_RANGE_SECONDS[time_range]
            posts = [post for post in posts if int(post.first_seen_at or 0) >= cutoff]

        snapshots = await self._monitor_repository.list_snapshots(
            sec_user_id=sec_user_id,
            limit=100000,
        )
        selected_ids = {post.aweme_id for post in posts}
        snapshots_by_post: dict[str, list] = {}
        for snapshot in snapshots:
            if snapshot.aweme_id in selected_ids:
                snapshots_by_post.setdefault(snapshot.aweme_id, []).append(snapshot)
        for items in snapshots_by_post.values():
            items.sort(key=lambda item: item.actual_age_seconds)
        return posts, snapshots_by_post

    @staticmethod
    def _truncate(value: Any, limit: int) -> str:
        text = str(value or "").strip()
        return text if len(text) <= limit else f"{text[:limit - 1]}…"

    @staticmethod
    def _tags(post) -> list[str]:
        tags = re.findall(r"#([^#\s]+)", f"{post.title or ''} {post.desc or ''}")
        return list(dict.fromkeys(tag.strip("，。！？,.!?：:；;、") for tag in tags if tag.strip()))[:12]

    @staticmethod
    def _snapshot_payload(snapshot) -> dict[str, Any]:
        return {
            "stage": snapshot.stage,
            "actual_age_hours": round(snapshot.actual_age_seconds / 3600, 3),
            "captured_at": snapshot.captured_at,
            "liked_count": int(snapshot.liked_count or 0),
            "collected_count": int(snapshot.collected_count or 0),
            "comment_count": int(snapshot.comment_count or 0),
            "share_count": int(snapshot.share_count or 0),
            "interaction_total": sum(int(value or 0) for value in (
                snapshot.liked_count,
                snapshot.collected_count,
                snapshot.comment_count,
                snapshot.share_count,
            )),
        }

    def _post_base_payload(self, post, snapshots: list) -> dict[str, Any]:
        latest = snapshots[-1] if snapshots else None
        return {
            "aweme_id": post.aweme_id,
            "title": self._truncate(post.title or post.aweme_id, 180),
            "desc": self._truncate(post.desc, 320),
            "create_time": post.create_time,
            "create_time_text": datetime.fromtimestamp(int(post.create_time)).isoformat(timespec="seconds"),
            "first_seen_delay_hours": round(max(0, int(post.first_seen_at or post.create_time) - int(post.create_time)) / 3600, 2),
            "tags": self._tags(post),
            "latest": self._snapshot_payload(latest) if latest else None,
        }

    def _build_topic_posts(self, posts: list, snapshots_by_post: dict[str, list]) -> list[dict[str, Any]]:
        return [self._post_base_payload(post, snapshots_by_post.get(post.aweme_id, [])) for post in posts]

    def _build_lifecycle_posts(self, posts: list, snapshots_by_post: dict[str, list]) -> list[dict[str, Any]]:
        result = []
        for post in posts:
            snapshots = snapshots_by_post.get(post.aweme_id, [])
            item = self._post_base_payload(post, snapshots)
            item["desc"] = self._truncate(post.desc, 160)
            item["lifecycle_type"] = self._lifecycle_type(snapshots)
            item["lifecycle_metrics"] = self._lifecycle_metrics(snapshots)
            item["snapshots"] = [
                self._snapshot_payload(snapshot)
                for snapshot in snapshots
                if snapshot.stage in LIFECYCLE_STAGES
            ]
            result.append(item)
        return result

    @staticmethod
    def _by_stage(snapshots: list) -> dict[str, Any]:
        return {snapshot.stage: snapshot for snapshot in snapshots}

    @staticmethod
    def _interaction(snapshot) -> int:
        if snapshot is None:
            return 0
        return sum(int(value or 0) for value in (
            snapshot.liked_count,
            snapshot.collected_count,
            snapshot.comment_count,
            snapshot.share_count,
        ))

    def _lifecycle_metrics(self, snapshots: list) -> dict[str, Optional[float]]:
        by_stage = self._by_stage(snapshots)
        first = self._interaction(by_stage.get("1h")) if by_stage.get("1h") else None
        six_hours = self._interaction(by_stage.get("6h")) if by_stage.get("6h") else None
        day = self._interaction(by_stage.get("24h")) if by_stage.get("24h") else None
        three_days = self._interaction(by_stage.get("72h")) if by_stage.get("72h") else None
        return {
            "burst": round(first / day, 4) if first is not None and day else None,
            "tail": round(day / six_hours, 4) if day is not None and six_hours else None,
            "persistence": round(three_days / day, 4) if three_days is not None and day else None,
            "increment_1h": first,
            "increment_6h": six_hours - first if first is not None and six_hours is not None else None,
            "increment_24h": day - six_hours if six_hours is not None and day is not None else None,
            "increment_72h": three_days - day if day is not None and three_days is not None else None,
        }

    def _lifecycle_type(self, snapshots: list) -> str:
        metrics = self._lifecycle_metrics(snapshots)
        increments = [
            metrics["increment_1h"],
            metrics["increment_6h"],
            metrics["increment_24h"],
            metrics["increment_72h"],
        ]
        if metrics["persistence"] is not None and metrics["persistence"] >= 1.15 and (metrics["increment_72h"] or 0) > 0:
            return "sustained"
        available = [(index, value or float("-inf")) for index, value in enumerate(increments) if value is not None]
        if not available:
            return "unknown"
        dominant_index = max(available, key=lambda item: item[1])[0]
        return {
            0: "earlyBurst",
            1: "quickDecline",
            2: "longTail",
            3: "sustained",
        }.get(dominant_index, "unknown")

    @staticmethod
    def _hash_input(source_data: Mapping[str, Any]) -> str:
        serialized = json.dumps(source_data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _scope_key(analysis_type: str, scope: Mapping[str, Any]) -> str:
        return f"{analysis_type}:{scope['time_range']}:limit={scope['post_limit']}"

    async def _run_cached_analysis(
        self,
        *,
        sec_user_id: str,
        analysis_type: str,
        scope: Mapping[str, Any],
        source_data: Mapping[str, Any],
        prompt_version: str,
        system_prompt: str,
        max_tokens: int,
        force: bool,
        normalizer,
    ) -> dict[str, Any]:
        status = self._model_service.get_status()
        provider = str(status.get("provider") or "")
        model_name = str(status.get("model") or "")
        scope_key = self._scope_key(analysis_type, scope)
        input_hash = self._hash_input({
            "analysis_type": analysis_type,
            "scope": scope,
            "max_tokens": max_tokens,
            "data": source_data,
        })
        cache_key = {
            "sec_user_id": sec_user_id,
            "analysis_type": analysis_type,
            "scope_key": scope_key,
            "input_hash": input_hash,
            "provider": provider,
            "model_name": model_name,
            "prompt_version": prompt_version,
        }

        async with self._lock:
            cached = await self._repository.get_cached_result(**cache_key)
            if not force and cached is not None:
                return self._serialize_cache_item(cached, cache_hit=True)

            try:
                result = await self._model_service.generate_json(
                    system_prompt=system_prompt,
                    user_prompt=json.dumps(source_data, ensure_ascii=False, separators=(",", ":")),
                    max_tokens=max_tokens,
                )
                normalized = normalizer(result)
                ttl_hours = max(1, int(config.AI_ANALYSIS_CACHE_TTL_HOURS))
                item = await self._repository.upsert_result(
                    **cache_key,
                    status="done",
                    result=normalized,
                    scope=dict(scope),
                    expires_at=int(time.time()) + ttl_hours * 3600,
                )
                return self._serialize_cache_item(item, cache_hit=False)
            except Exception as exc:
                if cached is not None:
                    fallback = self._serialize_cache_item(cached, cache_hit=True)
                    fallback["refresh_error"] = str(exc)[:1000]
                    return fallback
                try:
                    await self._repository.mark_failed(**cache_key, error=str(exc)[:1000])
                except Exception:
                    pass
                raise

    @staticmethod
    def _valid_post_ids(value: Any, valid_ids: set[str]) -> list[str]:
        if not isinstance(value, list):
            return []
        result = []
        for item in value:
            post_id = str(item or "").strip()
            if post_id in valid_ids and post_id not in result:
                result.append(post_id)
        return result

    @staticmethod
    def _confidence(value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.0

    def _cluster_metrics(self, post_ids: list[str], posts_by_id: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
        rows = [posts_by_id[post_id] for post_id in post_ids if post_id in posts_by_id]
        interactions = [int((row.get("latest") or {}).get("interaction_total") or 0) for row in rows]
        total = sum(interactions)
        average = total / len(interactions) if interactions else 0
        middle = statistics.median(interactions) if interactions else 0
        threshold = max(middle * 2, 1)
        representatives = sorted(rows, key=lambda row: int((row.get("latest") or {}).get("interaction_total") or 0), reverse=True)[:3]
        return {
            "posts": len(rows),
            "total_interaction": total,
            "average_interaction": round(average, 2),
            "median_interaction": round(middle, 2),
            "burst_rate": round(sum(1 for value in interactions if value >= threshold) / len(interactions) * 100, 2) if interactions else 0,
            "representative_posts": [
                {
                    "aweme_id": row["aweme_id"],
                    "title": row.get("title") or row["aweme_id"],
                    "interaction_total": int((row.get("latest") or {}).get("interaction_total") or 0),
                    "create_time": row.get("create_time"),
                }
                for row in representatives
            ],
        }

    def _normalize_topic_result(self, result: Any, posts: list[dict[str, Any]]) -> dict[str, Any]:
        if not isinstance(result, dict):
            raise AIServiceError("AI topic analysis did not return a JSON object.", code="invalid_analysis")
        posts_by_id = {post["aweme_id"]: post for post in posts}
        valid_ids = set(posts_by_id)
        clusters = []
        for row in result.get("clusters") if isinstance(result.get("clusters"), list) else []:
            if not isinstance(row, dict):
                continue
            post_ids = self._valid_post_ids(row.get("post_ids"), valid_ids)
            if not post_ids:
                continue
            clusters.append({
                "name": _safe_text(row.get("name"), 100) or f"主题 {len(clusters) + 1}",
                "description": _safe_text(row.get("description"), 500),
                "keywords": _string_list(row.get("keywords"), 12),
                "representative_insight": _safe_text(row.get("representative_insight"), 500),
                "confidence": self._confidence(row.get("confidence")),
                **self._cluster_metrics(post_ids, posts_by_id),
            })
        if not clusters:
            raise AIServiceError("AI topic analysis did not contain valid post IDs.", code="invalid_analysis")

        tag_groups = []
        for row in result.get("tag_groups") if isinstance(result.get("tag_groups"), list) else []:
            if not isinstance(row, dict):
                continue
            tag_groups.append({
                "name": _safe_text(row.get("name"), 100),
                "tags": _string_list(row.get("tags"), 20),
                "summary": _safe_text(row.get("summary"), 500),
            })
        return {
            "summary": _safe_text(result.get("summary"), 2000),
            "clusters": clusters,
            "tag_groups": tag_groups,
            "recommendations": _string_list(result.get("recommendations"), 20),
            "data_limits": _string_list(result.get("data_limits"), 20),
            "source_post_count": len(posts),
        }

    def _normalize_lifecycle_result(self, result: Any, posts: list[dict[str, Any]]) -> dict[str, Any]:
        if not isinstance(result, dict):
            raise AIServiceError("AI lifecycle analysis did not return a JSON object.", code="invalid_analysis")
        posts_by_id = {post["aweme_id"]: post for post in posts}
        valid_ids = set(posts_by_id)
        insights = []
        for row in result.get("post_insights") if isinstance(result.get("post_insights"), list) else []:
            if not isinstance(row, dict):
                continue
            post_id = str(row.get("aweme_id") or "").strip()
            if post_id not in valid_ids:
                continue
            source = posts_by_id[post_id]
            insights.append({
                "aweme_id": post_id,
                "title": source.get("title") or post_id,
                "lifecycle_type": source.get("lifecycle_type"),
                "metrics": source.get("lifecycle_metrics") or {},
                "pattern": self._replace_post_ids(_safe_text(row.get("pattern"), 500), posts_by_id),
                "evidence": [self._replace_post_ids(item, posts_by_id) for item in _string_list(row.get("evidence"), 10)],
                "possible_factors": [self._replace_post_ids(item, posts_by_id) for item in _string_list(row.get("possible_factors"), 10)],
                "confidence": self._confidence(row.get("confidence")),
                "source": "model",
            })

        if not insights:
            for source in posts[:5]:
                insights.append({
                    "aweme_id": source["aweme_id"],
                    "title": source.get("title") or source["aweme_id"],
                    "lifecycle_type": source.get("lifecycle_type"),
                    "metrics": source.get("lifecycle_metrics") or {},
                    "pattern": self._fallback_lifecycle_pattern(source.get("lifecycle_type")),
                    "evidence": self._fallback_lifecycle_evidence(source),
                    "possible_factors": [],
                    "confidence": 0.0,
                    "source": "deterministic",
                })

        distribution: dict[str, int] = {}
        for post in posts:
            key = str(post.get("lifecycle_type") or "unknown")
            distribution[key] = distribution.get(key, 0) + 1

        stage_summary = []
        for stage in LIFECYCLE_STAGES:
            values = []
            for post in posts:
                snapshot = next((item for item in post.get("snapshots", []) if item.get("stage") == stage), None)
                if snapshot is not None:
                    values.append(int(snapshot.get("interaction_total") or 0))
            stage_summary.append({
                "stage": stage,
                "sample_count": len(values),
                "average_interaction": round(sum(values) / len(values), 2) if values else None,
            })

        stage_observation = self._lifecycle_stage_observation(posts, stage_summary)
        return {
            "overall_summary": self._replace_post_ids(_safe_text(result.get("overall_summary"), 2000), posts_by_id) or stage_observation,
            "stage_observation": stage_observation,
            "post_insights": insights,
            "content_patterns": [self._replace_post_ids(item, posts_by_id) for item in _string_list(result.get("content_patterns"), 20)],
            "anomaly_notes": [self._replace_post_ids(item, posts_by_id) for item in _string_list(result.get("anomaly_notes"), 20)],
            "recommendations": [self._replace_post_ids(item, posts_by_id) for item in _string_list(result.get("recommendations"), 20)],
            "caveats": [self._replace_post_ids(item, posts_by_id) for item in _string_list(result.get("caveats"), 20)],
            "type_distribution": distribution,
            "stage_summary": stage_summary,
            "source_post_count": len(posts),
        }

    @staticmethod
    def _lifecycle_stage_observation(posts: list[dict[str, Any]], stage_summary: list[dict[str, Any]]) -> str:
        available = [row for row in stage_summary if row.get("average_interaction") is not None]
        missing_72 = sum(
            1 for post in posts
            if not any(snapshot.get("stage") == "72h" for snapshot in post.get("snapshots", []))
        )
        if not available:
            return f"当前样本量较少（仅 {len(posts)} 篇），AI 已根据现有数据提供初步观察，但暂时无法判断主要增长阶段。"
        best = max(available, key=lambda row: row.get("average_interaction") or 0)
        observation = f"AI 观察到，本批次作品在 {best['stage']} 阶段（均值 {best.get('average_interaction')}）互动增长最为显著，是主要增长期。"
        if missing_72:
            observation += f" 同时有 {missing_72} 篇作品缺少 72h 快照，长尾判断仍需更多数据。"
        return observation

    @staticmethod
    def _replace_post_ids(text: str, posts_by_id: Mapping[str, Mapping[str, Any]]) -> str:
        result = str(text or "")
        for post_id, post in posts_by_id.items():
            title = str(post.get("title") or "").strip()
            if title:
                result = result.replace(post_id, f"《{title}》")
        return result

    @staticmethod
    def _fallback_lifecycle_pattern(lifecycle_type: Any) -> str:
        return {
            "earlyBurst": "互动主要在 1h 阶段形成，属于早爆节奏。",
            "quickDecline": "互动增量主要集中在 6h 阶段，后续增长放缓。",
            "longTail": "互动增量主要集中在 24h 阶段，存在较明显的长尾增长。",
            "sustained": "72h 阶段仍有增长，传播持续时间较长。",
            "unknown": "快照阶段不足，暂时无法判断传播节奏。",
        }.get(str(lifecycle_type or "unknown"), "快照阶段不足，暂时无法判断传播节奏。")

    @staticmethod
    def _fallback_lifecycle_evidence(post: Mapping[str, Any]) -> list[str]:
        metrics = post.get("lifecycle_metrics") or {}
        evidence = []
        if metrics.get("increment_1h") is not None:
            evidence.append(f"1h 互动为 {metrics['increment_1h']}")
        if metrics.get("increment_6h") is not None:
            evidence.append(f"1h→6h 增量为 {metrics['increment_6h']}")
        if metrics.get("increment_24h") is not None:
            evidence.append(f"6h→24h 增量为 {metrics['increment_24h']}")
        if metrics.get("increment_72h") is not None:
            evidence.append(f"24h→72h 增量为 {metrics['increment_72h']}")
        if not evidence:
            evidence.append("当前作品没有足够的阶段快照")
        return evidence

    @staticmethod
    def _insufficient_data(*, analysis_type: str, scope: Mapping[str, Any], message: str) -> dict[str, Any]:
        return {
            "id": None,
            "analysis_type": analysis_type,
            "status": "insufficient_data",
            "cache_hit": False,
            "scope": dict(scope),
            "result": {
                "summary": message,
                "data_limits": [message],
            },
        }

    @staticmethod
    def _serialize_cache_item(item, *, cache_hit: bool) -> dict[str, Any]:
        def loads(value: Optional[str], default):
            if not value:
                return default
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return default

        return {
            "id": item.id,
            "analysis_type": item.analysis_type,
            "status": item.status,
            "cache_hit": cache_hit,
            "scope": loads(item.scope_json, {}),
            "provider": item.provider,
            "model": item.model_name,
            "prompt_version": item.prompt_version,
            "result": loads(item.result_json, {}),
            "usage": loads(item.usage_json, {}),
            "created_at": item.created_at,
            "updated_at": item.updated_at,
            "expires_at": item.expires_at,
        }

    def serialize_result(self, item, *, cache_hit: bool = False) -> dict[str, Any]:
        return self._serialize_cache_item(item, cache_hit=cache_hit)


ai_analysis_service = AIAnalysisService()


__all__ = ["AIAnalysisService", "ai_analysis_service", "TOPIC_PROMPT_VERSION", "LIFECYCLE_PROMPT_VERSION"]
