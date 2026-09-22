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
from .cover_analysis_service import cover_analysis_service
from .title_strategy_metrics import DATA_LIMIT, clean_title, compute_title_strategy
from .title_strategy_prompts import HIT_SYSTEM_PROMPT, PATTERN_SYSTEM_PROMPT, STRATEGY_SYSTEM_PROMPT


TOPIC_PROMPT_VERSION = "topic-v8"
LIFECYCLE_PROMPT_VERSION = "lifecycle-v2"
TOPIC_IDEAS_PROMPT_VERSION = "topic-ideas-v4"
TITLE_STRATEGY_PROMPT_VERSION = "title-strategy-v2-cover"
TIME_RANGE_SECONDS = {
    "24h": 24 * 60 * 60,
    "7d": 7 * 24 * 60 * 60,
    "30d": 30 * 24 * 60 * 60,
}
LIFECYCLE_STAGES = ("1h", "6h", "24h", "72h")


TOPIC_SYSTEM_PROMPT = """
你是抖音内容研究分析师。你只能使用输入中已有的作品 ID、标题、标签、最新点赞、最新收藏、最新评论和最新总互动。

任务要求：
1. 将作品归纳为 3 到 6 个主题聚类，描述保持简洁。
2. 每个聚类必须返回主题名称、简短说明、作品 ID 列表、4 到 10 个关键词和 0 到 1 之间的置信度。
3. 不允许编造作品 ID、标签或互动数字。
4. 不允许把相关性表述为确定因果。
5. 信息不足时写入 data_limits，不要猜测。
6. summary 必须比较表现最好和较低的主题。
7. recommendations 只输出行动建议，不要直接罗列互动数字。
8. representative_insight 只补充 description 中没有出现的具体爆点规律；如果无法提供额外信息，返回空字符串，禁止重复 description。

输出 JSON 结构：
{
  "summary": "整体主题与表现摘要",
  "clusters": [
    {
      "name": "主题名称",
      "description": "主题内容说明",
      "post_ids": ["作品ID"],
      "keywords": ["关键词"],
      "representative_insight": "仅当有额外代表作规律时填写，否则为空字符串",
      "confidence": 0.9
    }
  ],
  "tag_groups": [
    {"name": "标签组名称", "tags": ["标签"], "summary": "标签共同表达的内容"}
  ],
  "recommendations": [],
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


TOPIC_IDEAS_SYSTEM_PROMPT = """
你是抖音内容策划编辑。你会收到一份已经生成的主题分析报告，只能基于报告中的主题表现、标签、代表作特征和行动建议提出选题方案。

任务要求：
1. 生成 3 到 4 个具体、可执行、彼此有差异的选题方案。
2. 选题必须能够直接指导拍摄或制作，不能只写抽象主题。
3. 优先选择互动表现好、内容供给有差异、可持续跟踪的选题。
4. 不允许编造报告中没有的数据、事件或作品。
5. 不希望直接重复报告里的行动建议，必须转成具体内容方案。
6. 每个方案说明推荐理由、内容角度、适合形式、目标受众、预期表现和风险。
7. strategy_points 必须明确区分数据依据、排除范围和生成原则，每组最多 3 条。
8. 每个选题必须解释 viral_reason：为什么这个标题在现有数据下更可能获得互动。
9. title_formula 提炼标题结构，title_variants 给出 2 个可直接使用的改写标题。
10. writing_notes 用一句话解释为什么使用这些词、结构或情绪表达。

输出 JSON 结构：
{
  "summary": "一句话说明本次选题策略",
  "strategy_points": {
    "data_basis": ["基于数据得出的结论"],
    "exclusions": ["暂不优先投入的方向及原因"],
    "principles": ["生成方案时遵循的原则"]
  },
  "ideas": [
    {
      "title": "具体选题名称",
      "angle": "内容切入角度",
      "format": "短视频系列 / 实地探访 / 对比盘点等",
      "audience": "目标受众",
      "why_now": "基于主题报告的数据依据和推荐原因",
      "evidence": ["引用的主题名称或代表作特征"],
      "viral_reason": "为什么这个标题可能爆，必须引用报告中的主题表现",
      "title_formula": "标题结构公式",
      "title_variants": ["改写标题1", "改写标题2"],
      "writing_notes": "解释为什么这样写更容易被点击或产生互动",
      "expected_performance": "high / medium / low",
      "difficulty": "low / medium / high",
      "risk_notes": "执行风险或注意事项",
      "priority": 1
    }
  ],
  "avoid": ["不建议近期投入的方向"]
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
        cover_analysis_service_instance=None,
    ) -> None:
        self._model_service = model_service or ai_model_service
        self._repository = analysis_repository or ai_analysis_repository
        self._monitor_repository = monitor_repository_instance or monitor_repository
        self._cover_analysis_service = cover_analysis_service_instance or cover_analysis_service
        self._lock = asyncio.Lock()

    async def analyze_topics(
        self,
        *,
        sec_user_id: str,
        scope: Optional[Mapping[str, Any]] = None,
        force: bool = False,
    ) -> dict[str, Any]:
        normalized_scope = self._normalize_scope(scope, default_limit=100)
        normalized_scope["today_only"] = True
        normalized_scope["analysis_date"] = datetime.now().date().isoformat()
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
            max_tokens=max(int(config.AI_MAX_TOKENS), 12288),
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
        normalized_scope["today_only"] = True
        normalized_scope["analysis_date"] = datetime.now().date().isoformat()
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

    async def analyze_title_strategy(
        self,
        *,
        sec_user_id: str,
        scope: Optional[Mapping[str, Any]] = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Run deterministic statistics followed by three compact semantic model calls."""
        values = dict(scope or {})
        time_range = str(values.get("time_range") or "30d")
        if time_range not in {*TIME_RANGE_SECONDS.keys(), "all"}:
            time_range = "30d"
        try:
            post_limit = int(values.get("post_limit") or 1000)
        except (TypeError, ValueError):
            post_limit = 1000
        normalized_scope = {"time_range": time_range, "post_limit": max(3, min(post_limit, 10000))}
        posts, snapshots_by_post = await self._load_source(sec_user_id, normalized_scope)
        if len(posts) < 3:
            return self._insufficient_data(
                analysis_type="title_strategy",
                scope=normalized_scope,
                message="标题策略分析至少需要 3 篇作品数据。",
            )

        metrics = compute_title_strategy(posts, snapshots_by_post)
        sample_limit = int(config.VISION_AI_SAMPLE_LIMIT)
        hit_limit = sample_limit // 2
        selected_rows = list(metrics.get("hit_samples", []))[:hit_limit]
        selected_rows.extend(list(metrics.get("normal_samples", []))[:sample_limit - len(selected_rows)])
        if len(selected_rows) < sample_limit:
            selected_ids = {str(row.get("aweme_id")) for row in selected_rows if isinstance(row, dict)}
            remaining = [
                row for row in [*metrics.get("hit_samples", []), *metrics.get("normal_samples", [])]
                if isinstance(row, dict) and str(row.get("aweme_id")) not in selected_ids
            ]
            selected_rows.extend(remaining[:sample_limit - len(selected_rows)])
        posts_by_id = {str(post.aweme_id): post for post in posts}
        hit_ids = {str(row.get("aweme_id")) for row in metrics.get("hit_samples", []) if isinstance(row, dict)}
        cover_samples = []
        for row in selected_rows:
            post_id = str(row.get("aweme_id") or "")
            post = posts_by_id.get(post_id)
            if post is None:
                continue
            cover_samples.append({
                **row,
                "cover_url": str(getattr(post, "cover_url", "") or ""),
                "is_hit": post_id in hit_ids,
            })
        metrics["cover_analysis"] = await self._cover_analysis_service.analyze_samples(cover_samples)
        account = await self._monitor_repository.get_monitored_account(sec_user_id)
        account_name = _safe_text(getattr(account, "display_name", ""), 100) or sec_user_id
        period = self._analysis_period(posts, time_range)
        source_data = {
            "account": account_name,
            "period": period,
            "scope": normalized_scope,
            "metrics": metrics,
        }
        return await self._run_cached_title_strategy(
            sec_user_id=sec_user_id,
            scope=normalized_scope,
            source_data=source_data,
            force=force,
        )

    async def analyze_topic_ideas(
        self,
        *,
        sec_user_id: str,
        topic_result_id: int,
        force: bool = False,
    ) -> dict[str, Any]:
        source = await self._repository.get_result(topic_result_id)
        if source is None or source.sec_user_id != sec_user_id or source.analysis_type != "topic" or source.status != "done":
            raise AIServiceError("A completed topic report is required before generating ideas.", code="source_not_found")
        try:
            topic_report = json.loads(source.result_json or "{}")
        except json.JSONDecodeError as exc:
            raise AIServiceError("The source topic report is invalid.", code="source_not_found") from exc

        source_data = {
            "topic_report": topic_report,
            "source_result_id": topic_result_id,
            "generated_at": source.updated_at,
        }
        scope = {"source_result_id": topic_result_id}
        return await self._run_cached_analysis(
            sec_user_id=sec_user_id,
            analysis_type="topic_ideas",
            scope=scope,
            source_data=source_data,
            prompt_version=TOPIC_IDEAS_PROMPT_VERSION,
            system_prompt=TOPIC_IDEAS_SYSTEM_PROMPT,
            max_tokens=int(config.AI_MAX_TOKENS),
            force=force,
            normalizer=self._normalize_topic_ideas_result,
        )

    @staticmethod
    def _analysis_period(posts: list, time_range: str) -> str:
        timestamps = [int(post.create_time or 0) for post in posts if int(post.create_time or 0) > 0]
        if not timestamps:
            return time_range
        start = datetime.fromtimestamp(min(timestamps)).date().isoformat()
        end = datetime.fromtimestamp(max(timestamps)).date().isoformat()
        return start if start == end else f"{start} 至 {end}"

    async def _run_cached_title_strategy(
        self,
        *,
        sec_user_id: str,
        scope: Mapping[str, Any],
        source_data: Mapping[str, Any],
        force: bool,
    ) -> dict[str, Any]:
        status = self._model_service.get_status()
        provider = str(status.get("provider") or "")
        model_name = str(status.get("model") or "")
        scope_key = self._scope_key("title_strategy", scope)
        input_hash = self._hash_input(source_data)
        cache_key = {
            "sec_user_id": sec_user_id,
            "analysis_type": "title_strategy",
            "scope_key": scope_key,
            "input_hash": input_hash,
            "provider": provider,
            "model_name": model_name,
            "prompt_version": TITLE_STRATEGY_PROMPT_VERSION,
        }

        async with self._lock:
            cached = await self._repository.get_cached_result(**cache_key)
            if not force and cached is not None:
                return self._serialize_cache_item(cached, cache_hit=True)

            previous_item = await self._repository.get_latest_result(
                sec_user_id=sec_user_id,
                analysis_type="title_strategy",
                status="done",
            )
            previous_result: dict[str, Any] = {}
            if previous_item and previous_item.result_json:
                try:
                    previous_result = json.loads(previous_item.result_json)
                except json.JSONDecodeError:
                    previous_result = {}

            metrics = dict(source_data.get("metrics") or {})
            overview = dict(metrics.get("overview") or {})
            compact_context = {
                "account_positioning": source_data.get("account"),
                "period": source_data.get("period"),
                "total_works": overview.get("total_works"),
                "interaction_formula": "点赞 + 2×评论 + 2×收藏 + 3×转发",
                "hit_definition": "互动分 >= max(P90, 均值 + 2×标准差)",
                "data_limit": DATA_LIMIT,
            }
            phase_one_payload = {
                **compact_context,
                "top_keywords": metrics.get("top_keywords") or [],
                "title_length_groups": metrics.get("title_length_groups") or [],
                "long_vs_short": metrics.get("long_vs_short") or {},
                # The text model receives only controlled cover tags and Python
                # aggregates. Image URLs and pixels never enter this request.
                "cover_tags": self._cover_text_payload(metrics.get("cover_analysis") or {}),
            }

            previous_hits = {
                str(row.get("aweme_id")): row
                for row in previous_result.get("hit_works", [])
                if isinstance(row, dict) and row.get("aweme_id")
            }
            current_hits = [row for row in metrics.get("hit_samples", []) if isinstance(row, dict)]
            new_hits = [row for row in current_hits if str(row.get("aweme_id")) not in previous_hits]
            retained_hits = [
                {
                    "aweme_id": row.get("aweme_id"),
                    "title": row.get("title"),
                    "hook_type": row.get("hook_type"),
                    "why_viral": row.get("why_viral"),
                    "title_formula": row.get("title_formula"),
                }
                for row in previous_result.get("hit_works", [])
                if isinstance(row, dict) and str(row.get("aweme_id")) in {str(item.get("aweme_id")) for item in current_hits}
            ]
            phase_two_payload = {
                **compact_context,
                "hit_samples_to_analyze": new_hits or current_hits,
                "reused_hit_analyses": retained_hits if new_hits else [],
                "normal_samples": metrics.get("normal_samples") or [],
            }

            try:
                max_tokens = max(4096, int(config.AI_MAX_TOKENS))
                phase_one = await self._model_service.generate_json(
                    system_prompt=PATTERN_SYSTEM_PROMPT,
                    user_prompt=json.dumps(phase_one_payload, ensure_ascii=False, separators=(",", ":")),
                    max_tokens=max_tokens,
                )
                phase_two = await self._model_service.generate_json(
                    system_prompt=HIT_SYSTEM_PROMPT,
                    user_prompt=json.dumps(phase_two_payload, ensure_ascii=False, separators=(",", ":")),
                    max_tokens=max_tokens,
                )
                phase_three = await self._model_service.generate_json(
                    system_prompt=STRATEGY_SYSTEM_PROMPT,
                    user_prompt=json.dumps({
                        **compact_context,
                        "phase_one_result": phase_one,
                        "phase_two_result": phase_two,
                    }, ensure_ascii=False, separators=(",", ":")),
                    max_tokens=max_tokens,
                )
                normalized = self._normalize_title_strategy_result(
                    source_data=source_data,
                    phase_one=phase_one,
                    phase_two=phase_two,
                    phase_three=phase_three,
                    previous_result=previous_result,
                )
                item = await self._repository.upsert_result(
                    **cache_key,
                    status="done",
                    result=normalized,
                    scope={**dict(scope), "total_works": overview.get("total_works", 0)},
                    # The input hash already invalidates the cache when posts or snapshots change.
                    # Keeping the exact-input result avoids repeating three model calls after a TTL.
                    expires_at=None,
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
    def _strategy_text(value: Any, limit: int = 1200, fallback: str = "数据不足") -> str:
        text = _safe_text(value, limit)
        forbidden = ("互动率", "完播率", "点击率", "曝光转化率")
        return fallback if not text or any(term in text for term in forbidden) else text

    def _strategy_list(self, value: Any, limit: int = 10) -> list[str]:
        if not isinstance(value, list):
            return []
        result = []
        for item in value:
            text = self._strategy_text(item, 600, "")
            if text and text not in result:
                result.append(text)
            if len(result) >= limit:
                break
        return result

    def _normalize_title_strategy_result(
        self,
        *,
        source_data: Mapping[str, Any],
        phase_one: Any,
        phase_two: Any,
        phase_three: Any,
        previous_result: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not all(isinstance(value, dict) for value in (phase_one, phase_two, phase_three)):
            raise AIServiceError("Title strategy analysis did not return JSON objects.", code="invalid_analysis")
        metrics = dict(source_data.get("metrics") or {})
        overview = dict(metrics.get("overview") or {})

        keyword_conclusions = {
            str(row.get("keyword")): self._strategy_text(row.get("conclusion"), 500)
            for row in phase_one.get("top_keywords", [])
            if isinstance(row, dict) and row.get("keyword")
        }
        top_keywords = [
            {**row, "conclusion": keyword_conclusions.get(str(row.get("keyword")), "数据不足")}
            for row in metrics.get("top_keywords", [])
            if isinstance(row, dict)
        ]

        length_ai = phase_one.get("title_length_analysis") if isinstance(phase_one.get("title_length_analysis"), dict) else {}
        long_short_ai = length_ai.get("long_vs_short") if isinstance(length_ai.get("long_vs_short"), dict) else {}
        title_length_analysis = {
            "groups": metrics.get("title_length_groups") or [],
            "long_vs_short": metrics.get("long_vs_short") or {},
            "best_range": self._strategy_text(length_ai.get("best_range"), 80),
            "trend": self._strategy_text(length_ai.get("trend"), 800),
            "winner": self._strategy_text(long_short_ai.get("winner"), 80),
            "comparison_explanation": self._strategy_text(long_short_ai.get("explanation"), 800),
            "recommendation": self._strategy_text(length_ai.get("recommendation"), 1000),
        }

        previous_hits = {
            str(row.get("aweme_id")): row
            for row in previous_result.get("hit_works", [])
            if isinstance(row, dict) and row.get("aweme_id")
        }
        model_hits = {
            str(row.get("aweme_id")): row
            for row in phase_two.get("hit_works", [])
            if isinstance(row, dict) and row.get("aweme_id")
        }
        hit_works = []
        reused_count = 0
        for sample in metrics.get("hit_samples", []):
            if not isinstance(sample, dict):
                continue
            post_id = str(sample.get("aweme_id") or "")
            semantic = model_hits.get(post_id) or previous_hits.get(post_id) or {}
            if post_id in previous_hits and post_id not in model_hits:
                reused_count += 1
            hit_works.append({
                **sample,
                "hook_type": self._strategy_text(semantic.get("hook_type"), 100),
                "why_viral": self._strategy_text(semantic.get("why_viral"), 1000),
                "title_formula": self._strategy_text(semantic.get("title_formula"), 500),
                "interaction_structure": self._strategy_text(semantic.get("interaction_structure"), 800),
            })

        comparison = phase_two.get("hit_vs_normal") if isinstance(phase_two.get("hit_vs_normal"), dict) else {}
        reusable_formulas = []
        for row in phase_two.get("reusable_formulas", []):
            if not isinstance(row, dict):
                continue
            reusable_formulas.append({
                "formula": self._strategy_text(row.get("formula"), 300),
                "example": self._strategy_text(row.get("example"), 300),
                "why_effective": self._strategy_text(row.get("why_effective"), 800),
            })
            if len(reusable_formulas) >= 10:
                break

        strategy = phase_three.get("strategy_summary") if isinstance(phase_three.get("strategy_summary"), dict) else {}
        next_titles = []
        for row in phase_three.get("next_titles", []):
            if not isinstance(row, dict):
                continue
            title = self._strategy_text(row.get("title"), 180, "")
            if not title:
                continue
            next_titles.append({
                "title": title,
                "formula": self._strategy_text(row.get("formula"), 300),
                "expected_length": len(clean_title(title)),
                "target_audience": self._strategy_text(row.get("target_audience"), 300),
                "hook_type": self._strategy_text(row.get("hook_type"), 100),
            })
            if len(next_titles) >= 10:
                break

        risk_notes = self._strategy_list(phase_three.get("risk_notes"), 10)
        if DATA_LIMIT not in risk_notes:
            risk_notes.insert(0, DATA_LIMIT)
        return {
            "overview": {
                **overview,
                "core_finding": self._strategy_text(strategy.get("core_finding") or phase_one.get("overall_insight"), 1500),
                "title_length_advice": self._strategy_text(strategy.get("title_length_advice"), 1000),
                "keyword_advice": self._strategy_text(strategy.get("keyword_advice"), 1000),
                "content_advice": self._strategy_text(strategy.get("content_advice"), 1000),
            },
            "top_keywords": top_keywords,
            "title_length_analysis": title_length_analysis,
            "hit_works": hit_works,
            "hit_vs_normal": {
                "key_differences": self._strategy_list(comparison.get("key_differences"), 10),
                "common_patterns": self._strategy_text(comparison.get("common_patterns"), 1200),
            },
            "reusable_formulas": reusable_formulas,
            "next_titles": next_titles,
            "risk_notes": risk_notes,
            "title_templates": metrics.get("title_templates") or [],
            "cover_analysis": self._normalize_cover_analysis(
                metrics.get("cover_analysis") or {},
                phase_one.get("cover_analysis") if isinstance(phase_one.get("cover_analysis"), dict) else {},
            ),
            "meta": {
                "account": source_data.get("account"),
                "period": source_data.get("period"),
                "total_works": overview.get("total_works", 0),
                "hit_threshold": overview.get("hit_threshold", 0),
                "data_limit": DATA_LIMIT,
                "interaction_formula": "点赞 + 2×评论 + 2×收藏 + 3×转发",
                "source_post_ids": metrics.get("source_post_ids") or [],
                "reused_hit_analyses": reused_count,
            },
        }

    @staticmethod
    def _cover_text_payload(cover_analysis: Mapping[str, Any]) -> dict[str, Any]:
        statistics_payload = cover_analysis.get("statistics") if isinstance(cover_analysis.get("statistics"), dict) else {}
        return {
            "status": cover_analysis.get("status"),
            "sample_count": cover_analysis.get("sample_count", 0),
            "statistics": statistics_payload,
            "rule": "这里只包含结构化标签的Python聚合统计，不包含图片、URL、OCR原文或作品标题；只能解释相关性，不得推断因果。",
        }

    def _normalize_cover_analysis(
        self,
        cover_analysis: Mapping[str, Any],
        model_analysis: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            **dict(cover_analysis),
            "summary": self._strategy_text(model_analysis.get("summary"), 1200),
            "hit_differences": self._strategy_list(model_analysis.get("hit_differences"), 8),
            "recommendations": self._strategy_list(model_analysis.get("recommendations"), 8),
        }

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
            posts = [post for post in posts if int(post.create_time or 0) >= cutoff]
        if scope.get("today_only"):
            today = datetime.now().date()
            posts = [post for post in posts if datetime.fromtimestamp(int(post.create_time)).date() == today]

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
        result = []
        for post in posts:
            latest = (snapshots_by_post.get(post.aweme_id) or [None])[-1]
            result.append({
                "aweme_id": post.aweme_id,
                "title": self._truncate(post.title or post.aweme_id, 180),
                "tags": self._tags(post),
                "latest": {
                    "liked_count": int(latest.liked_count or 0) if latest else 0,
                    "collected_count": int(latest.collected_count or 0) if latest else 0,
                    "comment_count": int(latest.comment_count or 0) if latest else 0,
                    "interaction_total": self._interaction(latest) if latest else 0,
                },
            })
        return result

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
        if "source_result_id" in scope:
            return f"{analysis_type}:source={scope['source_result_id']}"
        if scope.get("analysis_date"):
            return f"{analysis_type}:date={scope['analysis_date']}:limit={scope['post_limit']}"
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
                "keywords": _string_list(row.get("keywords"), 20),
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

    def _normalize_topic_ideas_result(self, result: Any) -> dict[str, Any]:
        if not isinstance(result, dict):
            raise AIServiceError("AI topic ideas did not return a JSON object.", code="invalid_analysis")
        ideas = []
        rows = result.get("ideas") if isinstance(result.get("ideas"), list) else []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            title = _safe_text(row.get("title"), 160)
            if not title:
                continue
            expected = str(row.get("expected_performance") or "medium").lower()
            difficulty = str(row.get("difficulty") or "medium").lower()
            ideas.append({
                "id": index + 1,
                "title": title,
                "angle": _safe_text(row.get("angle"), 700),
                "format": _safe_text(row.get("format"), 200),
                "audience": _safe_text(row.get("audience"), 300),
                "why_now": _safe_text(row.get("why_now"), 700),
                "evidence": _string_list(row.get("evidence"), 8),
                "viral_reason": _safe_text(row.get("viral_reason"), 1000),
                "title_formula": _safe_text(row.get("title_formula"), 300),
                "title_variants": _string_list(row.get("title_variants"), 5),
                "writing_notes": _safe_text(row.get("writing_notes"), 1000),
                "expected_performance": expected if expected in {"high", "medium", "low"} else "medium",
                "difficulty": difficulty if difficulty in {"high", "medium", "low"} else "medium",
                "risk_notes": _safe_text(row.get("risk_notes"), 500),
                "priority": index + 1,
            })
            if len(ideas) >= 4:
                break
        if not ideas:
            raise AIServiceError("AI topic ideas did not contain valid ideas.", code="invalid_analysis")
        strategy = result.get("strategy_points") if isinstance(result.get("strategy_points"), dict) else {}
        return {
            "summary": _safe_text(result.get("summary"), 1500),
            "strategy_points": {
                "data_basis": _string_list(strategy.get("data_basis"), 8),
                "exclusions": _string_list(strategy.get("exclusions"), 8),
                "principles": _string_list(strategy.get("principles"), 8),
            },
            "ideas": ideas,
            "avoid": _string_list(result.get("avoid"), 10),
        }

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


__all__ = [
    "AIAnalysisService",
    "ai_analysis_service",
    "TOPIC_PROMPT_VERSION",
    "LIFECYCLE_PROMPT_VERSION",
    "TITLE_STRATEGY_PROMPT_VERSION",
]
