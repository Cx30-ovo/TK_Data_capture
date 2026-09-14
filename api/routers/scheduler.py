# -*- coding: utf-8 -*-
"""Scheduled crawler API routes."""

from fastapi import APIRouter, HTTPException

from ..schemas import SchedulerConfigRequest, SchedulerStatusResponse
from ..services import scheduler_service

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.get("/status", response_model=SchedulerStatusResponse)
async def get_scheduler_status():
    return scheduler_service.get_status()


@router.post("/config", response_model=SchedulerStatusResponse)
async def update_scheduler_config(request: SchedulerConfigRequest):
    try:
        return await scheduler_service.update(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/disable", response_model=SchedulerStatusResponse)
async def disable_scheduler():
    return await scheduler_service.disable()
