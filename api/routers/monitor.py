# -*- coding: utf-8 -*-
"""API routes for the single-account monitor module."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from database.monitor_repository import monitor_repository

from ..schemas import MonitorAccountConfigRequest, MonitorAccountUpdateRequest, MonitorAlertStatusRequest
from ..services.monitor_service import monitor_service
from ..services.report_service import report_service
from ..services.analytics_service import analytics_service

router = APIRouter(prefix="/monitor", tags=["monitor"])


def _serialize_account(account) -> dict:
    return {
        "id": account.id,
        "platform": account.platform,
        "sec_user_id": account.sec_user_id,
        "display_name": account.display_name or account.sec_user_id,
        "profile_url": account.profile_url,
        "enabled": account.enabled,
        "discover_interval_minutes": account.discover_interval_minutes,
        "last_discovered_at": account.last_discovered_at,
        "created_at": account.created_at,
        "updated_at": account.updated_at,
    }


async def _resolve_account_sec_user_id(account_id: Optional[int], all_accounts: bool = False) -> Optional[str]:
    if all_accounts:
        return None
    account = (
        await monitor_repository.get_monitored_account_by_id(account_id)
        if account_id is not None
        else await monitor_repository.get_enabled_monitored_account()
    )
    return account.sec_user_id if account else None


@router.get("/accounts")
async def list_monitor_accounts(include_disabled: bool = True):
    accounts = await monitor_repository.list_monitored_accounts(include_disabled=include_disabled)
    return {"accounts": [_serialize_account(account) for account in accounts]}


@router.get("/accounts/comparison")
async def compare_monitor_accounts(limit: int = 100):
    return await monitor_service.get_account_comparison(limit=limit)


@router.post("/accounts")
async def create_monitor_account(request: MonitorAccountConfigRequest):
    account = await monitor_repository.upsert_monitored_account(
        sec_user_id=request.sec_user_id,
        display_name=request.display_name,
        profile_url=request.profile_url,
        enabled=request.enabled,
        discover_interval_minutes=request.discover_interval_minutes,
    )
    return _serialize_account(account)


@router.put("/accounts/{account_id}")
async def update_monitor_account(account_id: int, request: MonitorAccountUpdateRequest):
    account = await monitor_repository.update_monitored_account(
        account_id=account_id,
        sec_user_id=request.sec_user_id,
        display_name=request.display_name,
        profile_url=request.profile_url,
        enabled=request.enabled,
        discover_interval_minutes=request.discover_interval_minutes,
    )
    if account is None:
        raise HTTPException(status_code=404, detail=f"Monitor account not found: {account_id}")
    return _serialize_account(account)


@router.delete("/accounts/{account_id}")
async def delete_monitor_account(account_id: int):
    deleted = await monitor_repository.delete_monitored_account(account_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Monitor account not found: {account_id}")
    return {"status": "ok", "account_id": account_id, "data_retained": True}


@router.post("/accounts/{account_id}/discover")
async def discover_monitor_account(account_id: int):
    account = await monitor_repository.get_monitored_account_by_id(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"Monitor account not found: {account_id}")
    return await monitor_service.discover_account(sec_user_id=account.sec_user_id)


@router.get("/status")
async def get_monitor_status(account_id: Optional[int] = None, all_accounts: bool = False):
    account = (
        await monitor_repository.get_monitored_account_by_id(account_id)
        if account_id is not None and not all_accounts
        else None if all_accounts
        else await monitor_repository.get_enabled_monitored_account()
    )
    jobs = await monitor_repository.get_job_counts(sec_user_id=account.sec_user_id if account else None)
    return {
        "enabled": account is not None,
        "account": _serialize_account(account) if account else None,
        "jobs": jobs,
        "loop_running": monitor_service.is_running,
    }


@router.post("/config")
async def save_monitor_config(request: MonitorAccountConfigRequest):
    account = await monitor_repository.upsert_monitored_account(
        sec_user_id=request.sec_user_id,
        display_name=request.display_name,
        profile_url=request.profile_url,
        enabled=request.enabled,
        discover_interval_minutes=request.discover_interval_minutes,
    )
    return _serialize_account(account)


@router.post("/discover")
async def run_monitor_discovery(sec_user_id: Optional[str] = None):
    return await monitor_service.discover_account(sec_user_id=sec_user_id)


@router.post("/snapshots/run-due")
async def run_due_snapshots(limit: int = 50):
    return await monitor_service.run_due_snapshots(limit=limit)


@router.get("/dashboard")
async def get_monitor_dashboard(limit: int = 100, account_id: Optional[int] = None, all_accounts: bool = False):
    return await monitor_service.get_dashboard_data(limit=limit, account_id=account_id, all_accounts=all_accounts)


@router.get("/overview")
async def get_monitor_overview(account_id: Optional[int] = None, all_accounts: bool = False):
    return await monitor_service.get_overview_data(account_id=account_id, all_accounts=all_accounts)


@router.get("/jobs")
async def list_monitor_jobs(status: Optional[str] = None, limit: int = 300, account_id: Optional[int] = None, all_accounts: bool = False):
    return await monitor_service.list_jobs(status=status, limit=limit, account_id=account_id, all_accounts=all_accounts)


@router.post("/jobs/{job_id}/retry")
async def retry_monitor_job(job_id: int):
    try:
        return await monitor_service.retry_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/jobs/retry-failed")
async def retry_failed_monitor_jobs(job_ids: Optional[str] = None):
    try:
        parsed_ids = [int(item) for item in job_ids.split(",") if item.strip()] if job_ids else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="job_ids must be a comma-separated list of integers") from exc
    return await monitor_service.retry_failed_jobs(job_ids=parsed_ids)


@router.get("/alerts")
async def list_monitor_alerts(status: Optional[str] = None, limit: int = 200, account_id: Optional[int] = None, all_accounts: bool = False):
    return await monitor_service.list_alerts(status=status, limit=limit, account_id=account_id, all_accounts=all_accounts)


@router.post("/alerts/status")
async def update_monitor_alerts_status(request: MonitorAlertStatusRequest):
    try:
        return await monitor_service.update_alerts_status(
            alert_ids=request.alert_ids,
            status=request.status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/alerts/{alert_id}/read")
async def mark_monitor_alert_read(alert_id: int):
    try:
        return await monitor_service.mark_alert_read(alert_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/alerts/read-all")
async def mark_all_monitor_alerts_read(account_id: Optional[int] = None, all_accounts: bool = False):
    return await monitor_service.mark_all_alerts_read(account_id=account_id, all_accounts=all_accounts)


@router.get("/health")
async def get_monitor_health(account_id: Optional[int] = None, all_accounts: bool = False):
    return await monitor_service.get_health_data(account_id=account_id, all_accounts=all_accounts)


@router.get("/analytics")
async def get_monitor_analytics(limit: int = 100, account_id: Optional[int] = None, all_accounts: bool = False):
    return await analytics_service.get_data(limit=limit, sec_user_id=await _resolve_account_sec_user_id(account_id, all_accounts))


@router.get("/export/posts")
async def export_monitor_posts(file_format: str = Query("csv", alias="format"), account_id: Optional[int] = None, all_accounts: bool = False):
    try:
        path = await report_service.export_posts(file_format=file_format, sec_user_id=await _resolve_account_sec_user_id(account_id, all_accounts))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(path, filename=path.name)


@router.get("/export/post/{aweme_id}")
async def export_monitor_post_snapshots(aweme_id: str, file_format: str = Query("csv", alias="format"), account_id: Optional[int] = None, all_accounts: bool = False):
    try:
        path = await report_service.export_post_snapshots(aweme_id=aweme_id, file_format=file_format, sec_user_id=await _resolve_account_sec_user_id(account_id, all_accounts))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, filename=path.name)


@router.get("/export/snapshots")
async def export_monitor_selected_snapshots(
    aweme_ids: str,
    file_format: str = Query("csv", alias="format"),
    account_id: Optional[int] = None,
    all_accounts: bool = False,
):
    try:
        ids = [item.strip() for item in aweme_ids.split(",") if item.strip()]
        path = await report_service.export_snapshots(ids, file_format=file_format, sec_user_id=await _resolve_account_sec_user_id(account_id, all_accounts))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(path, filename=path.name)


@router.post("/reports/generate")
async def generate_monitor_report(period: str = "daily", account_id: Optional[int] = None, all_accounts: bool = False):
    try:
        result = await report_service.generate_report(period=period, sec_user_id=await _resolve_account_sec_user_id(account_id, all_accounts))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result["download_url"] = f"/api/monitor/reports/download?name={result['filename']}"
    return result


@router.get("/reports")
async def list_monitor_reports(account_id: Optional[int] = None, all_accounts: bool = False):
    return {"reports": report_service.list_reports(sec_user_id=await _resolve_account_sec_user_id(account_id, all_accounts))}


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
