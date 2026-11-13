"""Automatic rules with a disposable background cache. No model or manual IO."""
import asyncio
import hashlib
import json
import logging
import time
from copy import deepcopy
from .editorial_rule_cache import EditorialRuleCache

from database.post_editorial_repository import source_sha256
from .post_editorial_tags import RULE_VERSION, assess_post

VERSION = RULE_VERSION


class PostEditorialService:
    def __init__(self, model=None, repository=None, media_loader=None):
        # Keep the constructor shape for existing callers, but never inspect or
        # use injected providers. Old persisted classifications remain untouched.
        self.worker = None
        self.queue = asyncio.Queue()
        self.pending = set()
        self.cache = None
        self.progress = {"state": "not_started", "scanned": 0, "recomputed": 0,
                         "reused": 0, "last_completed_at": None, "last_error": None}

    def available(self):
        return False

    def cache_key(self, post, references=None):
        value = [VERSION, source_sha256(post)]
        return hashlib.sha256(json.dumps(value).encode()).hexdigest()

    @staticmethod
    def classify(post):
        return {**assess_post(post.title, post.desc),
                "classification_source_sha256": source_sha256(post),
                "manual_revision": 0, "manual_status": "none", "manual_reason": "",
                "manual_corrected_at": None}

    async def read_for_correction(self, post):
        """Compatibility GET: automatic rule labels, no database writes or jobs."""
        return (await self.enrich([post]))[post.aweme_id]

    async def enrich(self, posts):
        sources = [(post.aweme_id, source_sha256(post)) for post in posts]
        saved = await asyncio.to_thread(self.cache.read_many, sources) if self.cache else {}
        # Work is bounded by the query's posts; never schedule writes from GET.
        def assemble():
            result = {}
            for post in posts:
                row = saved.get(post.aweme_id)
                tags = deepcopy(row["tags"]) if row else self.classify(post)
                result[post.aweme_id] = {**tags, "classification_cached_at": row["cached_at"] if row else None,
                    "classification_cache_status": "current" if row else "pending" if self.cache else "disabled"}
            return result
        return await asyncio.to_thread(assemble)

    def health(self, posts, tags):
        """Counts are scoped to the returned account and loaded rows, not global."""
        rows = [tags[post.aweme_id] for post in posts]
        reasons, channels, regions = {}, {}, {}
        for row in rows:
            for field, counts in (("channel", channels), ("region", regions)):
                label = row[field]
                counts[label] = counts.get(label, 0) + 1
            for reason in row["tag_pending_reasons"]:
                code = reason["code"]
                reasons[code] = reasons.get(code, 0) + 1
        cached = [row["classification_cached_at"] for row in rows if row.get("classification_cached_at")]
        return dict(rule_version=VERSION, total=len(rows), scope="loaded_posts",
                    channel_resolved=sum(row["channel"] != "待判定" for row in rows),
                    region_resolved=sum(row["region"] != "待判定" for row in rows),
                    pending_posts=sum(bool(row["tag_pending_reasons"]) for row in rows),
                    pending_reasons=reasons, channel_counts=channels, region_counts=regions,
                    cached_posts=len(cached), last_updated_at=max(cached, default=None),
                    worker={**self.progress, "scope": "all_accounts"})

    async def start(self, source_repository, cache_dir, batch_size=100, interval=15):
        if self.worker and not self.worker.done():
            return
        self.cache = EditorialRuleCache(cache_dir, VERSION)
        self.worker = asyncio.create_task(self._run(source_repository, batch_size, interval),
                                          name="editorial-rule-cache")

    async def refresh_once(self, repository, modified_since=None, batch_size=100):
        """Stable ID keyset batches with a fixed timestamp boundary per sweep."""
        cutoff = int(time.time())
        self.progress.update(state="rebuilding" if modified_since is None else "incremental",
                             scanned=0, recomputed=0, reused=0, last_error=None)
        after_id = 0
        try:
            while True:
                posts = await repository.list_editorial_sources(after_id=after_id, limit=batch_size,
                    modified_since=modified_since, modified_until=cutoff)
                if not posts:
                    break
                def cache_batch():
                    existing = self.cache.read_many([(p.aweme_id, source_sha256(p)) for p in posts])
                    recomputed = 0
                    for post in posts:
                        if post.aweme_id not in existing:
                            self.cache.save(post.aweme_id, source_sha256(post), self.classify(post))
                            recomputed += 1
                    return recomputed
                changed = await asyncio.to_thread(cache_batch)
                self.progress["scanned"] += len(posts)
                self.progress["recomputed"] += changed
                self.progress["reused"] += len(posts) - changed
                after_id = posts[-1].id
                await asyncio.sleep(0)
            self.progress.update(state="idle", last_completed_at=int(time.time()))
        except Exception:
            self.progress.update(state="error", last_error="分类缓存更新失败，读取仍使用当前规则兜底")
            raise
        return cutoff

    async def _run(self, repository, batch_size, interval):
        watermark = None
        sweeps = 0
        while True:
            try:
                # Periodic reconciliation also catches delayed commits and
                # external imports whose source timestamps predate the cursor.
                if sweeps % 120 == 0:
                    watermark = None
                cutoff = await self.refresh_once(repository, watermark, batch_size)
                # Inclusive overlap prevents same-second updates being skipped.
                watermark = max(0, cutoff - 1)
                sweeps += 1
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.getLogger(__name__).warning("Editorial rule cache update failed; retrying")
            await asyncio.sleep(interval)

    async def stop(self):
        if self.worker and not self.worker.done():
            self.worker.cancel()
            try:
                await self.worker
            except asyncio.CancelledError:
                pass
        while not self.queue.empty():
            self.queue.get_nowait()
            self.queue.task_done()
        self.pending.clear()


post_editorial_service = PostEditorialService()
