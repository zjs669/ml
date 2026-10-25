"""命盘相关出入参。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.domains.bazi.schemas import BaziInput, Convention


class CalculateIn(BaziInput):
    convention: Convention = Field(default_factory=Convention)


class SaveChartIn(CalculateIn):
    title: str | None = Field(default=None, max_length=120)
    delete_after_days: int | None = Field(default=None, ge=1, le=365)


class ChartListItem(BaseModel):
    id: int
    title: str | None
    domain: str
    created_at: datetime
    algorithm_version: str
    day_master: str | None = None
    pillars_text: str | None = None


class ChartPage(BaseModel):
    items: list[ChartListItem]
    total: int
    page: int
    size: int


class ChartOut(BaseModel):
    id: int
    title: str | None
    domain: str
    created_at: datetime
    updated_at: datetime
    algorithm_version: str
    convention: dict[str, Any]
    input_summary: dict[str, Any]
    chart_facts: dict[str, Any]
    triggered_rules: list[dict[str, Any]]
    warnings: list[str]
    source_refs: list[dict[str, Any]]
    share_token: str | None = None


class ChartPatchIn(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    visibility: Literal["private", "link"] | None = None
    delete_after_days: int | None = Field(default=None, ge=1, le=365)

    model_config = {"extra": "forbid"}


class NoteIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)

    model_config = {"extra": "forbid"}


class NoteOut(BaseModel):
    id: int
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ShareIn(BaseModel):
    expires_in_days: int = Field(default=7, ge=1, le=30)
    redact_level: Literal["basic", "full"] = "basic"

    model_config = {"extra": "forbid"}


class ShareOut(BaseModel):
    token: str
    expires_at: datetime
    note: str = "链接仅展示一次，请自行保存；可随时撤销。"


class SharePreview(BaseModel):
    """脱敏预览：不含出生精确时刻，不含 owner 信息。"""

    title: str | None
    domain: str
    pillars_text: str
    chart_facts: dict[str, Any]
    triggered_rules: list[dict[str, Any]]
    warnings: list[str]
    algorithm_version: str
    convention: dict[str, Any]
    expires_at: datetime
