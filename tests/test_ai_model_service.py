import json

import httpx
import pytest

from api.services.ai_model_service import AIModelService, AIServiceError, parse_json_response


def test_parse_json_response_accepts_fenced_output():
    assert parse_json_response('```json\n{"ok": true}\n```') == {"ok": True}
    assert parse_json_response('prefix [{"id": "a"}]\nsuffix') == [{"id": "a"}]


@pytest.mark.asyncio
async def test_ai_model_service_lists_models_and_generates_json():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "Qwen3.8-27B-FP8"}]}, request=request)
        if request.url.path.endswith("/chat/completions"):
            assert request.headers["authorization"] == "Bearer test-key"
            payload = json.loads(request.content)
            assert payload["model"] == "Qwen3.8-27B-FP8"
            return httpx.Response(
                200,
                json={
                    "model": "Qwen3.8-27B-FP8",
                    "choices": [{"message": {"content": '```json\n{"ok": true}\n```'}, "finish_reason": "stop"}],
                    "usage": {"total_tokens": 10},
                },
                request=request,
            )
        return httpx.Response(404, json={"error": {"message": "not found"}}, request=request)

    service = AIModelService(
        config_data={
            "enabled": True,
            "provider": "openai_compatible",
            "base_url": "http://model.local/v1",
            "api_key": "test-key",
            "model": "Qwen3.8-27B-FP8",
            "timeout_seconds": 5,
            "max_tokens": 256,
            "temperature": 0.2,
            "max_retries": 0,
        },
        transport=httpx.MockTransport(handler),
    )

    assert await service.list_models() == ["Qwen3.8-27B-FP8"]
    assert await service.generate_json(system_prompt="test", user_prompt="test") == {"ok": True}


@pytest.mark.asyncio
async def test_ai_model_service_rejects_disabled_configuration():
    service = AIModelService(config_data={"enabled": False})

    with pytest.raises(AIServiceError) as error:
        await service.list_models()

    assert error.value.code == "disabled"
