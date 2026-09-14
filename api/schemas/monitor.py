# -*- coding: utf-8 -*-
"""Schemas for the single-account monitor module."""

from pydantic import BaseModel, Field


class MonitorAccountConfigRequest(BaseModel):
    sec_user_id: str
    profile_url: str = ""
    enabled: bool = True
    discover_interval_minutes: int = Field(default=30, ge=1, le=360)
