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
                "ocr_text": "重要新闻 2026",
                "text_density": "medium",
                "text_position": "bottom",
                "text_hook": "news_headline",
                "subject_type": "news_scene",
                "person_count": "1",
                "face_closeup": False,
                "composition": "medium",
                "color_tone": "cool",
                "brightness": "medium",
                "contrast": "high",
                "information_density": "high",
                "visual_style": ["news", "documentary"],
                "emotion": "neutral",
                "has_logo": True,
                "has_subtitle_bar": True,
                "has_number": True,
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
        {"interaction": 100, "is_hit": True, "labels": {"subject_type": "person", "visual_style": ["portrait"], "ocr_text": "新闻"}},
        {"interaction": 20, "is_hit": False, "labels": {"subject_type": "person", "visual_style": ["portrait"], "ocr_text": ""}},
        {"interaction": 10, "is_hit": False, "labels": {"subject_type": "scenery", "visual_style": ["scenery"], "ocr_text": ""}},
    ])
    person = next(row for row in result["dimensions"] if row["dimension"] == "subject_type" and row["label"] == "person")
    assert result["sample_count"] == 3
    assert person["count"] == 2
    assert person["avg_interaction"] == 60
    assert person["hit_rate"] == 0.5
    assert person["lift"] == 1.5


@pytest.mark.asyncio
async def test_cover_analysis_labels_only_eligible_samples_and_reuses_cache():
    model = FakeVisionModel()
    repository = FakeCoverRepository()
    async def image_loader(url):
        return "data:image/jpeg;base64,dGVzdA=="

    service = CoverAnalysisService(model_service=model, repository=repository, image_loader=image_loader)
    samples = [
        {"aweme_id": "hit", "title": "爆款", "cover_url": "https://example.com/hit.jpg", "interaction": 100, "is_hit": True},
        {"aweme_id": "normal", "title": "普通", "cover_url": "https://example.com/normal.jpg", "interaction": 10, "is_hit": False},
        {"aweme_id": "missing", "title": "无封面", "cover_url": "", "interaction": 5, "is_hit": False},
    ]

    first = await service.analyze_samples(samples)
    second = await service.analyze_samples(samples)

    assert first["status"] == "done"
    assert first["requested_sample_count"] == 3
    assert first["sample_count"] == 2
    assert first["missing_cover_count"] == 1
    assert len(model.calls) == 1
    assert {image["id"] for image in model.calls[0]} == {"hit", "normal"}
    assert all(image["url"].startswith("data:image/jpeg;base64,") for image in model.calls[0])
    assert second["sample_count"] == 2
    assert len(model.calls) == 1
