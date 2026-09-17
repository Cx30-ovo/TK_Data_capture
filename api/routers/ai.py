# -*- coding: utf-8 -*-
"""API routes for AI topic and lifecycle analysis."""

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query

from database.ai_analysis_repository import ai_analysis_repository
from database.monitor_repository import monitor_repository

from ..schemas import AIAnalysisRequest, AITopicIdeasRequest
from ..services.ai_analysis_service import ai_analysis_service
from ..services.ai_model_service import AIServiceError, ai_model_service


router = APIRouter(prefix="/monitor/ai", tags=["ai"])


async def _resolve_account_sec_user_id(account_id: int) -> str:
    account = await monitor_repository.get_monitored_account_by_id(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"Monitor account not found: {account_id}")
    return account.sec_user_id


def _raise_ai_error(error: AIServiceError) -> None:
    if error.code in {"disabled", "not_configured"}:
        status_code = 503
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
    return ai_model_service.get_status()


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
    analysis_type: Optional[Literal["topic", "lifecycle", "topic_ideas"]] = None,
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
