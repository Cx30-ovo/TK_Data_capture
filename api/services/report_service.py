# -*- coding: utf-8 -*-
"""CSV, Excel and periodic report generation for the monitor module."""

import csv
import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional

from openpyxl import Workbook

from database.monitor_repository import monitor_repository


class ReportService:
    def __init__(self, output_root: Optional[Path] = None):
        self.output_root = output_root or (Path(__file__).parent.parent.parent / "output")
        self.export_dir = self.output_root / "exports"
        self.report_dir = self.output_root / "reports"

    def _ensure_dirs(self) -> None:
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _account_suffix(sec_user_id: Optional[str]) -> str:
        return hashlib.sha1(sec_user_id.encode("utf-8")).hexdigest()[:8] if sec_user_id else "all"

    @staticmethod
    def _write_csv(path: Path, headers: list[str], rows: Iterable[list]) -> None:
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            writer.writerows(rows)

    @staticmethod
    def _write_xlsx(path: Path, headers: list[str], rows: Iterable[list], title: str = "Data") -> None:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = title[:31]
        sheet.append(headers)
        for row in rows:
            sheet.append(row)
        workbook.save(path)

    async def export_posts(
        self,
        file_format: str = "csv",
        limit: int = 10000,
        sec_user_id: Optional[str] = None,
    ) -> Path:
        self._ensure_dirs()
        posts = await monitor_repository.list_posts(limit=limit, sec_user_id=sec_user_id)
        snapshots = await monitor_repository.list_snapshots(limit=100000, sec_user_id=sec_user_id)

        latest_snapshots: dict[str, object] = {}
        snapshot_counts: dict[str, int] = {}
        for snapshot in sorted(snapshots, key=lambda item: item.captured_at):
            latest_snapshots[snapshot.aweme_id] = snapshot
            snapshot_counts[snapshot.aweme_id] = snapshot_counts.get(snapshot.aweme_id, 0) + 1

        headers = [
            "作品ID", "发布时间", "首次发现时间", "标题", "正文", "规范URL",
            "快照数量", "最新点赞", "最新收藏", "最新评论", "最新分享",
        ]
        rows = []
        for post in posts:
            latest = latest_snapshots.get(post.aweme_id)
            rows.append([
                post.aweme_id,
                datetime.fromtimestamp(post.create_time).strftime("%Y-%m-%d %H:%M:%S"),
                datetime.fromtimestamp(post.first_seen_at).strftime("%Y-%m-%d %H:%M:%S"),
                post.title or "",
                post.desc or "",
                post.canonical_url,
                snapshot_counts.get(post.aweme_id, 0),
                latest.liked_count if latest else 0,
                latest.collected_count if latest else 0,
                latest.comment_count if latest else 0,
                latest.share_count if latest else 0,
            ])

        suffix = "xlsx" if file_format == "xlsx" else "csv"
        path = self.export_dir / f"douyin_posts_{self._account_suffix(sec_user_id)}_{datetime.now().strftime('%Y-%m-%d')}.{suffix}"
        if suffix == "xlsx":
            self._write_xlsx(path, headers, rows, "作品列表")
        else:
            self._write_csv(path, headers, rows)
        return path

    async def export_post_snapshots(
        self,
        aweme_id: str,
        file_format: str = "csv",
        sec_user_id: Optional[str] = None,
    ) -> Path:
        return await self.export_snapshots([aweme_id], file_format=file_format, sec_user_id=sec_user_id)

    async def export_snapshots(
        self,
        aweme_ids: list[str],
        file_format: str = "csv",
        sec_user_id: Optional[str] = None,
    ) -> Path:
        self._ensure_dirs()
        unique_ids = list(dict.fromkeys(item.strip() for item in aweme_ids if item.strip()))
        if not unique_ids:
            raise ValueError("At least one post must be selected.")

        headers = [
            "作品ID", "标题", "阶段", "计划时间", "实际观测时间",
            "实际发布后年龄(秒)", "点赞", "收藏", "评论", "分享",
        ]
        rows = []
        for aweme_id in unique_ids:
            post = await monitor_repository.get_post(aweme_id)
            if post is None:
                continue
            if sec_user_id and post.sec_user_id != sec_user_id:
                continue
            snapshots = await monitor_repository.list_snapshots(aweme_id=aweme_id, limit=10000, sec_user_id=sec_user_id)
            for snapshot in sorted(snapshots, key=lambda item: item.captured_at):
                rows.append([
                    post.aweme_id,
                    post.title or "",
                    snapshot.stage,
                    datetime.fromtimestamp(snapshot.due_at).strftime("%Y-%m-%d %H:%M:%S"),
                    datetime.fromtimestamp(snapshot.captured_at).strftime("%Y-%m-%d %H:%M:%S"),
                    snapshot.actual_age_seconds,
                    snapshot.liked_count,
                    snapshot.collected_count,
                    snapshot.comment_count,
                    snapshot.share_count,
                ])

        if not rows:
            raise ValueError("No snapshots found for the selected posts.")

        suffix = "xlsx" if file_format == "xlsx" else "csv"
        suffix_name = unique_ids[0] if len(unique_ids) == 1 else f"selected_{len(unique_ids)}"
        path = self.export_dir / f"douyin_snapshots_{self._account_suffix(sec_user_id)}_{suffix_name}_{datetime.now().strftime('%Y-%m-%d')}.{suffix}"
        if suffix == "xlsx":
            self._write_xlsx(path, headers, rows, "快照历史")
        else:
            self._write_csv(path, headers, rows)
        return path

    @staticmethod
    def _period_start(period: str) -> datetime:
        now = datetime.now()
        if period == "daily":
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        if period == "weekly":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return start - timedelta(days=start.weekday())
        if period == "monthly":
            return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        raise ValueError("period must be daily, weekly or monthly")

    async def generate_report(self, period: str = "daily", sec_user_id: Optional[str] = None) -> dict:
        self._ensure_dirs()
        start = self._period_start(period)
        start_ts = int(start.timestamp())
        now = datetime.now()
        posts = await monitor_repository.list_posts(limit=10000, sec_user_id=sec_user_id)
        snapshots = await monitor_repository.list_snapshots(limit=100000, sec_user_id=sec_user_id)
        jobs = await monitor_repository.list_jobs(limit=100000, sec_user_id=sec_user_id)

        new_posts = [post for post in posts if post.first_seen_at >= start_ts]
        period_snapshots = [snapshot for snapshot in snapshots if snapshot.captured_at >= start_ts]
        abnormal_jobs = [
            job for job in jobs
            if job["status"] in ("failed", "missed") and job["due_at"] >= start_ts
        ]

        post_map = {post.aweme_id: post for post in posts}
        snapshots_by_post: dict[str, list] = {}
        for snapshot in sorted(period_snapshots, key=lambda item: item.actual_age_seconds):
            snapshots_by_post.setdefault(snapshot.aweme_id, []).append(snapshot)

        growth_rows = []
        best_rows = []
        for aweme_id, items in snapshots_by_post.items():
            first = items[0]
            latest = items[-1]
            growth = {
                "aweme_id": aweme_id,
                "title": post_map[aweme_id].title if aweme_id in post_map else aweme_id,
                "likes": latest.liked_count - first.liked_count,
                "collections": latest.collected_count - first.collected_count,
                "comments": latest.comment_count - first.comment_count,
                "shares": latest.share_count - first.share_count,
                "latest": latest,
            }
            growth_rows.append(growth)
            best_rows.append(growth)

        growth_rows.sort(key=lambda item: item["likes"] + item["collections"] + item["comments"] + item["shares"], reverse=True)
        best_rows.sort(key=lambda item: item["latest"].liked_count + item["latest"].collected_count * 2 + item["latest"].comment_count * 3, reverse=True)

        period_label = {"daily": "日报", "weekly": "周报", "monthly": "月报"}[period]
        lines = [
            f"# 抖音监控{period_label}",
            "",
            f"- 生成时间：{now.strftime('%Y-%m-%d %H:%M:%S')}",
            f"- 统计开始：{start.strftime('%Y-%m-%d %H:%M:%S')}",
            f"- 新增作品：{len(new_posts)}",
            f"- 新增快照：{len(period_snapshots)}",
            f"- 异常任务：{len(abnormal_jobs)}",
            "",
            "## 新增作品",
            "",
            "| 发布时间 | 作品ID | 标题 |",
            "|---|---|---|",
        ]
        lines.extend([
            f"| {datetime.fromtimestamp(post.create_time).strftime('%Y-%m-%d %H:%M:%S')} | {post.aweme_id} | {post.title or ''} |"
            for post in new_posts
        ] or ["| - | - | 无 |"])

        lines.extend([
            "",
            "## 互动增长",
            "",
            "| 作品 | 点赞增长 | 收藏增长 | 评论增长 | 分享增长 |",
            "|---|---:|---:|---:|---:|",
        ])
        lines.extend([
            f"| {row['title']} | {row['likes']} | {row['collections']} | {row['comments']} | {row['shares']} |"
            for row in growth_rows[:20]
        ] or ["| 无 | 0 | 0 | 0 | 0 |"])

        lines.extend([
            "",
            "## 高表现作品",
            "",
            "| 作品 | 最新点赞 | 最新收藏 | 最新评论 | 最新分享 |",
            "|---|---:|---:|---:|---:|",
        ])
        lines.extend([
            f"| {row['title']} | {row['latest'].liked_count} | {row['latest'].collected_count} | {row['latest'].comment_count} | {row['latest'].share_count} |"
            for row in best_rows[:10]
        ] or ["| 无 | 0 | 0 | 0 | 0 |"])

        lines.extend([
            "",
            "## 异常任务",
            "",
            "| 状态 | 阶段 | 作品 | 计划时间 | 原因 |",
            "|---|---|---|---|---|",
        ])
        lines.extend([
            f"| {job['status']} | {job['stage']} | {job['title']} | {datetime.fromtimestamp(job['due_at']).strftime('%Y-%m-%d %H:%M:%S')} | {job.get('miss_reason') or job.get('last_error') or ''} |"
            for job in abnormal_jobs[:50]
        ] or ["| - | - | - | - | 无 |"])

        content = "\n".join(lines) + "\n"
        filename = f"douyin_{period}_{self._account_suffix(sec_user_id)}_{now.strftime('%Y-%m-%d_%H%M%S')}.md"
        path = self.report_dir / filename
        path.write_text(content, encoding="utf-8")
        json_path = path.with_suffix(".json")
        json_path.write_text(json.dumps({
            "period": period,
            "sec_user_id": sec_user_id,
            "generated_at": now.isoformat(timespec="seconds"),
            "new_posts": len(new_posts),
            "new_snapshots": len(period_snapshots),
            "abnormal_jobs": len(abnormal_jobs),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"filename": filename, "content": content, "path": str(path)}

    def list_reports(self, sec_user_id: Optional[str] = None) -> list[dict]:
        self._ensure_dirs()
        account_suffix = self._account_suffix(sec_user_id) if sec_user_id else None
        reports = []
        for path in self.report_dir.glob("*.md"):
            is_legacy_report = bool(re.match(r"^douyin_(daily|weekly|monthly)_\d{4}-", path.name))
            if account_suffix and f"_{account_suffix}_" not in path.name and not is_legacy_report:
                continue
            stat = path.stat()
            reports.append({
                "name": path.name,
                "size": stat.st_size,
                "modified_at": int(stat.st_mtime),
            })
        return sorted(reports, key=lambda item: item["modified_at"], reverse=True)

    def resolve_report(self, name: str) -> Path:
        if Path(name).name != name:
            raise ValueError("Invalid report name.")
        path = self.report_dir / name
        if not path.exists() or path.suffix.lower() not in (".md", ".json"):
            raise ValueError("Report not found.")
        return path

    def delete_report(self, name: str) -> bool:
        if Path(name).name != name:
            raise ValueError("Invalid report name.")
        path = self.report_dir / name
        if path.suffix.lower() not in (".md", ".json"):
            raise ValueError("Report not found.")
        if not path.exists():
            return False
        path.unlink(missing_ok=True)
        if path.suffix.lower() == ".md":
            path.with_suffix(".json").unlink(missing_ok=True)
        return True


report_service = ReportService()
