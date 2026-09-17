# -*- coding: utf-8 -*-
"""Schemas for AI topic and lifecycle analysis."""

from typing import Literal

from pydantic import BaseModel, Field


class AIAnalysisRequest(BaseModel):
    account_id: int = Field(gt=0)
    time_range: Literal["24h", "7d", "30d", "all"] = "30d"
    post_limit: int = Field(default=20, ge=1, le=200)
    force: bool = False
