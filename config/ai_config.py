# -*- coding: utf-8 -*-
"""Configuration for the optional AI analysis provider."""

import os


def _as_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: str, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


AI_ENABLED = _as_bool(os.getenv("AI_ENABLED", "false"), default=False)
AI_PROVIDER = os.getenv("AI_PROVIDER", "openai_compatible").strip().lower()
AI_BASE_URL = os.getenv("AI_BASE_URL", "").strip().rstrip("/")
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
AI_MODEL = os.getenv("AI_MODEL", "").strip()
AI_TIMEOUT_SECONDS = max(1.0, _as_float(os.getenv("AI_TIMEOUT_SECONDS"), 300.0))
AI_MAX_TOKENS = max(1, _as_int(os.getenv("AI_MAX_TOKENS"), 8192))
AI_TEMPERATURE = max(0.0, min(2.0, _as_float(os.getenv("AI_TEMPERATURE"), 0.2)))
AI_MAX_RETRIES = max(0, _as_int(os.getenv("AI_MAX_RETRIES"), 2))
AI_ANALYSIS_CACHE_TTL_HOURS = max(1, _as_int(os.getenv("AI_ANALYSIS_CACHE_TTL_HOURS"), 24))
AI_ENABLE_THINKING = _as_bool(os.getenv("AI_ENABLE_THINKING", "false"), default=False)


ai_config = {
    "enabled": AI_ENABLED,
    "provider": AI_PROVIDER,
    "base_url": AI_BASE_URL,
    "api_key": AI_API_KEY,
    "model": AI_MODEL,
    "timeout_seconds": AI_TIMEOUT_SECONDS,
    "max_tokens": AI_MAX_TOKENS,
    "temperature": AI_TEMPERATURE,
    "max_retries": AI_MAX_RETRIES,
    "cache_ttl_hours": AI_ANALYSIS_CACHE_TTL_HOURS,
    "enable_thinking": AI_ENABLE_THINKING,
}


__all__ = [
    "AI_ENABLED",
    "AI_PROVIDER",
    "AI_BASE_URL",
    "AI_API_KEY",
    "AI_MODEL",
    "AI_TIMEOUT_SECONDS",
    "AI_MAX_TOKENS",
    "AI_TEMPERATURE",
    "AI_MAX_RETRIES",
    "AI_ANALYSIS_CACHE_TTL_HOURS",
    "AI_ENABLE_THINKING",
    "ai_config",
]
