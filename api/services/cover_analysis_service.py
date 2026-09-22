# -*- coding: utf-8 -*-
"""Sample-only cover OCR/vision labeling and deterministic Python statistics."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import re
import statistics
from collections import defaultdict
from typing import Any, Mapping, Optional

import config
import httpx
from database.ai_analysis_repository import AIAnalysisRepository, ai_analysis_repository

from .ai_model_service import AIModelService, AIServiceError


COVER_PROMPT_VERSION = "cover_labels_v1"
COVER_VISION_SYSTEM_PROMPT = """
你是短视频封面 OCR 与视觉标注器。逐张识别图片文字和视觉特征，只做客观标注，不分析传播效果。
必须为每个图片ID返回一条记录；看不清时使用 unknown，不得猜测人物身份、地点或事件。

输出结构：
{"items":[{
  "aweme_id":"",
  "ocr_text":"",
  "text_density":"none/low/medium/high",
  "text_position":"none/top/center/bottom/multiple",
  "text_hook":"none/news_headline/question/number_fact/emotional_quote/call_to_action/identity_label/benefit_promise/other",
  "subject_type":"person/news_scene/object/scenery/screenshot/graphic/mixed/unknown",
  "person_count":"0/1/2/many/unknown",
  "face_closeup":false,
  "composition":"close_up/medium/wide/split/collage/unknown",
  "color_tone":"warm/cool/neutral/mixed/unknown",
  "brightness":"dark/medium/bright/unknown",
  "contrast":"low/medium/high/unknown",
  "information_density":"low/medium/high/unknown",
  "visual_style":["news","documentary","portrait","poster","screenshot","scenery","product","other"],
  "emotion":"positive/negative/tense/neutral/unknown",
  "has_logo":false,
  "has_subtitle_bar":false,
  "has_number":false,
  "confidence":0.0
}]}
""".strip()


ENUMS = {
    "text_density": {"none", "low", "medium", "high"},
    "text_position": {"none", "top", "center", "bottom", "multiple"},
    "text_hook": {"none", "news_headline", "question", "number_fact", "emotional_quote", "call_to_action", "identity_label", "benefit_promise", "other"},
    "subject_type": {"person", "news_scene", "object", "scenery", "screenshot", "graphic", "mixed", "unknown"},
    "person_count": {"0", "1", "2", "many", "unknown"},
    "composition": {"close_up", "medium", "wide", "split", "collage", "unknown"},
    "color_tone": {"warm", "cool", "neutral", "mixed", "unknown"},
    "brightness": {"dark", "medium", "bright", "unknown"},
    "contrast": {"low", "medium", "high", "unknown"},
    "information_density": {"low", "medium", "high", "unknown"},
    "emotion": {"positive", "negative", "tense", "neutral", "unknown"},
}
VISUAL_STYLES = {"news", "documentary", "portrait", "poster", "screenshot", "scenery", "product", "other"}
DIMENSION_NAMES = {
    "subject_type": "主体类型",
    "composition": "构图景别",
    "text_density": "文字密度",
    "text_position": "文字位置",
    "text_hook": "文字钩子",
    "color_tone": "色彩倾向",
    "brightness": "明暗",
    "contrast": "对比度",
    "information_density": "信息密度",
    "emotion": "情绪氛围",
    "visual_style": "视觉风格",
    "face_closeup": "人脸特写",
    "has_logo": "品牌标识",
    "has_subtitle_bar": "字幕条",
    "has_number": "数字元素",
    "ocr_length": "封面字数",
}
VALUE_NAMES = {
    "none": "无", "low": "低", "medium": "中", "high": "高", "top": "顶部", "center": "居中",
    "bottom": "底部", "multiple": "多区域", "news_headline": "新闻标题", "question": "提问",
    "number_fact": "数字事实", "emotional_quote": "情绪引语", "call_to_action": "行动指令",
    "identity_label": "身份标签", "benefit_promise": "利益承诺", "other": "其他", "person": "人物",
    "news_scene": "新闻现场", "object": "物体", "scenery": "风景", "screenshot": "截图", "graphic": "图形设计",
    "mixed": "混合", "unknown": "未知", "close_up": "近景", "wide": "远景", "split": "分屏",
    "collage": "拼贴", "warm": "暖色", "cool": "冷色", "neutral": "中性", "dark": "偏暗",
    "bright": "明亮", "positive": "积极", "negative": "消极", "tense": "紧张", "news": "新闻",
    "documentary": "纪实", "portrait": "人物肖像", "poster": "海报", "product": "产品", "true": "有", "false": "无",
    "0": "无人", "1": "1人", "2": "2人", "many": "多人", "0字": "0字", "1-8字": "1-8字",
    "9-16字": "9-16字", "17字以上": "17字以上",
}


def _cover_hash(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()


def _round(value: float, digits: int = 4) -> float:
    return round(float(value), digits)


def _normalize_label(raw: Mapping[str, Any], aweme_id: str) -> dict[str, Any]:
    result: dict[str, Any] = {"aweme_id": aweme_id}
    result["ocr_text"] = str(raw.get("ocr_text") or "").strip()[:500]
    for key, allowed in ENUMS.items():
        value = str(raw.get(key) or "unknown").strip().lower()
        result[key] = value if value in allowed else ("none" if key.startswith("text_") else "unknown")
    styles = raw.get("visual_style") if isinstance(raw.get("visual_style"), list) else []
    result["visual_style"] = list(dict.fromkeys(str(value).lower() for value in styles if str(value).lower() in VISUAL_STYLES))[:4] or ["other"]
    for key in ("face_closeup", "has_logo", "has_subtitle_bar", "has_number"):
        result[key] = bool(raw.get(key))
    try:
        result["confidence"] = _round(max(0.0, min(1.0, float(raw.get("confidence") or 0.0))), 3)
    except (TypeError, ValueError):
        result["confidence"] = 0.0
    return result


def _ocr_length_group(text: str) -> str:
    length = len("".join(str(text or "").split()))
    if length == 0:
        return "0字"
    if length <= 8:
        return "1-8字"
    if length <= 16:
        return "9-16字"
    return "17字以上"


def compute_cover_statistics(samples: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate vision tags with Python; no model arithmetic is trusted."""
    if not samples:
        return {"sample_count": 0, "overall_hit_rate": 0.0, "dimensions": []}
    overall_hit_rate = sum(1 for row in samples if row.get("is_hit")) / len(samples)
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    scalar_dimensions = (
        "subject_type", "composition", "text_density", "text_position", "text_hook", "color_tone",
        "brightness", "contrast", "information_density", "emotion", "face_closeup", "has_logo",
        "has_subtitle_bar", "has_number",
    )
    for row in samples:
        labels = row.get("labels") if isinstance(row.get("labels"), Mapping) else {}
        for dimension in scalar_dimensions:
            value = str(labels.get(dimension, "unknown")).lower()
            grouped[(dimension, value)].append(row)
        for value in labels.get("visual_style", []) if isinstance(labels.get("visual_style"), list) else []:
            grouped[("visual_style", str(value))].append(row)
        grouped[("ocr_length", _ocr_length_group(str(labels.get("ocr_text") or "")))].append(row)

    dimensions = []
    for (dimension, label), rows in grouped.items():
        hit_rate = sum(1 for row in rows if row.get("is_hit")) / len(rows)
        interactions = [int(row.get("interaction") or 0) for row in rows]
        dimensions.append({
            "dimension": dimension,
            "dimension_name": DIMENSION_NAMES.get(dimension, dimension),
            "label": label,
            "label_name": VALUE_NAMES.get(label, label),
            "count": len(rows),
            "ratio": _round(len(rows) / len(samples)),
            "avg_interaction": _round(statistics.fmean(interactions), 2) if interactions else 0.0,
            "hit_rate": _round(hit_rate),
            "lift": _round(hit_rate / overall_hit_rate, 2) if overall_hit_rate else 0.0,
        })
    dimensions.sort(key=lambda row: (row["dimension"], -row["count"], -row["avg_interaction"], row["label"]))
    return {
        "sample_count": len(samples),
        "hit_sample_count": sum(1 for row in samples if row.get("is_hit")),
        "normal_sample_count": sum(1 for row in samples if not row.get("is_hit")),
        "overall_hit_rate": _round(overall_hit_rate),
        "dimensions": dimensions,
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
        """Download a sampled cover server-side to avoid provider-side hotlink 403s."""
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
            raise AIServiceError("No sampled cover could be downloaded.", code="invalid_media")
        response = await self._model_service.generate_multimodal_json(
            system_prompt=COVER_VISION_SYSTEM_PROMPT,
            user_prompt="请按图片ID逐张执行OCR并输出结构化视觉标签。",
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

    async def analyze_samples(self, samples: list[Mapping[str, Any]]) -> dict[str, Any]:
        requested_count = len(samples)
        eligible = [row for row in samples if str(row.get("cover_url") or "").strip()]
        status = self.get_status()
        if not status.get("configured"):
            return {
                "status": "not_configured",
                "requested_sample_count": requested_count,
                "sample_count": 0,
                "missing_cover_count": requested_count - len(eligible),
                "model": status.get("model") or "",
                "statistics": compute_cover_statistics([]),
                "samples": [],
            }
        if not eligible:
            return {
                "status": "no_covers",
                "requested_sample_count": requested_count,
                "sample_count": 0,
                "missing_cover_count": requested_count,
                "model": status.get("model") or "",
                "statistics": compute_cover_statistics([]),
                "samples": [],
            }

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
        for offset in range(0, len(uncached), 4):
            batch = uncached[offset:offset + 4]
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

        labeled_samples = []
        for row in eligible:
            aweme_id = str(row["aweme_id"])
            labels = labels_by_id.get(aweme_id)
            if labels is None:
                continue
            labeled_samples.append({
                "aweme_id": aweme_id,
                "title": str(row.get("title") or "")[:200],
                "cover_url": str(row.get("cover_url") or ""),
                "interaction": int(row.get("interaction") or 0),
                "is_hit": bool(row.get("is_hit")),
                "labels": labels,
                "display_tags": [
                    VALUE_NAMES.get(str(value), str(value))
                    for value in [
                        labels.get("subject_type"),
                        labels.get("text_density"),
                        labels.get("composition"),
                        *(labels.get("visual_style") or []),
                    ]
                    if value
                ][:4],
            })
        return {
            "status": "done" if len(labeled_samples) == len(eligible) else "partial",
            "requested_sample_count": requested_count,
            "sample_count": len(labeled_samples),
            "missing_cover_count": requested_count - len(eligible),
            "failed_count": len(eligible) - len(labeled_samples),
            "model": model_name,
            "prompt_version": COVER_PROMPT_VERSION,
            "statistics": compute_cover_statistics(labeled_samples),
            "samples": labeled_samples,
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
