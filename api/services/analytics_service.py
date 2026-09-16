# -*- coding: utf-8 -*-
"""Analytics derived from collected post snapshots."""

import statistics
from datetime import datetime
from typing import Optional

from database.monitor_repository import monitor_repository


STAGE_ORDER = ["first_seen", "1h", "6h", "24h", "72h", "7d"]
METRICS = ("liked_count", "collected_count", "comment_count", "share_count")


class AnalyticsService:
    async def get_data(self, limit: int = 100) -> dict:
        posts = await monitor_repository.list_posts(limit=limit)
        snapshots = await monitor_repository.list_snapshots(limit=100000)
        post_map = {post.aweme_id: post for post in posts}

        snapshots_by_post: dict[str, list] = {}
        for snapshot in snapshots:
            if snapshot.aweme_id in post_map:
                snapshots_by_post.setdefault(snapshot.aweme_id, []).append(snapshot)
        for items in snapshots_by_post.values():
            items.sort(key=lambda item: item.actual_age_seconds)

        stage_deltas = self._stage_deltas(post_map, snapshots_by_post)
        growth_rates = self._growth_rates(post_map, snapshots_by_post)
        engagement_rates = self._engagement_rates(post_map, snapshots_by_post)
        leaderboard = self._leaderboards(post_map, snapshots_by_post)
        heatmap = self._publish_heatmap(post_map, snapshots_by_post)
        anomalies = self._detect_anomalies(post_map, growth_rates)

        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "stage_deltas": stage_deltas,
            "growth_rates": growth_rates[:100],
            "engagement_rates": engagement_rates,
            "leaderboard": leaderboard,
            "heatmap": heatmap,
            "anomalies": anomalies,
        }

    @staticmethod
    def _by_stage(items: list) -> dict:
        return {item.stage: item for item in items}

    def _stage_deltas(self, post_map: dict, snapshots_by_post: dict[str, list]) -> list[dict]:
        aggregates: dict[str, list[dict]] = {stage: [] for stage in STAGE_ORDER[1:]}
        for aweme_id, items in snapshots_by_post.items():
            by_stage = self._by_stage(items)
            base = by_stage.get("first_seen") or items[0]
            for stage in STAGE_ORDER[1:]:
                current = by_stage.get(stage)
                if current is None:
                    continue
                aggregates[stage].append({
                    "liked_count": current.liked_count - base.liked_count,
                    "collected_count": current.collected_count - base.collected_count,
                    "comment_count": current.comment_count - base.comment_count,
                    "share_count": current.share_count - base.share_count,
                })

        result = []
        for stage in STAGE_ORDER[1:]:
            rows = aggregates[stage]
            if not rows:
                continue
            result.append({
                "stage": stage,
                "sample_count": len(rows),
                **{
                    metric: round(sum(row[metric] for row in rows) / len(rows), 2)
                    for metric in METRICS
                },
            })
        return result

    def _growth_rates(self, post_map: dict, snapshots_by_post: dict[str, list]) -> list[dict]:
        results = []
        for aweme_id, items in snapshots_by_post.items():
            for previous, current in zip(items, items[1:]):
                hours = (current.actual_age_seconds - previous.actual_age_seconds) / 3600
                if hours <= 0:
                    continue
                for metric in METRICS:
                    delta = getattr(current, metric) - getattr(previous, metric)
                    results.append({
                        "aweme_id": aweme_id,
                        "title": post_map[aweme_id].title if aweme_id in post_map else aweme_id,
                        "metric": metric,
                        "from_stage": previous.stage,
                        "to_stage": current.stage,
                        "delta": delta,
                        "hours": round(hours, 3),
                        "per_hour": round(delta / hours, 2),
                    })
        results.sort(key=lambda item: item["per_hour"], reverse=True)
        return results

    def _engagement_rates(self, post_map: dict, snapshots_by_post: dict[str, list]) -> list[dict]:
        results = []
        for aweme_id, items in snapshots_by_post.items():
            latest = items[-1]
            total = latest.liked_count + latest.collected_count + latest.comment_count + latest.share_count
            if total <= 0:
                continue
            results.append({
                "aweme_id": aweme_id,
                "title": post_map[aweme_id].title if aweme_id in post_map else aweme_id,
                "stage": latest.stage,
                "interaction_total": total,
                "like_rate": round(latest.liked_count / total * 100, 2),
                "collect_rate": round(latest.collected_count / total * 100, 2),
                "comment_rate": round(latest.comment_count / total * 100, 2),
                "share_rate": round(latest.share_count / total * 100, 2),
            })
        return sorted(results, key=lambda item: item["interaction_total"], reverse=True)

    @staticmethod
    def _leaderboards(post_map: dict, snapshots_by_post: dict[str, list]) -> dict:
        latest_items = []
        for aweme_id, items in snapshots_by_post.items():
            latest = items[-1]
            latest_items.append({
                "aweme_id": aweme_id,
                "title": post_map[aweme_id].title if aweme_id in post_map else aweme_id,
                "stage": latest.stage,
                "liked_count": latest.liked_count,
                "collected_count": latest.collected_count,
                "comment_count": latest.comment_count,
                "share_count": latest.share_count,
                "score": latest.liked_count + latest.collected_count * 2 + latest.comment_count * 3 + latest.share_count * 2,
            })

        def ranked(metric: str) -> list[dict]:
            return sorted(latest_items, key=lambda item: item[metric], reverse=True)[:20]

        return {
            "overall": ranked("score"),
            "likes": ranked("liked_count"),
            "collections": ranked("collected_count"),
            "comments": ranked("comment_count"),
            "shares": ranked("share_count"),
        }

    @staticmethod
    def _publish_heatmap(post_map: dict, snapshots_by_post: dict[str, list]) -> list[dict]:
        cells: dict[tuple[int, int], list[int]] = {}
        for aweme_id, post in post_map.items():
            published = datetime.fromtimestamp(post.create_time)
            key = (published.weekday(), published.hour)
            items = snapshots_by_post.get(aweme_id, [])
            likes = items[-1].liked_count if items else 0
            cells.setdefault(key, []).append(likes)

        result = []
        for weekday in range(7):
            for hour in range(24):
                values = cells.get((weekday, hour), [])
                result.append({
                    "weekday": weekday,
                    "hour": hour,
                    "post_count": len(values),
                    "avg_likes": round(sum(values) / len(values), 2) if values else 0,
                })
        return result

    @staticmethod
    def _detect_anomalies(post_map: dict, growth_rates: list[dict]) -> list[dict]:
        like_rates = [item["per_hour"] for item in growth_rates if item["metric"] == "liked_count" and item["per_hour"] > 0]
        if len(like_rates) < 3:
            return []
        median = statistics.median(like_rates)
        deviations = [abs(value - median) for value in like_rates]
        mad = statistics.median(deviations) or max(median * 0.5, 1)
        threshold = max(median + 3 * mad, median * 2, 10)
        anomalies = [item for item in growth_rates if item["metric"] == "liked_count" and item["per_hour"] > threshold]
        for item in anomalies:
            item["baseline_per_hour"] = round(median, 2)
            item["score"] = round(item["per_hour"] / max(median, 1), 2)
        return anomalies[:20]


analytics_service = AnalyticsService()
