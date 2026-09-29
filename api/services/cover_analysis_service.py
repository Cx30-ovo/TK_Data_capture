# -*- coding: utf-8 -*-
"""Full-scope cover vision scoring and deterministic interaction statistics."""

from __future__ import annotations

import asyncio
import base64
import bisect
import binascii
import hashlib
import math
import re
import statistics
from collections import defaultdict
from typing import Any, Mapping, Optional

import config
import httpx
from database.ai_analysis_repository import AIAnalysisRepository, ai_analysis_repository

from .ai_model_service import AIModelService, AIServiceError


COVER_PROMPT_VERSION = "cover_performance_v3"
COVER_VISION_SYSTEM_PROMPT = """
你是短视频封面视觉评估器。逐张识别客观视觉特征并独立评分，不分析互动量，不推断传播因果。
必须为每个图片 ID 返回一条记录；看不清时使用 unknown，不得猜测人物身份、地点或事件。
禁止输出 OCR 原文，只估算封面文字字符数。

六类结构化标签：
- theme_type：根据封面可见内容判断主题类型，不得依赖人物身份或地点猜测
- text_density：封面文字密度
- text_hook：封面文字采用的注意力钩子；无文字时返回 none，无法判断时返回 unknown
- composition：画面景别或版式构图
- visual_style：可选择 1 至 2 个视觉风格
- color_tone：整体色彩倾向

六项视觉评分均为 0 至 100 的整数：
- information_focus：信息聚焦
- visual_hierarchy：视觉层级
- subject_clarity：主体清晰
- text_readability：信息可读
- emotional_tension：情绪张力
- thumbnail_recognition：小图识别

输出结构：
{"items":[{
  "aweme_id":"",
  "theme_type":"news_event/people_story/public_affairs/livelihood_service/culture_tourism/sports_entertainment/product_service/graphic_information/other/unknown",
  "text_density":"none/low/medium/high/unknown",
  "text_hook":"none/news_headline/question/number_fact/emotional_quote/call_to_action/identity_label/benefit_promise/other/unknown",
  "text_character_count_estimate":0,
  "composition":"close_up/medium/wide/split/collage/centered/unknown",
  "visual_style":["news","documentary","portrait","poster","screenshot","scenery","product","minimal","other"],
  "color_tone":"warm/cool/neutral/mixed/unknown",
  "scores":{
    "information_focus":0,
    "visual_hierarchy":0,
    "subject_clarity":0,
    "text_readability":0,
    "emotional_tension":0,
    "thumbnail_recognition":0
  },
  "confidence":0.0
}]}
""".strip()


ENUMS = {
    "theme_type": {"news_event", "people_story", "public_affairs", "livelihood_service", "culture_tourism", "sports_entertainment", "product_service", "graphic_information", "other", "unknown"},
    "text_density": {"none", "low", "medium", "high", "unknown"},
    "text_hook": {"none", "news_headline", "question", "number_fact", "emotional_quote", "call_to_action", "identity_label", "benefit_promise", "other", "unknown"},
    "composition": {"close_up", "medium", "wide", "split", "collage", "centered", "unknown"},
    "color_tone": {"warm", "cool", "neutral", "mixed", "unknown"},
}
VISUAL_STYLES = {"news", "documentary", "portrait", "poster", "screenshot", "scenery", "product", "minimal", "other"}
SCORE_KEYS = (
    "information_focus",
    "visual_hierarchy",
    "subject_clarity",
    "text_readability",
    "emotional_tension",
    "thumbnail_recognition",
)
DIMENSION_NAMES = {
    "theme_type": "主题类型",
    "text_density": "文字密度",
    "text_hook": "文字钩子",
    "composition": "构图景别",
    "visual_style": "视觉风格",
    "color_tone": "色彩倾向",
}
DIMENSION_VALUE_NAMES = {
    "theme_type": {
        "news_event": "新闻事件", "people_story": "人物故事", "public_affairs": "政务公共",
        "livelihood_service": "民生服务", "culture_tourism": "文旅风景",
        "sports_entertainment": "体育娱乐", "product_service": "产品服务",
        "graphic_information": "图文资讯", "other": "其他", "unknown": "未知",
    },
    "text_density": {"none": "无字", "low": "少字", "medium": "中字", "high": "多字", "unknown": "未知"},
    "text_hook": {
        "none": "无钩子", "news_headline": "新闻标题", "question": "提问悬念",
        "number_fact": "数字事实", "emotional_quote": "情绪引语", "call_to_action": "行动指令",
        "identity_label": "身份标签", "benefit_promise": "利益承诺", "other": "其他", "unknown": "未知",
    },
    "composition": {
        "close_up": "近景", "medium": "中景", "wide": "远景", "split": "分栏",
        "collage": "拼贴", "centered": "居中", "unknown": "未知",
    },
    "visual_style": {
        "news": "新闻", "documentary": "纪实", "portrait": "人物肖像", "poster": "海报",
        "screenshot": "截图", "scenery": "风景", "product": "产品", "minimal": "简洁", "other": "其他",
    },
    "color_tone": {"warm": "暖色", "cool": "冷色", "neutral": "中性", "mixed": "混合", "unknown": "未知"},
}


def _cover_hash(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()


def _round(value: float, digits: int = 4) -> float:
    return round(float(value), digits)


def _score(value: Any) -> int:
    try:
        return int(round(max(0.0, min(100.0, float(value)))))
    except (TypeError, ValueError):
        return 0


def _normalize_label(raw: Mapping[str, Any], aweme_id: str) -> dict[str, Any]:
    result: dict[str, Any] = {"aweme_id": aweme_id}
    for key, allowed in ENUMS.items():
        value = str(raw.get(key) or "unknown").strip().lower()
        result[key] = value if value in allowed else "unknown"
    styles = raw.get("visual_style") if isinstance(raw.get("visual_style"), list) else []
    result["visual_style"] = list(dict.fromkeys(
        str(value).lower() for value in styles if str(value).lower() in VISUAL_STYLES
    ))[:4] or ["other"]
    try:
        result["text_character_count_estimate"] = max(0, min(200, int(raw.get("text_character_count_estimate") or 0)))
    except (TypeError, ValueError):
        result["text_character_count_estimate"] = 0
    raw_scores = raw.get("scores") if isinstance(raw.get("scores"), Mapping) else {}
    result["scores"] = {key: _score(raw_scores.get(key)) for key in SCORE_KEYS}
    result["visual_quality_score"] = _round(statistics.fmean(result["scores"].values()), 1)
    try:
        result["confidence"] = _round(max(0.0, min(1.0, float(raw.get("confidence") or 0.0))), 3)
    except (TypeError, ValueError):
        result["confidence"] = 0.0
    return result


def _percentile_scores(samples: list[Mapping[str, Any]]) -> dict[str, float]:
    """Return tie-aware 0-100 interaction percentiles inside the selected account scope."""
    values = sorted(int(row.get("interaction") or 0) for row in samples)
    if not values:
        return {}
    denominator = max(1, len(values) - 1)
    result: dict[str, float] = {}
    for row in samples:
        value = int(row.get("interaction") or 0)
        left = bisect.bisect_left(values, value)
        right = bisect.bisect_right(values, value) - 1
        average_rank = (left + right) / 2
        result[str(row.get("aweme_id") or "")] = _round(average_rank / denominator * 100, 1) if len(values) > 1 else 50.0
    return result


def _sample_status(count: int) -> str:
    if count < 10:
        return "insufficient"
    if count < 30:
        return "reference"
    return "stable"


def _validated_image_data_url(value: str) -> str:
    data_url = str(value or "").strip()
    match = re.fullmatch(r"data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=\r\n]+)", data_url, re.IGNORECASE)
    if not match:
        raise AIServiceError("Only JPEG, PNG, and WebP cover images are supported.", code="invalid_media")
    try:
        content = base64.b64decode(match.group(2), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AIServiceError("The uploaded cover image is not valid base64 data.", code="invalid_media") from exc
    if not content or len(content) > 8 * 1024 * 1024:
        raise AIServiceError("The uploaded cover image is empty or exceeds 8 MB.", code="invalid_media")
    return f"data:{match.group(1).lower()};base64,{base64.b64encode(content).decode('ascii')}"


def _candidate_similarity(candidate: Mapping[str, Any], historical: Mapping[str, Any]) -> float:
    values: list[float] = []
    for dimension in ("theme_type", "text_density", "text_hook", "composition", "color_tone"):
        candidate_value = str(candidate.get(dimension) or "unknown")
        historical_value = str(historical.get(dimension) or "unknown")
        values.append(1.0 if candidate_value != "unknown" and candidate_value == historical_value else 0.0)
    candidate_styles = {str(item) for item in candidate.get("visual_style", []) if str(item)}
    historical_styles = {str(item) for item in historical.get("visual_style", []) if str(item)}
    union = candidate_styles | historical_styles
    values.append(len(candidate_styles & historical_styles) / len(union) if union else 0.0)
    return statistics.fmean(values)


def _candidate_factor_evidence(labels: Mapping[str, Any], statistics_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    dimensions = statistics_payload.get("dimensions") if isinstance(statistics_payload.get("dimensions"), list) else []
    evidence: list[dict[str, Any]] = []
    for dimension in DIMENSION_NAMES:
        raw_values = labels.get(dimension)
        values = [str(item) for item in raw_values] if isinstance(raw_values, list) else [str(raw_values or "unknown")]
        matches = [
            row for row in dimensions
            if isinstance(row, Mapping) and str(row.get("dimension") or "") == dimension and str(row.get("label") or "") in values
        ]
        supported = [row for row in matches if int(row.get("count") or 0) >= 10]
        weight_total = sum(math.sqrt(max(1, int(row.get("count") or 0))) for row in supported)
        avg_data_score = (
            sum(float(row.get("avg_data_score") or 0) * math.sqrt(max(1, int(row.get("count") or 0))) for row in supported) / weight_total
            if weight_total else None
        )
        count = max((int(row.get("count") or 0) for row in matches), default=0)
        evidence.append({
            "dimension": dimension,
            "dimension_name": DIMENSION_NAMES[dimension],
            "labels": values,
            "label_names": [DIMENSION_VALUE_NAMES.get(dimension, {}).get(value, value) for value in values],
            "sample_count": count,
            "avg_data_score": _round(avg_data_score, 1) if avg_data_score is not None else None,
            "sample_status": _sample_status(count),
        })
    return evidence


def compute_cover_statistics(samples: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate controlled tags and scores. All arithmetic is deterministic Python."""
    if not samples:
        return {
            "sample_count": 0,
            "average_visual_score": 0.0,
            "average_data_score": 0.0,
            "average_cover_score": 0.0,
            "dimensions": [],
            "score_distribution": [],
        }

    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in samples:
        labels = row.get("labels") if isinstance(row.get("labels"), Mapping) else {}
        for dimension in ("theme_type", "text_density", "text_hook", "composition", "color_tone"):
            grouped[(dimension, str(labels.get(dimension) or "unknown"))].append(row)
        for value in labels.get("visual_style", []) if isinstance(labels.get("visual_style"), list) else []:
            grouped[("visual_style", str(value))].append(row)

    dimensions = []
    for (dimension, label), rows in grouped.items():
        interactions = [int(row.get("interaction") or 0) for row in rows]
        dimensions.append({
            "dimension": dimension,
            "dimension_name": DIMENSION_NAMES.get(dimension, dimension),
            "label": label,
            "label_name": DIMENSION_VALUE_NAMES.get(dimension, {}).get(label, label),
            "count": len(rows),
            "ratio": _round(len(rows) / len(samples)),
            "avg_interaction": _round(statistics.fmean(interactions), 2),
            "median_interaction": _round(statistics.median(interactions), 2),
            "avg_visual_score": _round(statistics.fmean(float(row.get("visual_quality_score") or 0) for row in rows), 1),
            "avg_data_score": _round(statistics.fmean(float(row.get("data_performance_score") or 0) for row in rows), 1),
            "avg_cover_score": _round(statistics.fmean(float(row.get("cover_performance_score") or 0) for row in rows), 1),
            "sample_status": _sample_status(len(rows)),
        })
    dimensions.sort(key=lambda row: (row["dimension"], -row["count"], -row["avg_cover_score"], row["label"]))

    buckets = (("优秀", 80, 101), ("良好", 65, 80), ("一般", 50, 65), ("偏弱", 0, 50))
    distribution = []
    for label, lower, upper in buckets:
        count = sum(1 for row in samples if lower <= float(row.get("cover_performance_score") or 0) < upper)
        distribution.append({"label": label, "count": count, "ratio": _round(count / len(samples))})

    return {
        "sample_count": len(samples),
        "average_visual_score": _round(statistics.fmean(float(row.get("visual_quality_score") or 0) for row in samples), 1),
        "average_data_score": _round(statistics.fmean(float(row.get("data_performance_score") or 0) for row in samples), 1),
        "average_cover_score": _round(statistics.fmean(float(row.get("cover_performance_score") or 0) for row in samples), 1),
        "score_formula": "视觉质量分 × 40% + 数据表现分 × 60%",
        "dimensions": dimensions,
        "score_distribution": distribution,
    }


class CoverAnalysisService:
    def __init__(
        self,
        model_service: Optional[AIModelService] = None,
        repository: Optional[AIAnalysisRepository] = None,
        image_loader=None,
    ) -> None:
        self._model_service = model_service or AIModelService(config.vision_ai_config)
        self._repository = repository or ai_analysis_repository
        self._image_loader = image_loader or self._inline_image

    def get_status(self) -> dict[str, Any]:
        return self._model_service.get_status()

    @staticmethod
    async def _inline_image(url: str) -> str:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/138 Safari/537.36",
            "Referer": "https://www.douyin.com/",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        }
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
        content = response.content
        if not content or len(content) > 8 * 1024 * 1024:
            raise AIServiceError("Cover image is empty or exceeds 8 MB.", code="invalid_media")
        media_type = str(response.headers.get("content-type") or "image/jpeg").split(";", 1)[0].strip().lower()
        if not media_type.startswith("image/"):
            media_type = "image/jpeg"
        return f"data:{media_type};base64,{base64.b64encode(content).decode('ascii')}"

    async def _label_batch(self, samples: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
        loaded = await asyncio.gather(
            *(self._image_loader(str(row["cover_url"])) for row in samples),
            return_exceptions=True,
        )
        images = [
            {"id": str(row["aweme_id"]), "url": value}
            for row, value in zip(samples, loaded)
            if isinstance(value, str) and value
        ]
        if not images:
            raise AIServiceError("No cover could be downloaded.", code="invalid_media")
        response = await self._model_service.generate_multimodal_json(
            system_prompt=COVER_VISION_SYSTEM_PROMPT,
            user_prompt="请按图片 ID 逐张输出客观视觉标签与六项评分，不要输出 OCR 原文。",
            images=images,
            max_tokens=int(config.VISION_AI_MAX_TOKENS),
        )
        items = response.get("items") if isinstance(response, dict) else None
        if not isinstance(items, list):
            raise AIServiceError("Vision model did not return an items array.", code="invalid_analysis")
        requested = {str(row["aweme_id"]) for row in samples}
        return [
            _normalize_label(row, str(row.get("aweme_id") or ""))
            for row in items
            if isinstance(row, dict) and str(row.get("aweme_id") or "") in requested
        ]

    async def evaluate_candidate(self, image_data_url: str, reference_analysis: Mapping[str, Any]) -> dict[str, Any]:
        """Score one unpublished cover and compare it with an existing account report."""
        status = self.get_status()
        if not status.get("configured"):
            raise AIServiceError("Vision model is not configured.", code="not_configured")
        image = _validated_image_data_url(image_data_url)
        response = await self._model_service.generate_multimodal_json(
            system_prompt=COVER_VISION_SYSTEM_PROMPT,
            user_prompt="请评估这张待发布封面。图片 ID 为 candidate；只输出客观标签与六项评分，不要输出 OCR 原文。",
            images=[{"id": "candidate", "url": image}],
            max_tokens=int(config.VISION_AI_MAX_TOKENS),
        )
        items = response.get("items") if isinstance(response, Mapping) else None
        raw = next((row for row in items or [] if isinstance(row, Mapping)), None)
        if raw is None:
            raise AIServiceError("Vision model did not return a candidate evaluation.", code="invalid_analysis")
        labels = _normalize_label(raw, "candidate")

        statistics_payload = reference_analysis.get("statistics") if isinstance(reference_analysis.get("statistics"), Mapping) else {}
        records = reference_analysis.get("score_records") if isinstance(reference_analysis.get("score_records"), list) else []
        historical_records = [row for row in records if isinstance(row, Mapping) and isinstance(row.get("labels"), Mapping)]
        similar = sorted(
            ((_candidate_similarity(labels, row.get("labels") or {}), row) for row in historical_records),
            key=lambda item: item[0],
            reverse=True,
        )
        similar = [item for item in similar if item[0] >= 0.5][:50]
        similar_weight = sum(score for score, _ in similar)
        similar_data_score = (
            sum(float(row.get("data_performance_score") or 0) * score for score, row in similar) / similar_weight
            if similar_weight else None
        )

        factor_evidence = _candidate_factor_evidence(labels, statistics_payload)
        supported_factors = [row for row in factor_evidence if row["avg_data_score"] is not None]
        factor_weight = sum(math.sqrt(max(1, int(row["sample_count"]))) for row in supported_factors)
        factor_data_score = (
            sum(float(row["avg_data_score"]) * math.sqrt(max(1, int(row["sample_count"]))) for row in supported_factors) / factor_weight
            if factor_weight else None
        )
        if len(similar) >= 10 and factor_data_score is not None:
            estimated_data_score = float(similar_data_score) * 0.6 + factor_data_score * 0.4
        elif len(similar) >= 10:
            estimated_data_score = float(similar_data_score)
        elif factor_data_score is not None:
            estimated_data_score = factor_data_score
        else:
            estimated_data_score = float(statistics_payload.get("average_data_score") or 50.0)

        stable_factors = sum(1 for row in factor_evidence if row["sample_status"] == "stable")
        if len(similar) >= 30 and stable_factors >= 4:
            confidence = "high"
        elif len(similar) >= 10 or stable_factors >= 3:
            confidence = "medium"
        else:
            confidence = "low"

        visual_score = float(labels.get("visual_quality_score") or 0)
        feasibility_score = visual_score * 0.4 + estimated_data_score * 0.6
        if confidence == "low":
            decision = "insufficient_reference"
        elif feasibility_score >= 65:
            decision = "recommended"
        elif feasibility_score >= 50:
            decision = "usable"
        else:
            decision = "adjust"

        historical_visual_scores = sorted(float(row.get("visual_quality_score") or 0) for row in historical_records)
        visual_percentile = (
            bisect.bisect_right(historical_visual_scores, visual_score) / len(historical_visual_scores) * 100
            if historical_visual_scores else 50.0
        )
        overall_data_score = float(statistics_payload.get("average_data_score") or 0)
        for row in factor_evidence:
            row["delta_vs_overall"] = (
                _round(float(row["avg_data_score"]) - overall_data_score, 1)
                if row["avg_data_score"] is not None else None
            )

        suggestions: list[dict[str, Any]] = []
        for key, value in sorted(labels.get("scores", {}).items(), key=lambda item: item[1]):
            if int(value) < 65:
                suggestions.append({"type": "visual", "code": key, "score": int(value)})
            if len(suggestions) >= 2:
                break
        weak_factor = min(
            (row for row in factor_evidence if row["delta_vs_overall"] is not None and row["sample_count"] >= 10),
            key=lambda row: float(row["delta_vs_overall"]),
            default=None,
        )
        if weak_factor and float(weak_factor["delta_vs_overall"]) <= -5:
            suggestions.append({
                "type": "factor",
                "dimension": weak_factor["dimension"],
                "label": " / ".join(weak_factor["label_names"]),
                "delta": weak_factor["delta_vs_overall"],
                "sample_count": weak_factor["sample_count"],
            })
        if not suggestions:
            suggestions.append({"type": "keep"})

        return {
            "status": "done",
            "model": status.get("model") or "",
            "decision": decision,
            "confidence": confidence,
            "visual_quality_score": _round(visual_score, 1),
            "estimated_data_score": _round(estimated_data_score, 1),
            "feasibility_score": _round(feasibility_score, 1),
            "visual_percentile": _round(visual_percentile, 1),
            "reference_count": len(historical_records),
            "similar_count": len(similar),
            "labels": labels,
            "factor_evidence": factor_evidence,
            "benchmark": {
                "average_visual_score": _round(float(statistics_payload.get("average_visual_score") or 0), 1),
                "average_data_score": _round(overall_data_score, 1),
                "average_cover_score": _round(float(statistics_payload.get("average_cover_score") or 0), 1),
            },
            "suggestions": suggestions[:3],
        }

    async def analyze_samples(self, samples: list[Mapping[str, Any]]) -> dict[str, Any]:
        """Analyze every valid cover inside the already-filtered work scope."""
        requested_count = len(samples)
        eligible = [row for row in samples if str(row.get("cover_url") or "").strip()]
        status = self.get_status()
        common = {
            "requested_sample_count": requested_count,
            "valid_cover_count": len(eligible),
            "missing_cover_count": requested_count - len(eligible),
            "model": status.get("model") or "",
        }
        if not status.get("configured"):
            return {**common, "status": "not_configured", "sample_count": 0, "failed_count": 0, "statistics": compute_cover_statistics([])}
        if not eligible:
            return {**common, "status": "no_covers", "sample_count": 0, "failed_count": 0, "statistics": compute_cover_statistics([])}

        model_name = str(status.get("model") or "")
        labels_by_id: dict[str, dict[str, Any]] = {}
        uncached: list[Mapping[str, Any]] = []
        for row in eligible:
            aweme_id = str(row["aweme_id"])
            cover_hash = _cover_hash(str(row["cover_url"]))
            cached = await self._repository.get_cover_label(
                aweme_id=aweme_id,
                cover_hash=cover_hash,
                model_name=model_name,
                prompt_version=COVER_PROMPT_VERSION,
            )
            if cached:
                labels_by_id[aweme_id] = _normalize_label(cached, aweme_id)
            else:
                uncached.append(row)

        errors: list[str] = []
        batch_size = int(config.VISION_AI_BATCH_SIZE)
        for offset in range(0, len(uncached), batch_size):
            batch = uncached[offset:offset + batch_size]
            try:
                labeled = await self._label_batch(batch)
            except Exception as exc:
                errors.append(re.sub(r"https?://\S+", "[image-url]", str(exc))[:300])
                labeled = []
                if len(batch) > 1:
                    for row in batch:
                        try:
                            labeled.extend(await self._label_batch([row]))
                        except Exception as item_exc:
                            errors.append(re.sub(r"https?://\S+", "[image-url]", str(item_exc))[:300])
            for labels in labeled:
                aweme_id = labels["aweme_id"]
                source = next((row for row in batch if str(row["aweme_id"]) == aweme_id), None)
                if source is None:
                    continue
                labels_by_id[aweme_id] = labels
                await self._repository.upsert_cover_label(
                    aweme_id=aweme_id,
                    cover_hash=_cover_hash(str(source["cover_url"])),
                    model_name=model_name,
                    prompt_version=COVER_PROMPT_VERSION,
                    labels=labels,
                )

        data_scores = _percentile_scores(samples)
        scored_samples = []
        for row in eligible:
            aweme_id = str(row["aweme_id"])
            labels = labels_by_id.get(aweme_id)
            if labels is None:
                continue
            visual_score = float(labels.get("visual_quality_score") or 0)
            data_score = float(data_scores.get(aweme_id, 0))
            scored_samples.append({
                "aweme_id": aweme_id,
                "title": str(row.get("title") or aweme_id)[:300],
                "cover_url": str(row.get("cover_url") or ""),
                "canonical_url": str(row.get("canonical_url") or ""),
                "create_time": int(row.get("create_time") or 0),
                "publish_time": str(row.get("publish_time") or ""),
                "interaction": int(row.get("interaction") or 0),
                "likes": int(row.get("likes") or 0),
                "comments": int(row.get("comments") or 0),
                "collects": int(row.get("collects") or 0),
                "shares": int(row.get("shares") or 0),
                "visual_quality_score": _round(visual_score, 1),
                "data_performance_score": _round(data_score, 1),
                "cover_performance_score": _round(visual_score * 0.4 + data_score * 0.6, 1),
                "labels": labels,
            })
        return {
            **common,
            "status": "done" if len(scored_samples) == len(eligible) else "partial",
            "sample_count": len(scored_samples),
            "failed_count": len(eligible) - len(scored_samples),
            "prompt_version": COVER_PROMPT_VERSION,
            "statistics": compute_cover_statistics(scored_samples),
            "score_records": [
                {
                    "aweme_id": row["aweme_id"],
                    "title": row["title"],
                    "cover_url": row["cover_url"],
                    "canonical_url": row["canonical_url"],
                    "create_time": row["create_time"],
                    "publish_time": row["publish_time"],
                    "interaction": row["interaction"],
                    "likes": row["likes"],
                    "comments": row["comments"],
                    "collects": row["collects"],
                    "shares": row["shares"],
                    "visual_quality_score": row["visual_quality_score"],
                    "data_performance_score": row["data_performance_score"],
                    "cover_performance_score": row["cover_performance_score"],
                    "labels": row["labels"],
                }
                for row in scored_samples
            ],
            "errors": list(dict.fromkeys(errors))[:3],
        }


cover_analysis_service = CoverAnalysisService()


__all__ = [
    "COVER_PROMPT_VERSION",
    "COVER_VISION_SYSTEM_PROMPT",
    "CoverAnalysisService",
    "compute_cover_statistics",
    "cover_analysis_service",
]
