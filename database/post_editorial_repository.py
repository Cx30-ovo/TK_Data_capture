"""Persistent text-tag cache; version and model are encoded into cache keys."""
import json
import time

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from .db_session import get_monitor_session
from .models import PostEditorialLabel


class PostEditorialRepository:
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
