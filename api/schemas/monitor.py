# -*- coding: utf-8 -*-
"""Schemas for the single-account monitor module."""

from typing import Literal

from pydantic import BaseModel, Field


class MonitorAccountConfigRequest(BaseModel):
    sec_user_id: str
    display_name: str = ""
    profile_url: str = ""
    enabled: bool = True
    discover_interval_minutes: int = Field(default=30, ge=1, le=360)


class MonitorAccountUpdateRequest(BaseModel):
    sec_user_id: str | None = None
    display_name: str | None = None
    profile_url: str | None = None
    enabled: bool | None = None
    discover_interval_minutes: int | None = Field(default=None, ge=1, le=360)


class MonitorAlertStatusRequest(BaseModel):
    alert_ids: list[int] = Field(min_length=1)
    status: Literal["unread", "read", "resolved", "ignored"]
