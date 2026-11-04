"""Versioned response contract for the first account profile slice."""

from pydantic import BaseModel


class AccountIdentity(BaseModel):
    id: int
    display_name: str
    platform: str


class ProfileWindow(BaseModel):
    start: int
    end: int
    days: int


class ProfileCounts(BaseModel):
    eligible: int
    excluded_status: int
    sampled: int
    with_title: int
    missing_title: int
    truncated: bool


class Evidence(BaseModel):
    post_id: str
    field: str
    snippet: str
    published_at: int


class TitleSignal(BaseModel):
    key: str
    label: str
    count: int
    evidence: list[Evidence]


class Hashtag(BaseModel):
    tag: str
    post_count: int
    evidence: list[Evidence]


class HistogramBin(BaseModel):
    label: str
    count: int


class TitleLength(BaseModel):
    mean: float | None
    median: float | None
    histogram: list[HistogramBin]
    sample_count: int
    excluded_count: int
    extraction_version: str
    rule: str
    evidence: list[dict]


class Publication(BaseModel):
    earliest: int | None
    latest: int | None
    posts_per_day: float


class LifecycleCoverage(BaseModel):
    stage: str
    posts: int


class Coverage(BaseModel):
    observed_posts: int
    without_observation: int
    invalid_observations: int
    lifecycle: list[LifecycleCoverage]


class AccountProfile(BaseModel):
    version: str
    input_sha256: str
    account: AccountIdentity
    window: ProfileWindow
    counts: ProfileCounts
    publication: Publication
    title_length: TitleLength
    signals: list[TitleSignal]
    hashtags: list[Hashtag]
    coverage: Coverage
    limits: list[str]
