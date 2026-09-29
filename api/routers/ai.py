# -*- coding: utf-8 -*-
"""API routes for cached AI content analysis."""

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query

import config
from database.ai_analysis_repository import ai_analysis_repository
from database.monitor_repository import monitor_repository

from ..schemas import AIAnalysisRequest, AICoverCandidateRequest, AITopicIdeasRequest
from ..services.ai_analysis_service import TITLE_STRATEGY_PROMPT_VERSION, ai_analysis_service
from ..services.ai_model_service import AIServiceError, ai_model_service
from ..services.cover_analysis_service import cover_analysis_service


router = APIRouter(prefix="/monitor/ai", tags=["ai"])


async def _resolve_account_sec_user_id(account_id: int) -> str:
    account = await monitor_repository.get_monitored_account_by_id(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"Monitor account not found: {account_id}")
    return account.sec_user_id


def _raise_ai_error(error: AIServiceError) -> None:
    if error.code in {"disabled", "not_configured"}:
        status_code = 503
    elif error.code == "invalid_media":
        status_code = 422
    elif error.code in {"timeout", "connection_error"}:
        status_code = 504
    elif error.code == "http_error" and error.status_code and 400 <= error.status_code < 500:
        status_code = 502
    else:
        status_code = 502
    raise HTTPException(
        status_code=status_code,
        detail={"code": error.code, "message": str(error)},
    )


def _analysis_scope(request: AIAnalysisRequest) -> dict:
    return {
        "time_range": request.time_range,
        "post_limit": request.post_limit,
    }


@router.get("/status")
async def get_ai_status():
    return {
        **ai_model_service.get_status(),
        "vision": cover_analysis_service.get_status(),
        "vision_scope": "all_valid_covers",
        "vision_batch_size": int(config.VISION_AI_BATCH_SIZE),
    }


@router.post("/analyze/topics")
async def analyze_topics(request: AIAnalysisRequest):
    sec_user_id = await _resolve_account_sec_user_id(request.account_id)
    try:
        return await ai_analysis_service.analyze_topics(
            sec_user_id=sec_user_id,
            scope=_analysis_scope(request),
            force=request.force,
        )
    except AIServiceError as exc:
        _raise_ai_error(exc)


@router.post("/analyze/lifecycle")
async def analyze_lifecycle(request: AIAnalysisRequest):
    sec_user_id = await _resolve_account_sec_user_id(request.account_id)
    try:
        return await ai_analysis_service.analyze_lifecycle(
            sec_user_id=sec_user_id,
            scope=_analysis_scope(request),
            force=request.force,
        )
    except AIServiceError as exc:
        _raise_ai_error(exc)


@router.post("/analyze/title-strategy")
async def analyze_title_strategy(request: AIAnalysisRequest):
    sec_user_id = await _resolve_account_sec_user_id(request.account_id)
    try:
        return await ai_analysis_service.analyze_title_strategy(
            sec_user_id=sec_user_id,
            scope=_analysis_scope(request),
            force=request.force,
        )
    except AIServiceError as exc:
        _raise_ai_error(exc)


@router.post("/analyze/cover-candidate")
async def analyze_cover_candidate(request: AICoverCandidateRequest):
    sec_user_id = await _resolve_account_sec_user_id(request.account_id)
    if request.reference_result_id is not None:
        reference = await ai_analysis_repository.get_result(request.reference_result_id)
    else:
        reference = await ai_analysis_repository.get_latest_result(
            sec_user_id=sec_user_id,
            analysis_type="title_strategy",
            status="done",
        )
    if reference is None or reference.analysis_type != "title_strategy" or reference.sec_user_id != sec_user_id:
        raise HTTPException(status_code=404, detail="A matching content performance report was not found.")
    serialized = ai_analysis_service.serialize_result(reference, cache_hit=True)
    result = serialized.get("result") if isinstance(serialized, dict) else None
    cover_analysis = result.get("cover_analysis") if isinstance(result, dict) else None
    if not isinstance(cover_analysis, dict) or not cover_analysis.get("sample_count"):
        raise HTTPException(status_code=409, detail="Run cover analysis before evaluating a new cover.")
    try:
        return await cover_analysis_service.evaluate_candidate(request.image_data_url, cover_analysis)
    except AIServiceError as exc:
        _raise_ai_error(exc)


@router.post("/analyze/topic-ideas")
async def analyze_topic_ideas(request: AITopicIdeasRequest):
    sec_user_id = await _resolve_account_sec_user_id(request.account_id)
    try:
        return await ai_analysis_service.analyze_topic_ideas(
            sec_user_id=sec_user_id,
            topic_result_id=request.topic_result_id,
            force=request.force,
        )
    except AIServiceError as exc:
        _raise_ai_error(exc)


@router.get("/results")
async def list_ai_results(
    account_id: Optional[int] = None,
    analysis_type: Optional[Literal["topic", "lifecycle", "topic_ideas", "title_strategy"]] = None,
    result_status: Optional[Literal["pending", "running", "done", "failed"]] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=500),
):
    sec_user_id = await _resolve_account_sec_user_id(account_id) if account_id is not None else None
    items = await ai_analysis_repository.list_results(
        sec_user_id=sec_user_id,
        analysis_type=analysis_type,
        status=result_status,
        limit=limit,
    )
    return {"results": [ai_analysis_service.serialize_result(item, cache_hit=True) for item in items]}


@router.delete("/results/title-strategy/legacy")
async def delete_legacy_title_strategy_results(account_id: int = Query(..., ge=1)):
    sec_user_id = await _resolve_account_sec_user_id(account_id)
    deleted = await ai_analysis_repository.delete_legacy_results(
        sec_user_id=sec_user_id,
        analysis_type="title_strategy",
        current_prompt_version=TITLE_STRATEGY_PROMPT_VERSION,
    )
    return {"status": "ok", "deleted": deleted}


@router.get("/results/{result_id}")
async def get_ai_result(result_id: int):
    item = await ai_analysis_repository.get_result(result_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"AI analysis result not found: {result_id}")
    return ai_analysis_service.serialize_result(item, cache_hit=True)


@router.delete("/results/{result_id}")
async def delete_ai_result(result_id: int):
    deleted = await ai_analysis_repository.delete_result(result_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"AI analysis result not found: {result_id}")
    return {"status": "ok", "result_id": result_id}


__all__ = ["router"]
