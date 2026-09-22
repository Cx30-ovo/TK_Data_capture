# -*- coding: utf-8 -*-
"""Persistence and cache helpers for AI analysis results."""

import json
import time
from typing import Any, Mapping, Optional

from sqlalchemy import or_, select

from .db_session import get_monitor_session
from .models import AIAnalysisResult, CoverVisionLabel


ANALYSIS_TYPES = {"topic", "lifecycle", "topic_ideas", "title_strategy"}
ANALYSIS_STATUSES = {"pending", "running", "done", "failed"}


def _now_seconds() -> int:
    return int(time.time())


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


class AIAnalysisRepository:
    """CRUD helpers for cached AI analysis results."""

    async def get_result(self, result_id: int) -> Optional[AIAnalysisResult]:
        async with get_monitor_session() as session:
            return await session.get(AIAnalysisResult, result_id)

    async def get_cover_label(
        self,
        *,
        aweme_id: str,
        cover_hash: str,
        model_name: str,
        prompt_version: str,
        platform: str = "dy",
    ) -> Optional[dict[str, Any]]:
        stmt = select(CoverVisionLabel).where(
            CoverVisionLabel.platform == platform,
            CoverVisionLabel.aweme_id == aweme_id,
            CoverVisionLabel.cover_hash == cover_hash,
            CoverVisionLabel.model_name == model_name,
            CoverVisionLabel.prompt_version == prompt_version,
        )
        async with get_monitor_session() as session:
            item = (await session.execute(stmt)).scalar_one_or_none()
            if item is None:
                return None
            try:
                value = json.loads(item.labels_json)
            except (TypeError, json.JSONDecodeError):
                return None
            return value if isinstance(value, dict) else None

    async def upsert_cover_label(
        self,
        *,
        aweme_id: str,
        cover_hash: str,
        model_name: str,
        prompt_version: str,
        labels: Mapping[str, Any],
        platform: str = "dy",
    ) -> CoverVisionLabel:
        now = _now_seconds()
        stmt = select(CoverVisionLabel).where(
            CoverVisionLabel.platform == platform,
            CoverVisionLabel.aweme_id == aweme_id,
            CoverVisionLabel.cover_hash == cover_hash,
            CoverVisionLabel.model_name == model_name,
            CoverVisionLabel.prompt_version == prompt_version,
        )
        async with get_monitor_session() as session:
            item = (await session.execute(stmt)).scalar_one_or_none()
            if item is None:
                item = CoverVisionLabel(
                    platform=platform,
                    aweme_id=aweme_id,
                    cover_hash=cover_hash,
                    model_name=model_name,
                    prompt_version=prompt_version,
                    created_at=now,
                    updated_at=now,
                    labels_json="{}",
                )
                session.add(item)
            item.labels_json = _json_dumps(dict(labels))
            item.updated_at = now
            await session.flush()
            return item

    @staticmethod
    def _cache_filters(
        *,
        platform: str,
        sec_user_id: str,
        analysis_type: str,
        scope_key: str,
        input_hash: str,
        provider: str,
        model_name: str,
        prompt_version: str,
    ) -> list:
        return [
            AIAnalysisResult.platform == platform,
            AIAnalysisResult.sec_user_id == sec_user_id,
            AIAnalysisResult.analysis_type == analysis_type,
            AIAnalysisResult.scope_key == scope_key,
            AIAnalysisResult.input_hash == input_hash,
            AIAnalysisResult.provider == provider,
            AIAnalysisResult.model_name == model_name,
            AIAnalysisResult.prompt_version == prompt_version,
        ]

    async def get_cached_result(
        self,
        *,
        sec_user_id: str,
        analysis_type: str,
        scope_key: str,
        input_hash: str,
        provider: str,
        model_name: str,
        prompt_version: str,
        platform: str = "dy",
        now: Optional[int] = None,
    ) -> Optional[AIAnalysisResult]:
        current_time = now or _now_seconds()
        filters = self._cache_filters(
            platform=platform,
            sec_user_id=sec_user_id,
            analysis_type=analysis_type,
            scope_key=scope_key,
            input_hash=input_hash,
            provider=provider,
            model_name=model_name,
            prompt_version=prompt_version,
        )
        stmt = (
            select(AIAnalysisResult)
            .where(
                *filters,
                AIAnalysisResult.status == "done",
                or_(
                    AIAnalysisResult.expires_at.is_(None),
                    AIAnalysisResult.expires_at > current_time,
                ),
            )
            .order_by(AIAnalysisResult.updated_at.desc())
            .limit(1)
        )
        async with get_monitor_session() as session:
            return (await session.execute(stmt)).scalar_one_or_none()

    async def get_latest_result(
        self,
        *,
        sec_user_id: str,
        analysis_type: str,
        platform: str = "dy",
        status: Optional[str] = None,
    ) -> Optional[AIAnalysisResult]:
        stmt = select(AIAnalysisResult).where(
            AIAnalysisResult.platform == platform,
            AIAnalysisResult.sec_user_id == sec_user_id,
            AIAnalysisResult.analysis_type == analysis_type,
        )
        if status is not None:
            stmt = stmt.where(AIAnalysisResult.status == status)
        stmt = stmt.order_by(AIAnalysisResult.updated_at.desc()).limit(1)
        async with get_monitor_session() as session:
            return (await session.execute(stmt)).scalar_one_or_none()

    async def upsert_result(
        self,
        *,
        sec_user_id: str,
        analysis_type: str,
        scope_key: str,
        input_hash: str,
        provider: str,
        model_name: str,
        prompt_version: str,
        status: str = "done",
        result: Optional[Any] = None,
        usage: Optional[Any] = None,
        scope: Optional[Any] = None,
        error: Optional[str] = None,
        expires_at: Optional[int] = None,
        platform: str = "dy",
    ) -> AIAnalysisResult:
        if analysis_type not in ANALYSIS_TYPES:
            raise ValueError(f"Unsupported analysis type: {analysis_type}")
        if status not in ANALYSIS_STATUSES:
            raise ValueError(f"Unsupported analysis status: {status}")

        now = _now_seconds()
        filters = self._cache_filters(
            platform=platform,
            sec_user_id=sec_user_id,
            analysis_type=analysis_type,
            scope_key=scope_key,
            input_hash=input_hash,
            provider=provider,
            model_name=model_name,
            prompt_version=prompt_version,
        )
        async with get_monitor_session() as session:
            stmt = select(AIAnalysisResult).where(*filters)
            item = (await session.execute(stmt)).scalar_one_or_none()
            if item is None:
                item = AIAnalysisResult(
                    platform=platform,
                    sec_user_id=sec_user_id,
                    analysis_type=analysis_type,
                    scope_key=scope_key,
                    input_hash=input_hash,
                    provider=provider,
                    model_name=model_name,
                    prompt_version=prompt_version,
                    created_at=now,
                    updated_at=now,
                )
                session.add(item)

            item.status = status
            item.updated_at = now
            item.expires_at = expires_at
            if scope is not None:
                item.scope_json = _json_dumps(scope)
            if result is not None:
                item.result_json = _json_dumps(result)
            if usage is not None:
                item.usage_json = _json_dumps(usage)
            item.error = error
            await session.flush()
            return item

    async def mark_running(
        self,
        *,
        sec_user_id: str,
        analysis_type: str,
        scope_key: str,
        input_hash: str,
        provider: str,
        model_name: str,
        prompt_version: str,
        scope: Optional[Any] = None,
        platform: str = "dy",
    ) -> AIAnalysisResult:
        return await self.upsert_result(
            sec_user_id=sec_user_id,
            analysis_type=analysis_type,
            scope_key=scope_key,
            input_hash=input_hash,
            provider=provider,
            model_name=model_name,
            prompt_version=prompt_version,
            status="running",
            scope=scope,
            platform=platform,
        )

    async def mark_failed(
        self,
        *,
        sec_user_id: str,
        analysis_type: str,
        scope_key: str,
        input_hash: str,
        provider: str,
        model_name: str,
        prompt_version: str,
        error: str,
        platform: str = "dy",
    ) -> AIAnalysisResult:
        return await self.upsert_result(
            sec_user_id=sec_user_id,
            analysis_type=analysis_type,
            scope_key=scope_key,
            input_hash=input_hash,
            provider=provider,
            model_name=model_name,
            prompt_version=prompt_version,
            status="failed",
            error=error,
            platform=platform,
        )

    async def list_results(
        self,
        *,
        sec_user_id: Optional[str] = None,
        analysis_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        platform: str = "dy",
    ) -> list[AIAnalysisResult]:
        stmt = select(AIAnalysisResult).where(AIAnalysisResult.platform == platform)
        if sec_user_id is not None:
            stmt = stmt.where(AIAnalysisResult.sec_user_id == sec_user_id)
        if analysis_type is not None:
            stmt = stmt.where(AIAnalysisResult.analysis_type == analysis_type)
        if status is not None:
            stmt = stmt.where(AIAnalysisResult.status == status)
        stmt = stmt.order_by(AIAnalysisResult.updated_at.desc()).limit(max(1, limit))
        async with get_monitor_session() as session:
            return list((await session.execute(stmt)).scalars().all())

    async def delete_result(self, result_id: int) -> bool:
        async with get_monitor_session() as session:
            item = await session.get(AIAnalysisResult, result_id)
            if item is None:
                return False
            await session.delete(item)
            await session.flush()
            return True

    async def delete_for_scope(
        self,
        *,
        sec_user_id: str,
        analysis_type: str,
        scope_key: str,
        platform: str = "dy",
    ) -> int:
        stmt = select(AIAnalysisResult).where(
            AIAnalysisResult.platform == platform,
            AIAnalysisResult.sec_user_id == sec_user_id,
            AIAnalysisResult.analysis_type == analysis_type,
            AIAnalysisResult.scope_key == scope_key,
        )
        async with get_monitor_session() as session:
            items = list((await session.execute(stmt)).scalars().all())
            for item in items:
                await session.delete(item)
            await session.flush()
            return len(items)

    async def clear_expired(self, *, now: Optional[int] = None) -> int:
        current_time = now or _now_seconds()
        stmt = select(AIAnalysisResult).where(
            AIAnalysisResult.expires_at.is_not(None),
            AIAnalysisResult.expires_at <= current_time,
        )
        async with get_monitor_session() as session:
            items = list((await session.execute(stmt)).scalars().all())
            for item in items:
                await session.delete(item)
            await session.flush()
            return len(items)


ai_analysis_repository = AIAnalysisRepository()


__all__ = ["AIAnalysisRepository", "ai_analysis_repository", "ANALYSIS_TYPES", "ANALYSIS_STATUSES"]
