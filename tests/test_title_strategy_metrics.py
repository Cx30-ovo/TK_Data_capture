from types import SimpleNamespace

from api.services.title_strategy_metrics import clean_title, compute_title_strategy, interaction_score


def post(index: int, title: str):
    return SimpleNamespace(
        aweme_id=f"p{index}",
        title=title,
        desc=title,
        create_time=1_900_000_000 + index,
    )


def snapshot(index: int, likes: int, comments: int = 0, collects: int = 0, shares: int = 0):
    return SimpleNamespace(
        aweme_id=f"p{index}",
        actual_age_seconds=3600,
        captured_at=1_900_003_600 + index,
        liked_count=likes,
        comment_count=comments,
        collected_count=collects,
        share_count=shares,
    )


def test_title_cleaning_and_weighted_interaction_score():
    assert clean_title("厦门地铁通车！#本地新闻 @记者（编辑：小王）") == "厦门地铁通车"
    assert interaction_score(10, 2, 3, 4) == 32


def test_title_strategy_metrics_are_deterministic_and_use_unique_title_keywords():
    posts = [
        post(1, "厦门地铁地铁迎来新进展"),
        post(2, "厦门地铁新线路正式通车"),
        post(3, "厦门地铁建设进入新阶段"),
        post(4, "周末公园活动指南"),
        post(5, "城市夜景打卡攻略"),
    ]
    snapshots = {
        "p1": [snapshot(1, 10)],
        "p2": [snapshot(2, 20)],
        "p3": [snapshot(3, 1000, shares=100)],
        "p4": [snapshot(4, 5)],
        "p5": [snapshot(5, 8)],
    }

    result = compute_title_strategy(posts, snapshots)

    assert result["overview"]["total_works"] == 5
    assert result["overview"]["hit_threshold"] > result["overview"]["interaction_mean"]
    keyword = next(row for row in result["top_keywords"] if row["keyword"] == "厦门")
    assert keyword["count"] == 3
    assert keyword["ratio"] == 0.6
    assert result["long_vs_short"]["short"]["count"] + result["long_vs_short"]["long"]["count"] == 5
    assert len(result["hit_samples"]) <= 20
    assert len(result["normal_samples"]) <= 20

