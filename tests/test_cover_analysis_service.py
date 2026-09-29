import pytest

from api.services.cover_analysis_service import CoverAnalysisService, compute_cover_statistics


class FakeVisionModel:
    def __init__(self):
        self.calls = []

    def get_status(self):
        return {"configured": True, "model": "vision-test"}

    async def generate_multimodal_json(self, *, images, **kwargs):
        self.calls.append(images)
        return {
            "items": [{
                "aweme_id": image["id"],
                "theme_type": "news_event",
                "text_density": "medium",
                "text_hook": "news_headline",
                "text_character_count_estimate": 8,
                "composition": "medium",
                "color_tone": "cool",
                "visual_style": ["news", "documentary"],
                "scores": {
                    "information_focus": 80,
                    "visual_hierarchy": 76,
                    "subject_clarity": 82,
                    "text_readability": 78,
                    "emotional_tension": 70,
                    "thumbnail_recognition": 74,
                },
                "confidence": 0.93,
            } for image in images]
        }


class FakeCoverRepository:
    def __init__(self):
        self.cache = {}

    async def get_cover_label(self, **kwargs):
        return self.cache.get((kwargs["aweme_id"], kwargs["cover_hash"], kwargs["model_name"], kwargs["prompt_version"]))

    async def upsert_cover_label(self, *, labels, **kwargs):
        self.cache[(kwargs["aweme_id"], kwargs["cover_hash"], kwargs["model_name"], kwargs["prompt_version"])] = dict(labels)


def test_cover_statistics_are_computed_from_controlled_labels():
    result = compute_cover_statistics([
        {"interaction": 100, "visual_quality_score": 80, "data_performance_score": 100, "cover_performance_score": 92, "labels": {"theme_type": "news_event", "composition": "medium", "text_density": "low", "text_hook": "news_headline", "text_character_count_estimate": 6, "color_tone": "cool", "visual_style": ["news"]}},
        {"interaction": 20, "visual_quality_score": 60, "data_performance_score": 50, "cover_performance_score": 54, "labels": {"theme_type": "news_event", "composition": "medium", "text_density": "medium", "text_hook": "number_fact", "text_character_count_estimate": 10, "color_tone": "cool", "visual_style": ["news"]}},
        {"interaction": 10, "visual_quality_score": 40, "data_performance_score": 0, "cover_performance_score": 16, "labels": {"theme_type": "culture_tourism", "composition": "wide", "text_density": "none", "text_hook": "none", "text_character_count_estimate": 0, "color_tone": "warm", "visual_style": ["scenery"]}},
    ])
    news = next(row for row in result["dimensions"] if row["dimension"] == "theme_type" and row["label"] == "news_event")
    medium_composition = next(row for row in result["dimensions"] if row["dimension"] == "composition" and row["label"] == "medium")
    assert result["sample_count"] == 3
    assert result["average_cover_score"] == 54
    assert news["count"] == 2
    assert news["median_interaction"] == 60
    assert news["avg_cover_score"] == 73
    assert news["sample_status"] == "insufficient"
    assert medium_composition["label_name"] == "中景"
    assert {row["dimension"] for row in result["dimensions"]} == {"theme_type", "text_density", "text_hook", "composition", "visual_style", "color_tone"}


@pytest.mark.asyncio
async def test_cover_analysis_labels_only_eligible_samples_and_reuses_cache():
    model = FakeVisionModel()
    repository = FakeCoverRepository()
    async def image_loader(url):
        return "data:image/jpeg;base64,dGVzdA=="

    service = CoverAnalysisService(model_service=model, repository=repository, image_loader=image_loader)
    samples = [
        {"aweme_id": "hit", "title": "爆款", "cover_url": "https://example.com/hit.jpg", "canonical_url": "https://www.douyin.com/video/hit", "create_time": 1_800_000_000, "publish_time": "2027-01-15T08:00:00", "interaction": 100, "likes": 70, "comments": 5, "collects": 5, "shares": 5, "is_hit": True},
        {"aweme_id": "normal", "title": "普通", "cover_url": "https://example.com/normal.jpg", "canonical_url": "https://www.douyin.com/video/normal", "create_time": 1_800_000_100, "publish_time": "2027-01-15T08:01:40", "interaction": 10, "likes": 10, "comments": 0, "collects": 0, "shares": 0, "is_hit": False},
        {"aweme_id": "missing", "title": "无封面", "cover_url": "", "interaction": 5, "is_hit": False},
    ]

    first = await service.analyze_samples(samples)
    second = await service.analyze_samples(samples)

    assert first["status"] == "done"
    assert first["requested_sample_count"] == 3
    assert first["valid_cover_count"] == 2
    assert first["sample_count"] == 2
    assert first["missing_cover_count"] == 1
    assert len(model.calls) == 1
    assert {image["id"] for image in model.calls[0]} == {"hit", "normal"}
    assert all(image["url"].startswith("data:image/jpeg;base64,") for image in model.calls[0])
    assert second["sample_count"] == 2
    assert len(model.calls) == 1
    assert first["statistics"]["average_visual_score"] > 0
    assert len(first["score_records"]) == 2
    assert all("cover_performance_score" in row for row in first["score_records"])
    assert first["score_records"][0]["title"]
    assert first["score_records"][0]["cover_url"].startswith("https://")
    assert first["score_records"][0]["canonical_url"].startswith("https://www.douyin.com/video/")
    assert first["score_records"][0]["create_time"] > 0
    assert "interaction" in first["score_records"][0]
    assert "samples" not in first


@pytest.mark.asyncio
async def test_candidate_cover_uses_visual_model_and_historical_reference():
    model = FakeVisionModel()
    service = CoverAnalysisService(model_service=model, repository=FakeCoverRepository())
    score_records = [{
        "aweme_id": str(index),
        "visual_quality_score": 70 + index % 10,
        "data_performance_score": 62 + index % 15,
        "labels": {
            "theme_type": "news_event",
            "text_density": "medium",
            "text_hook": "news_headline",
            "composition": "medium",
            "color_tone": "cool",
            "visual_style": ["news", "documentary"],
        },
    } for index in range(35)]
    dimensions = []
    for dimension, label in (
        ("theme_type", "news_event"),
        ("text_density", "medium"),
        ("text_hook", "news_headline"),
        ("composition", "medium"),
        ("visual_style", "news"),
        ("color_tone", "cool"),
    ):
        dimensions.append({
            "dimension": dimension,
            "label": label,
            "count": 35,
            "avg_data_score": 68,
        })
    result = await service.evaluate_candidate(
        "data:image/jpeg;base64,dGVzdA==",
        {
            "statistics": {
                "average_visual_score": 68,
                "average_data_score": 60,
                "average_cover_score": 63,
                "dimensions": dimensions,
            },
            "score_records": score_records,
        },
    )

    assert result["status"] == "done"
    assert result["reference_count"] == 35
    assert result["similar_count"] == 35
    assert result["confidence"] == "high"
    assert result["visual_quality_score"] > 0
    assert result["estimated_data_score"] > 0
    assert len(result["factor_evidence"]) == 6
    assert model.calls[0][0]["id"] == "candidate"
