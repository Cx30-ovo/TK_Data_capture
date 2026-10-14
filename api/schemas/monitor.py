# -*- coding: utf-8 -*-
"""Schemas for the single-account monitor module."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from tools.douyin_account_identity import normalize_account_profile, parse_account_identity


class MonitorAccountConfigRequest(BaseModel):
    sec_user_id: str
    display_name: str = ""
    profile_url: str = ""
    enabled: bool = True
    snapshots_paused: bool = False
    discover_interval_minutes: int = Field(default=30, ge=1, le=360)

    @model_validator(mode="after")
    def normalize_identity(self):
        self.sec_user_id, self.profile_url = normalize_account_profile(self.sec_user_id, self.profile_url)
        if self.snapshots_paused:
            self.enabled = False
        return self


class MonitorAccountUpdateRequest(BaseModel):
    sec_user_id: str | None = None
    display_name: str | None = None
    profile_url: str | None = None
    enabled: bool | None = None
    snapshots_paused: bool | None = None
    discover_interval_minutes: int | None = Field(default=None, ge=1, le=360)

    @model_validator(mode="after")
    def normalize_identity(self):
        if self.sec_user_id is not None:
            self.sec_user_id, profile = normalize_account_profile(self.sec_user_id, self.profile_url or "")
            if self.profile_url is not None:
                self.profile_url = profile
        elif self.profile_url is not None:
            self.profile_url = f"https://www.douyin.com/user/{parse_account_identity(self.profile_url)}"
        return self


class MonitorAccountBatchRequest(BaseModel):
    account_ids: list[int] = Field(min_length=1, max_length=200)
    discover_interval_minutes: int = Field(ge=1, le=360)


class MonitorAlertStatusRequest(BaseModel):
    alert_ids: list[int] = Field(min_length=1)
    status: Literal["unread", "read", "resolved", "ignored"]
