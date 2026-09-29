import pytest

from api.services.monitor_service import DouyinMonitorFetcher, MonitorService


class FakeHotClient:
    async def get_hot_search_list(self):
        return {
            "data": {
                "word_list": [
                    {
                        "word": "一条巷子里的中国智慧",
                        "hot_value": 0,
                        "word_type": 14,
                        "is_n1": True,
                        "discuss_video_count": 1,
                    },
                    {
                        "word": "厦门新热点",
                        "hot_value": 987654,
                        "video_count": 123,
                        "event_time": 1_700_000_000,
                        "sentence_id": "sentence-1",
                        "label_name": "新",
                    },
                    {"word": "第二条热点", "hot_value": "456789"},
                ]
            }
        }


class FakeHotFetcher:
    def __init__(self, items):
        self.items = items
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def fetch_hot_rank(self):
        self.calls += 1
        return self.items


@pytest.mark.asyncio
async def test_hot_rank_response_is_normalized():
    fetcher = DouyinMonitorFetcher()
    fetcher._client = FakeHotClient()

    items = await fetcher._fetch_hot_rank_once()

    assert [item["rank"] for item in items] == [None, 1, 2]
    assert items[0]["word"] == "一条巷子里的中国智慧"
    assert items[0]["is_pinned"] is True
    assert items[0]["video_count"] == 1
    assert items[1]["word"] == "厦门新热点"
    assert items[1]["hot_value"] == 987654
    assert items[1]["label"] == "新"
    assert items[1]["is_pinned"] is False
    assert items[1]["search_url"].startswith("https://www.douyin.com/search/")


@pytest.mark.asyncio
async def test_hot_rank_uses_short_cache():
    service = MonitorService()
    fetcher = FakeHotFetcher([
        {
            "rank": 1,
            "is_pinned": False,
            "word": "测试热点",
            "hot_value": 100,
            "video_count": 0,
            "event_time": 0,
            "sentence_id": "1",
            "label": "",
            "search_url": "https://www.douyin.com/search/test",
        }
    ])

    first = await service.get_hot_rank(fetcher=fetcher)
    second = await service.get_hot_rank(fetcher=fetcher)

    assert first["cached"] is False
    assert second["cached"] is True
    assert fetcher.calls == 1
