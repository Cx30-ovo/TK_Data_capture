"""Business account metadata, independent of collection configuration."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MatrixAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    identity_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    role: Literal["unassigned", "owned", "competitor"]
    group: str = Field(default="", max_length=50)
    competitor_ids: list[int] = Field(default_factory=list, max_length=100)

    @field_validator("group")
    @classmethod
    def clean_group(cls, value: str) -> str:
        return value.strip()

    @field_validator("competitor_ids")
    @classmethod
    def unique_ids(cls, value: list[int]) -> list[int]:
        if any(item < 1 for item in value) or len(value) != len(set(value)):
            raise ValueError("竞品 ID 必须为不重复的正整数")
        return sorted(value)
