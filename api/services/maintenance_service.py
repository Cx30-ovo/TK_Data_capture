# -*- coding: utf-8 -*-
"""Background maintenance for backups and log retention."""

import asyncio
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import config

from .crawler_manager import crawler_manager


class MaintenanceService:
    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self.output_root = Path(__file__).parent.parent.parent / "output"
        self.backup_dir = self.output_root / "backups"
        self.db_path = Path(config.SQLITE_DB_PATH)

    @property
    def is_running(self) -> bool:
        return bool(self._task and not self._task.done())

    async def start(self) -> None:
        if not self.is_running:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await crawler_manager.add_log(f"[Maintenance] Error: {exc}", "error")
            await asyncio.sleep(max(30, int(config.MAINTENANCE_CHECK_INTERVAL_SECONDS)))

    def _latest_backup(self) -> Optional[Path]:
        if not self.backup_dir.exists():
            return None
        files = sorted(self.backup_dir.glob("sqlite_tables_*.db"), key=lambda path: path.stat().st_mtime, reverse=True)
        return files[0] if files else None

    def _backup_due(self) -> bool:
        latest = self._latest_backup()
        if latest is None:
            return True
        age = datetime.now() - datetime.fromtimestamp(latest.stat().st_mtime)
        return age >= timedelta(hours=max(1, int(config.BACKUP_INTERVAL_HOURS)))

    @staticmethod
    def _copy_sqlite(source: Path, destination: Path) -> None:
        with sqlite3.connect(source) as source_connection:
            with sqlite3.connect(destination) as destination_connection:
                source_connection.backup(destination_connection)

    def _cleanup_backups(self) -> int:
        if not self.backup_dir.exists():
            return 0
        cutoff = datetime.now() - timedelta(days=max(1, int(config.BACKUP_RETENTION_DAYS)))
        removed = 0
        for path in self.backup_dir.glob("sqlite_tables_*.db"):
            if datetime.fromtimestamp(path.stat().st_mtime) < cutoff:
                path.unlink(missing_ok=True)
                removed += 1
        return removed

    def _cleanup_logs(self) -> int:
        cutoff = datetime.now() - timedelta(days=max(1, int(config.LOG_RETENTION_DAYS)))
        removed = 0
        if not self.output_root.exists():
            return removed
        for path in self.output_root.glob("*.log.*"):
            if datetime.fromtimestamp(path.stat().st_mtime) < cutoff:
                path.unlink(missing_ok=True)
                removed += 1
        return removed

    async def run_once(self) -> dict:
        result = {"backup": None, "removed_backups": 0, "removed_logs": 0}
        if config.ENABLE_AUTO_BACKUP and self.db_path.exists() and self._backup_due():
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            destination = self.backup_dir / f"sqlite_tables_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            await asyncio.to_thread(self._copy_sqlite, self.db_path, destination)
            result["backup"] = str(destination)
            await crawler_manager.add_log(f"[Maintenance] SQLite backup created: {destination.name}", "success")

        result["removed_backups"] = self._cleanup_backups()
        result["removed_logs"] = self._cleanup_logs()
        if result["removed_backups"] or result["removed_logs"]:
            await crawler_manager.add_log(
                f"[Maintenance] Removed old files: backups={result['removed_backups']}, logs={result['removed_logs']}",
                "info",
            )
        return result


maintenance_service = MaintenanceService()
