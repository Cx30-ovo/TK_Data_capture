# -*- coding: utf-8 -*-
"""API routes for the single-account monitor module."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from database.monitor_repository import monitor_repository

from ..schemas import MonitorAccountConfigRequest
from ..services.monitor_service import monitor_service
from ..services.report_service import report_service

router = APIRouter(prefix="/monitor", tags=["monitor"])


@router.get("/status")
async def get_monitor_status():
    account = await monitor_repository.get_enabled_monitored_account()
    jobs = await monitor_repository.get_job_counts()
    return {
        "enabled": account is not None,
        "account": {
            "id": account.id,
            "platform": account.platform,
            "sec_user_id": account.sec_user_id,
            "profile_url": account.profile_url,
            "discover_interval_minutes": account.discover_interval_minutes,
            "last_discovered_at": account.last_discovered_at,
        } if account else None,
        "jobs": jobs,
        "loop_running": monitor_service.is_running,
    }


@router.post("/config")
async def save_monitor_config(request: MonitorAccountConfigRequest):
    account = await monitor_repository.upsert_monitored_account(
        sec_user_id=request.sec_user_id,
        profile_url=request.profile_url,
        enabled=request.enabled,
        discover_interval_minutes=request.discover_interval_minutes,
    )
    return {
        "id": account.id,
        "platform": account.platform,
        "sec_user_id": account.sec_user_id,
        "profile_url": account.profile_url,
        "enabled": account.enabled,
        "discover_interval_minutes": account.discover_interval_minutes,
    }


@router.post("/discover")
async def run_monitor_discovery(sec_user_id: Optional[str] = None):
    return await monitor_service.discover_account(sec_user_id=sec_user_id)


@router.post("/snapshots/run-due")
async def run_due_snapshots(limit: int = 50):
    return await monitor_service.run_due_snapshots(limit=limit)


@router.get("/dashboard")
async def get_monitor_dashboard(limit: int = 100):
    return await monitor_service.get_dashboard_data(limit=limit)


@router.get("/overview")
async def get_monitor_overview():
    return await monitor_service.get_overview_data()


@router.get("/jobs")
async def list_monitor_jobs(status: Optional[str] = None, limit: int = 300):
    return await monitor_service.list_jobs(status=status, limit=limit)


@router.post("/jobs/{job_id}/retry")
async def retry_monitor_job(job_id: int):
    try:
        return await monitor_service.retry_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/alerts")
async def list_monitor_alerts(status: Optional[str] = None, limit: int = 200):
    return await monitor_service.list_alerts(status=status, limit=limit)


@router.post("/alerts/{alert_id}/read")
async def mark_monitor_alert_read(alert_id: int):
    try:
        return await monitor_service.mark_alert_read(alert_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/alerts/read-all")
async def mark_all_monitor_alerts_read():
    return await monitor_service.mark_all_alerts_read()


@router.get("/health")
async def get_monitor_health():
    return await monitor_service.get_health_data()


@router.get("/export/posts")
async def export_monitor_posts(file_format: str = Query("csv", alias="format")):
    try:
        path = await report_service.export_posts(file_format=file_format)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(path, filename=path.name)


@router.get("/export/post/{aweme_id}")
async def export_monitor_post_snapshots(aweme_id: str, file_format: str = Query("csv", alias="format")):
    try:
        path = await report_service.export_post_snapshots(aweme_id=aweme_id, file_format=file_format)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, filename=path.name)


@router.post("/reports/generate")
async def generate_monitor_report(period: str = "daily"):
    try:
        result = await report_service.generate_report(period=period)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result["download_url"] = f"/api/monitor/reports/download?name={result['filename']}"
    return result


@router.get("/reports")
async def list_monitor_reports():
    return {"reports": report_service.list_reports()}


@router.get("/reports/download")
async def download_monitor_report(name: str):
    try:
        path = report_service.resolve_report(name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, filename=path.name)


@router.delete("/reports")
async def delete_monitor_report(name: str):
    try:
        deleted = report_service.delete_report(name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "ok", "name": name, "deleted": deleted}
