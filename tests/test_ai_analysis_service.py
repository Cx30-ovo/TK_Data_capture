import time
from types import SimpleNamespace

import pytest

from api.services.ai_analysis_service import AIAnalysisService
from database import db_session
from database.ai_analysis_repository import ai_analysis_repository


@pytest.fixture
def isolated_ai_analysis_db(tmp_path, monkeypatch):
    db_path = tmp_path / "ai_analysis_service.db"
    monkeypatch.setitem(db_session.sqlite_db_config, "db_path", str(db_path))
    db_session._engines.pop("sqlite", None)
    yield
    db_session._engines.pop("sqlite", None)


def make_post(aweme_id, title, create_time, first_seen_at):
    return SimpleNamespace(
        aweme_id=aweme_id,
        sec_user_id="sec_ai_service",
        title=title,
        desc=f"{title} #测试",
        create_time=create_time,
        first_seen_at=first_seen_at,
        canonical_url=f"https://www.douyin.com/video/{aweme_id}",
        status="active",
    )


def make_snapshot(aweme_id, stage, age_seconds, liked_count=0, collected_count=0, comment_count=0, share_count=0):
    return SimpleNamespace(
        aweme_id=aweme_id,
        stage=stage,
        actual_age_seconds=age_seconds,
        captured_at=1_900_000_000 + age_seconds,
        liked_count=liked_count,
        collected_count=collected_count,
        comment_count=comment_count,
        share_count=share_count,
    )


class FakeMonitorRepository:
    def __init__(self, posts, snapshots):
        self.posts = posts
        self.snapshots = snapshots

    async def list_posts(self, sec_user_id=None, limit=100):
        return self.posts[:limit]

    async def list_snapshots(self, sec_user_id=None, limit=100000):
        return self.snapshots[:limit]

    async def get_monitored_account(self, sec_user_id):
        return SimpleNamespace(display_name="测试账号")


class FakeModelService:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def get_status(self):
        return {
            "provider": "openai_compatible",
            "model": "Qwen3.8-27B-FP8",
        }

    async def generate_json(self, **kwargs):
        self.calls += 1
        return self.response


class SequenceModelService(FakeModelService):
    def __init__(self, responses):
        super().__init__({})
        self.responses = list(responses)

    async def generate_json(self, **kwargs):
        response = self.responses[self.calls]
        self.calls += 1
        return response


@pytest.mark.asyncio
async def test_topic_analysis_recomputes_metrics_and_uses_cache(isolated_ai_analysis_db):
    await db_session.create_tables("sqlite")
    now = int(time.time())
    posts = [
        make_post("p1", "厦门地铁建设", now - 300, now - 200),
        make_post("p2", "地铁线路进展", now - 200, now - 150),
        make_post("p3", "周末演出活动", now - 100, now - 50),
    ]
    snapshots = [
        make_snapshot("p1", "first_seen", 300, liked_count=10),
        make_snapshot("p2", "first_seen", 200, liked_count=20),
        make_snapshot("p3", "first_seen", 100, liked_count=30),
    ]
    model = FakeModelService({
        "summary": "主题摘要",
        "clusters": [
            {
                "name": "厦门地铁",
                "description": "地铁建设内容",
                "post_ids": ["p1", "p2", "unknown"],
                "keywords": ["地铁"],
                "confidence": 0.9,
            }
        ],
        "tag_groups": [],
        "recommendations": [],
        "data_limits": [],
    })
    service = AIAnalysisService(
        model_service=model,
        analysis_repository=ai_analysis_repository,
        monitor_repository_instance=FakeMonitorRepository(posts, snapshots),
    )

    first = await service.analyze_topics(sec_user_id="sec_ai_service", scope={"time_range": "all"})
    assert first["status"] == "done"
    assert first["cache_hit"] is False
    assert first["result"]["source_post_count"] == 3
    assert first["result"]["clusters"][0]["posts"] == 2
    assert first["result"]["clusters"][0]["total_interaction"] == 30
    assert model.calls == 1

    second = await service.analyze_topics(sec_user_id="sec_ai_service", scope={"time_range": "all"})
    assert second["cache_hit"] is True
    assert second["id"] == first["id"]
    assert model.calls == 1

    await service.analyze_topics(sec_user_id="sec_ai_service", scope={"time_range": "all"}, force=True)
    assert model.calls == 2


@pytest.mark.asyncio
async def test_lifecycle_analysis_enriches_post_insights(isolated_ai_analysis_db):
    await db_session.create_tables("sqlite")
    now = int(time.time())
    posts = [
        make_post("life-1", "持续增长作品", now - 500, now - 400),
        make_post("life-2", "快速爆发作品", now - 400, now - 300),
    ]
    snapshots = [
        make_snapshot("life-1", "1h", 3600, liked_count=10),
        make_snapshot("life-1", "6h", 21600, liked_count=30),
        make_snapshot("life-1", "24h", 86400, liked_count=100),
        make_snapshot("life-1", "72h", 259200, liked_count=110),
        make_snapshot("life-2", "1h", 3600, liked_count=100),
        make_snapshot("life-2", "6h", 21600, liked_count=120),
        make_snapshot("life-2", "24h", 86400, liked_count=130),
        make_snapshot("life-2", "72h", 259200, liked_count=140),
    ]
    model = FakeModelService({
        "overall_summary": "整体摘要",
        "post_insights": [
            {"aweme_id": "life-1", "pattern": "长尾", "evidence": ["24h 增量较高"], "possible_factors": [], "confidence": 0.8},
            {"aweme_id": "unknown", "pattern": "无效", "evidence": [], "possible_factors": [], "confidence": 0.1},
        ],
        "content_patterns": [],
        "anomaly_notes": [],
        "recommendations": [],
        "caveats": [],
    })
    service = AIAnalysisService(
        model_service=model,
        analysis_repository=ai_analysis_repository,
        monitor_repository_instance=FakeMonitorRepository(posts, snapshots),
    )

    result = await service.analyze_lifecycle(sec_user_id="sec_ai_service", scope={"time_range": "all"})
    assert result["status"] == "done"
    assert len(result["result"]["post_insights"]) == 1
    assert result["result"]["post_insights"][0]["aweme_id"] == "life-1"
    assert result["result"]["post_insights"][0]["metrics"]["tail"] == pytest.approx(100 / 30, abs=0.0001)
    assert sum(result["result"]["type_distribution"].values()) == 2
    assert [row["stage"] for row in result["result"]["stage_summary"]] == ["1h", "6h", "24h", "72h"]


@pytest.mark.asyncio
async def test_analysis_returns_insufficient_data_without_calling_model(isolated_ai_analysis_db):
    await db_session.create_tables("sqlite")
    now = int(time.time())
    model = FakeModelService({})
    service = AIAnalysisService(
        model_service=model,
        analysis_repository=ai_analysis_repository,
        monitor_repository_instance=FakeMonitorRepository(
            [make_post("only-one", "单篇作品", now, now)],
            [],
        ),
    )

    result = await service.analyze_topics(sec_user_id="sec_ai_service", scope={"time_range": "all"})
    assert result["status"] == "insufficient_data"
    assert model.calls == 0


@pytest.mark.asyncio
async def test_title_strategy_runs_three_model_phases_and_uses_cache(isolated_ai_analysis_db):
    await db_session.create_tables("sqlite")
    now = int(time.time())
    posts = [
        make_post(f"strategy-{index}", f"厦门地铁新进展第{index}期", now - index * 100, now - index * 90)
        for index in range(1, 7)
    ]
    snapshots = [
        make_snapshot(f"strategy-{index}", "24h", 86400, liked_count=1000 if index == 1 else index * 10)
        for index in range(1, 7)
    ]
    model = SequenceModelService([
        {
            "top_keywords": [{"keyword": "厦门", "conclusion": "与较高互动表现相关"}],
            "title_length_analysis": {"best_range": "≤20字", "trend": "短标题表现更集中", "long_vs_short": {"winner": "短标题", "explanation": "样本中表现更高"}, "recommendation": "优先测试短标题"},
            "overall_insight": "本批作品以本地交通内容为主",
        },
        {
            "hit_works": [{"aweme_id": "strategy-1", "title": "厦门地铁新进展第1期", "hook_type": "热点借势", "why_viral": "本地热点可能带来讨论", "title_formula": "城市+事件+进展", "interaction_structure": "点赞为主"}],
            "hit_vs_normal": {"key_differences": ["爆款更聚焦具体进展"], "common_patterns": "本地身份标签"},
            "reusable_formulas": [{"formula": "城市+事件+进展", "example": "厦门地铁新进展", "why_effective": "信息明确"}],
        },
        {
            "strategy_summary": {"core_finding": "具体进展更值得测试", "title_length_advice": "保持精炼", "keyword_advice": "保留城市词", "content_advice": "持续跟踪"},
            "next_titles": [{"title": "厦门地铁又有新进展", "formula": "城市+事件+进展", "expected_length": 99, "target_audience": "本地通勤者", "hook_type": "热点借势"}],
            "risk_notes": ["样本量有限"],
        },
    ])
    service = AIAnalysisService(
        model_service=model,
        analysis_repository=ai_analysis_repository,
        monitor_repository_instance=FakeMonitorRepository(posts, snapshots),
    )

    first = await service.analyze_title_strategy(sec_user_id="sec_ai_service", scope={"time_range": "all", "post_limit": 100})
    assert first["status"] == "done"
    assert first["analysis_type"] == "title_strategy"
    assert first["result"]["meta"]["total_works"] == 6
    assert first["result"]["next_titles"][0]["expected_length"] == len("厦门地铁又有新进展")
    assert model.calls == 3

    second = await service.analyze_title_strategy(sec_user_id="sec_ai_service", scope={"time_range": "all", "post_limit": 100})
    assert second["cache_hit"] is True
    assert model.calls == 3


def test_lifecycle_result_uses_deterministic_fallback_when_model_has_no_valid_ids():
    now = int(time.time())
    service = AIAnalysisService(model_service=FakeModelService({}), analysis_repository=ai_analysis_repository)
    posts = service._build_lifecycle_posts(
        [make_post("fallback-1", "兜底作品", now - 500, now - 400)],
        {
            "fallback-1": [
                make_snapshot("fallback-1", "1h", 3600, liked_count=10),
                make_snapshot("fallback-1", "6h", 21600, liked_count=30),
                make_snapshot("fallback-1", "24h", 86400, liked_count=100),
                make_snapshot("fallback-1", "72h", 259200, liked_count=110),
            ]
        },
    )

    normalized = service._normalize_lifecycle_result({"overall_summary": "摘要", "post_insights": []}, posts)
    assert normalized["post_insights"][0]["aweme_id"] == "fallback-1"
    assert normalized["post_insights"][0]["source"] == "deterministic"
    assert normalized["post_insights"][0]["evidence"]


def test_cover_attribution_payload_excludes_images_ocr_and_titles():
    payload = AIAnalysisService._cover_text_payload({
        "status": "done",
        "sample_count": 1,
        "statistics": {"dimensions": [{"dimension": "subject_type", "label": "person", "count": 1}]},
        "samples": [{
            "title": "不应进入文本模型",
            "cover_url": "https://example.com/private-cover.jpg",
            "labels": {"ocr_text": "封面原文"},
        }],
    })
    serialized = str(payload)
    assert "subject_type" in serialized
    assert "private-cover" not in serialized
    assert "封面原文" not in serialized
    assert "不应进入文本模型" not in serialized


@pytest.mark.asyncio
async def test_topic_ideas_are_generated_from_selected_topic_report(isolated_ai_analysis_db):
    await db_session.create_tables("sqlite")
    topic_report = await ai_analysis_repository.upsert_result(
        sec_user_id="sec_ai_service",
        analysis_type="topic",
        scope_key="topic:30d:limit=10",
        input_hash="d" * 64,
        provider="openai_compatible",
        model_name="Qwen3.8-27B-FP8",
        prompt_version="topic-v1",
        result={
            "summary": "地铁主题表现最好",
            "clusters": [{"name": "厦门地铁", "description": "地铁建设", "keywords": ["地铁"], "representative_insight": "试乘内容表现突出"}],
            "recommendations": ["围绕地铁通勤做系列内容"],
            "data_limits": [],
            "source_post_count": 10,
        },
    )
    model = FakeModelService({
        "summary": "优先做地铁系列",
        "ideas": [
            {
                "title": "地铁新线试乘实测",
                "angle": "从通勤时间变化切入",
                "format": "实地探访",
                "audience": "沿线通勤人群",
                "why_now": "地铁主题互动表现最好",
                "evidence": ["厦门地铁"],
                "expected_performance": "high",
                "difficulty": "medium",
                "risk_notes": "需要提前确认拍摄许可",
                "priority": 1,
            }
        ],
        "avoid": ["低互动国际时事"],
    })
    service = AIAnalysisService(model_service=model, analysis_repository=ai_analysis_repository)

    result = await service.analyze_topic_ideas(
        sec_user_id="sec_ai_service",
        topic_result_id=topic_report.id,
    )
    assert result["status"] == "done"
    assert result["result"]["ideas"][0]["title"] == "地铁新线试乘实测"
    assert result["result"]["ideas"][0]["expected_performance"] == "high"
    assert model.calls == 1
