"""Persistent text-tag cache; version and model are encoded into cache keys."""
import json
import time
import hashlib

from sqlalchemy import select, text
from sqlalchemy.dialects.sqlite import insert

from .db_session import get_monitor_session
from .models import DouyinPost, PostEditorialLabel


def source_sha256(post):
    value = ["dy", post.aweme_id, post.title or "", post.desc or ""]
    return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode()).hexdigest()


def manual_key(aweme_id):
    return hashlib.sha256(json.dumps(["editorial-manual-v1", aweme_id]).encode()).hexdigest()


class EditorialCorrectionError(Exception):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


class PostEditorialRepository:
    async def correction_examples(self, limit=200):
        """Only current human corrections are eligible as reference examples."""
        async with get_monitor_session() as session:
            rows = (await session.execute(select(PostEditorialLabel, DouyinPost).join(
                DouyinPost, (DouyinPost.aweme_id == PostEditorialLabel.aweme_id) & (DouyinPost.platform == "dy")
            ).where(PostEditorialLabel.tags_json.contains('"revision"'))
              .order_by(PostEditorialLabel.updated_at.desc(), PostEditorialLabel.cache_key).limit(limit))).all()
            examples = []
            for label, post in rows:
                try:
                    value = json.loads(label.tags_json)
                    if (label.cache_key != manual_key(post.aweme_id) or not value.get("active")
                            or value.get("source_sha256") != source_sha256(post)
                            or (value.get("channel") == "待判定" and value.get("region") == "待判定")):
                        continue
                    examples.append({"aweme_id": post.aweme_id, "title": post.title or "", "desc": post.desc or "",
                                     "channel": value["channel"], "region": value["region"],
                                     "reason": value["reason"], "revision": value["revision"],
                                     "source_sha256": value["source_sha256"]})
                except (ValueError, TypeError, KeyError, AttributeError):
                    continue
            return examples

    async def stored_video_url(self, aweme_id):
        from .models import DouyinAweme
        async with get_monitor_session() as session:
            return (await session.execute(select(DouyinAweme.video_download_url).where(
                DouyinAweme.aweme_id == aweme_id).order_by(DouyinAweme.id.desc()).limit(1))).scalar_one_or_none() or ""

    async def load_manual(self, ids):
        keys = {manual_key(ident): ident for ident in ids}
        saved = await self.load(list(keys)) if keys else {}
        return {keys[key]: row["tags"] for key, row in saved.items()}

    async def correct(self, aweme_id, request):
        """Serialize short manual writes; never share a key with model results."""
        async with get_monitor_session() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            post = (await session.execute(select(DouyinPost).where(
                DouyinPost.platform == "dy", DouyinPost.aweme_id == aweme_id))).scalar_one_or_none()
            if post is None:
                raise EditorialCorrectionError(404, "作品不存在")
            if source_sha256(post) != request.source_sha256:
                raise EditorialCorrectionError(409, "作品原文已变化，请重新打开纠正面板后重试")
            key = manual_key(aweme_id)
            row = await session.get(PostEditorialLabel, key)
            try:
                old = json.loads(row.tags_json) if row else {}
                revision = old.get("revision", 0)
                if type(revision) is not int or revision < 0:
                    raise ValueError()
            except (ValueError, TypeError, AttributeError) as exc:
                raise EditorialCorrectionError(503, "人工分类记录无法读取，请稍后重试") from exc
            if revision != request.expected_revision:
                raise EditorialCorrectionError(409, "分类已更新，请重新打开纠正面板后重试")
            now = int(time.time())
            value = {"active": request.mode == "manual", "revision": revision + 1,
                     "source_sha256": request.source_sha256, "corrected_at": now,
                     "channel": request.channel, "region": request.region, "reason": request.reason}
            values = dict(cache_key=key, aweme_id=aweme_id,
                          tags_json=json.dumps(value, ensure_ascii=False), retry_at=0, updated_at=now)
            stmt = insert(PostEditorialLabel).values(**values)
            await session.execute(stmt.on_conflict_do_update(index_elements=["cache_key"], set_=values))
            return value

    async def load(self, keys):
        result = {}
        async with get_monitor_session() as session:
            for offset in range(0, len(keys), 400):
                rows = (await session.execute(select(PostEditorialLabel).where(
                    PostEditorialLabel.cache_key.in_(keys[offset:offset + 400])))).scalars()
                for row in rows:
                    try:
                        result[row.cache_key] = {"tags": json.loads(row.tags_json), "retry_at": row.retry_at}
                    except (ValueError, TypeError):
                        continue
        return result

    async def save(self, key, post_id, tags, retry_at=0):
        async with get_monitor_session() as session:
            values = dict(cache_key=key, aweme_id=post_id, tags_json=json.dumps(tags, ensure_ascii=False),
                          retry_at=retry_at, updated_at=int(time.time()))
            stmt = insert(PostEditorialLabel).values(**values)
            await session.execute(stmt.on_conflict_do_update(index_elements=["cache_key"], set_=values))


post_editorial_repository = PostEditorialRepository()
