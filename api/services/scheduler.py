# -*- coding: utf-8 -*-
"""Daily scheduler for MediaCrawler WebUI tasks."""

import asyncio
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from ..schemas import CrawlerStartRequest, SchedulerConfigRequest
from .crawler_manager import crawler_manager

_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class SchedulerService:
    """Run the configured crawler once at each configured HH:MM time."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None
        self._file = Path(__file__).parent.parent.parent / "data" / "scheduled_tasks.json"
        self.enabled = False
        self.times: list[str] = []
        self.crawler_config: Optional[CrawlerStartRequest] = None
        self.last_run_at: Optional[datetime] = None
        self.last_result: Optional[str] = None
        self._last_triggered_key: Optional[str] = None

    def _normalize_times(self, times: list[str]) -> list[str]:
        normalized = []
        for value in times:
            value = str(value).strip()
            if not value:
                continue
            if not _TIME_RE.match(value):
                raise ValueError(f"Invalid scheduled time: {value}. Use HH:MM, for example 14:00.")
            if value not in normalized:
                normalized.append(value)
        return sorted(normalized)

    def _load(self) -> None:
        if not self._file.exists():
            return
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            request = SchedulerConfigRequest.model_validate(data)
            self.enabled = request.enabled
            self.times = self._normalize_times(request.times)
            self.crawler_config = request.crawler
        except Exception:
            self.enabled = False
            self.times = []
            self.crawler_config = None

    def _save(self) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        config = None
        if self.crawler_config:
            # Do not persist cookie credentials in the scheduler file.
            config = self.crawler_config.model_copy(update={"cookies": ""}).model_dump(mode="json")
        payload = {"enabled": self.enabled, "times": self.times, "crawler": config}
        self._file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _next_run_at(self) -> Optional[datetime]:
        if not self.enabled or not self.times:
            return None
        now = datetime.now()
        candidates = []
        for value in self.times:
            hour, minute = (int(part) for part in value.split(":"))
            candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate <= now:
                candidate += timedelta(days=1)
            candidates.append(candidate)
        return min(candidates) if candidates else None

    def get_status(self) -> dict:
        next_run = self._next_run_at()
        return {
            "enabled": self.enabled,
            "times": self.times,
            "next_run_at": next_run.isoformat(timespec="seconds") if next_run else None,
            "last_run_at": self.last_run_at.isoformat(timespec="seconds") if self.last_run_at else None,
            "last_result": self.last_result,
            "running": bool(crawler_manager.process and crawler_manager.process.poll() is None),
        }

    async def start(self) -> None:
        self._load()
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def update(self, request: SchedulerConfigRequest) -> dict:
        times = self._normalize_times(request.times)
        if request.enabled and not times:
            raise ValueError("At least one scheduled time is required when scheduling is enabled.")
        async with self._lock:
            self.enabled = request.enabled
            self.times = times
            self.crawler_config = request.crawler
            self._last_triggered_key = None
            self._save()
        await crawler_manager.add_log(
            f"[Scheduler] Saved schedule: enabled={self.enabled}, times={self.times}",
            "success" if self.enabled else "info",
        )
        return self.get_status()

    async def disable(self) -> dict:
        async with self._lock:
            self.enabled = False
            self._save()
        await crawler_manager.add_log("[Scheduler] Schedule disabled", "info")
        return self.get_status()

    async def _loop(self) -> None:
        while True:
            try:
                await self._check_due()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await crawler_manager.add_log(f"[Scheduler] Error: {exc}", "error")
            await asyncio.sleep(20)

    async def _check_due(self) -> None:
        if not self.enabled or not self.times or not self.crawler_config:
            return
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        if current_time not in self.times:
            return
        trigger_key = f"{now.strftime('%Y-%m-%d')} {current_time}"
        if self._last_triggered_key == trigger_key:
            return
        self._last_triggered_key = trigger_key

        async with self._lock:
            if crawler_manager.process and crawler_manager.process.poll() is None:
                self.last_result = "skipped: crawler already running"
                await crawler_manager.add_log(
                    f"[Scheduler] {current_time} skipped because a crawler task is already running",
                    "warning",
                )
                return
            self.last_run_at = now
            ok = await crawler_manager.start(self.crawler_config)
            self.last_result = "started" if ok else "failed to start"
            await crawler_manager.add_log(
                f"[Scheduler] {current_time} trigger result: {self.last_result}",
                "success" if ok else "error",
            )


scheduler_service = SchedulerService()
