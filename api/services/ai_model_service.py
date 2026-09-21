# -*- coding: utf-8 -*-
"""Unified client for OpenAI-compatible model providers."""

import asyncio
import json
import re
import time
from typing import Any, Mapping, Optional, Sequence

import httpx

import config


_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class AIServiceError(RuntimeError):
    """A sanitized error raised by the AI service layer."""

    def __init__(self, message: str, *, code: str = "ai_error", status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def parse_json_response(content: str) -> Any:
    """Parse a JSON object or array from model text, including fenced output."""
    if not isinstance(content, str) or not content.strip():
        raise ValueError("AI response content is empty.")

    text = content.strip()
    if text.startswith("```"):
        text = _JSON_FENCE_RE.sub("", text).strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, (dict, list)):
            return parsed
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character not in "[{":
            continue
        try:
            parsed, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, (dict, list)):
            return parsed

    raise ValueError("AI response does not contain a valid JSON object or array.")


class AIModelService:
    """Small provider-neutral client used by the AI analysis services."""

    def __init__(
        self,
        config_data: Optional[Mapping[str, Any]] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self._config = dict(config_data or config.ai_config)
        self._transport = transport

    def get_status(self) -> dict[str, Any]:
        return {
            "enabled": bool(self._config.get("enabled")),
            "configured": self._is_configured(),
            "provider": str(self._config.get("provider") or ""),
            "base_url": str(self._config.get("base_url") or ""),
            "model": str(self._config.get("model") or ""),
            "api_key_configured": bool(self._config.get("api_key")),
            "timeout_seconds": float(self._config.get("timeout_seconds") or 120.0),
            "max_tokens": int(self._config.get("max_tokens") or 2048),
            "temperature": float(self._config.get("temperature") or 0.2),
            "enable_thinking": bool(self._config.get("enable_thinking", False)),
        }

    def _is_configured(self) -> bool:
        return bool(
            self._config.get("enabled")
            and str(self._config.get("base_url") or "").strip()
            and str(self._config.get("model") or "").strip()
        )

    def _require_configured(self) -> None:
        if not self._config.get("enabled"):
            raise AIServiceError("AI analysis is disabled. Set AI_ENABLED=true in .env.", code="disabled")
        if not str(self._config.get("base_url") or "").strip():
            raise AIServiceError("AI_BASE_URL is not configured.", code="not_configured")
        if not str(self._config.get("model") or "").strip():
            raise AIServiceError("AI_MODEL is not configured.", code="not_configured")

    def _endpoint(self, path: str) -> str:
        base_url = str(self._config.get("base_url") or "").rstrip("/")
        return f"{base_url}/{path.lstrip('/')}"

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        api_key = str(self._config.get("api_key") or "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _redact(self, value: str) -> str:
        api_key = str(self._config.get("api_key") or "").strip()
        if api_key:
            return value.replace(api_key, "[redacted]")
        return value

    def _response_error(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                error = payload.get("error")
                if isinstance(error, dict):
                    detail = error.get("message") or error.get("detail") or error.get("code")
                else:
                    detail = payload.get("detail") or payload.get("message")
            else:
                detail = None
        except ValueError:
            detail = response.text[:500]
        return self._redact(str(detail or f"HTTP {response.status_code}"))[:500]

    async def _request(self, method: str, path: str, *, json_body: Optional[dict[str, Any]] = None) -> Any:
        self._require_configured()
        timeout = float(self._config.get("timeout_seconds") or 120.0)
        max_retries = max(0, int(self._config.get("max_retries") or 0))
        last_error: Optional[AIServiceError] = None

        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout, transport=self._transport) as client:
                    response = await client.request(method, self._endpoint(path), headers=self._headers(), json=json_body)
                    response.raise_for_status()
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise AIServiceError("AI provider returned invalid JSON.", code="invalid_response") from exc
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                error = AIServiceError(
                    f"AI provider returned HTTP {status_code}: {self._response_error(exc.response)}",
                    code="http_error",
                    status_code=status_code,
                )
                if status_code < 500:
                    raise error from exc
                last_error = error
            except httpx.TimeoutException as exc:
                last_error = AIServiceError("AI provider request timed out.", code="timeout")
                last_error.__cause__ = exc
            except httpx.RequestError as exc:
                last_error = AIServiceError(f"AI provider connection failed: {self._redact(str(exc))}", code="connection_error")
                last_error.__cause__ = exc
            except AIServiceError:
                raise

            if attempt < max_retries:
                await asyncio.sleep(min(1.0 * (2 ** attempt), 4.0))

        if last_error is not None:
            raise last_error
        raise AIServiceError("AI provider request failed.", code="unknown")

    async def list_models(self) -> list[str]:
        payload = await self._request("GET", "/models")
        rows = payload.get("data") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            return []
        models = []
        for item in rows:
            model_id = item.get("id") if isinstance(item, dict) else item
            if model_id:
                models.append(str(model_id))
        return sorted(set(models))

    async def chat(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        if not messages:
            raise ValueError("At least one chat message is required.")

        payload: dict[str, Any] = {
            "model": str(self._config.get("model") or ""),
            "messages": [dict(message) for message in messages],
            "temperature": float(self._config.get("temperature") or 0.2) if temperature is None else temperature,
            "max_tokens": int(self._config.get("max_tokens") or 2048) if max_tokens is None else max_tokens,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        if self._config.get("enable_thinking") is False:
            payload["chat_template_kwargs"] = {"enable_thinking": False}

        started_at = time.monotonic()
        data = await self._request("POST", "/chat/completions", json_body=payload)
        elapsed = time.monotonic() - started_at
        choices = data.get("choices") if isinstance(data, dict) else None
        choice = choices[0] if isinstance(choices, list) and choices else {}
        message = choice.get("message") if isinstance(choice, dict) else {}
        content = message.get("content") if isinstance(message, dict) else None
        reasoning_content = message.get("reasoning_content") if isinstance(message, dict) else None
        finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
        if not isinstance(content, str) or not content.strip():
            if finish_reason == "length":
                raise AIServiceError("AI provider exhausted max_tokens before final message content.", code="output_truncated")
            raise AIServiceError("AI provider response does not contain message content.", code="invalid_response")

        return {
            "content": content,
            "model": data.get("model") or self._config.get("model"),
            "finish_reason": finish_reason,
            "reasoning_content": reasoning_content if isinstance(reasoning_content, str) else None,
            "usage": data.get("usage") if isinstance(data, dict) else {},
            "elapsed_seconds": round(elapsed, 3),
        }

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[dict[str, str]] = None,
    ) -> Any:
        messages = [
            {
                "role": "system",
                "content": f"{system_prompt.strip()}\n\n只输出一个合法 JSON 对象或数组，不要使用 Markdown 代码块，不要添加解释文字。",
            },
            {"role": "user", "content": user_prompt.strip()},
        ]
        response = await self.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format if response_format is not None else {"type": "json_object"},
        )
        if response.get("finish_reason") == "length":
            raise AIServiceError("AI output was truncated by max_tokens before the JSON was complete.", code="output_truncated")
        try:
            return parse_json_response(response["content"])
        except ValueError as exc:
            raise AIServiceError(f"AI returned invalid structured JSON: {exc}", code="invalid_json") from exc


ai_model_service = AIModelService()


__all__ = ["AIServiceError", "AIModelService", "ai_model_service", "parse_json_response"]
