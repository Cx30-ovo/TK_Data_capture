from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.routers.ai as ai_router_module
from api.services.ai_model_service import AIServiceError


def make_client():
    app = FastAPI()
    app.include_router(ai_router_module.router, prefix="/api")
    return TestClient(app)


def test_ai_status_does_not_expose_api_key(monkeypatch):
    monkeypatch.setattr(
        ai_router_module.ai_model_service,
        "get_status",
        lambda: {
            "enabled": True,
            "configured": True,
            "provider": "openai_compatible",
            "base_url": "http://model.local/v1",
            "model": "Qwen3.8-27B-FP8",
            "api_key_configured": True,
        },
    )

    response = make_client().get("/api/monitor/ai/status")
    assert response.status_code == 200
    assert response.json()["model"] == "Qwen3.8-27B-FP8"
    assert "api_key" not in response.json()


def test_ai_topic_analysis_route(monkeypatch):
    async def resolve_account(account_id):
        assert account_id == 7
        return "sec_ai_router"

    async def analyze_topics(**kwargs):
        assert kwargs["sec_user_id"] == "sec_ai_router"
        assert kwargs["scope"] == {"time_range": "7d", "post_limit": 20}
        assert kwargs["force"] is True
        return {"id": 1, "status": "done", "result": {"summary": "ok"}}

    monkeypatch.setattr(ai_router_module, "_resolve_account_sec_user_id", resolve_account)
    monkeypatch.setattr(ai_router_module.ai_analysis_service, "analyze_topics", analyze_topics)

    response = make_client().post(
        "/api/monitor/ai/analyze/topics",
        json={"account_id": 7, "time_range": "7d", "post_limit": 20, "force": True},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "done"


def test_ai_result_list_detail_and_delete_routes(monkeypatch):
    item = SimpleNamespace(id=9, analysis_type="topic", status="done")
    serialized = {"id": 9, "analysis_type": "topic", "status": "done", "result": {"summary": "ok"}}

    async def list_results(**kwargs):
        assert kwargs["status"] == "done"
        return [item]

    async def get_result(result_id):
        assert result_id == 9
        return item

    async def delete_result(result_id):
        assert result_id == 9
        return True

    monkeypatch.setattr(ai_router_module.ai_analysis_repository, "list_results", list_results)
    monkeypatch.setattr(ai_router_module.ai_analysis_repository, "get_result", get_result)
    monkeypatch.setattr(ai_router_module.ai_analysis_repository, "delete_result", delete_result)
    def serialize_result(value, cache_hit=False):
        assert cache_hit is True
        return serialized

    monkeypatch.setattr(ai_router_module.ai_analysis_service, "serialize_result", serialize_result)

    client = make_client()
    listed = client.get("/api/monitor/ai/results?status=done")
    assert listed.status_code == 200
    assert listed.json()["results"][0]["id"] == 9

    detail = client.get("/api/monitor/ai/results/9")
    assert detail.status_code == 200
    assert detail.json()["result"]["summary"] == "ok"

    deleted = client.delete("/api/monitor/ai/results/9")
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "ok"


def test_ai_route_maps_disabled_provider_to_service_unavailable(monkeypatch):
    async def resolve_account(account_id):
        return "sec_ai_router"

    async def analyze_topics(**kwargs):
        raise AIServiceError("AI analysis is disabled.", code="disabled")

    monkeypatch.setattr(ai_router_module, "_resolve_account_sec_user_id", resolve_account)
    monkeypatch.setattr(ai_router_module.ai_analysis_service, "analyze_topics", analyze_topics)

    response = make_client().post(
        "/api/monitor/ai/analyze/topics",
        json={"account_id": 7, "time_range": "30d", "post_limit": 20},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "disabled"
