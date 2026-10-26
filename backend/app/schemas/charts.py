"""命盘相关出入参：排盘、保存、笔记、分享，以及四柱反查。

反查也在这里，因为它的路由就挂在 charts 下（`/charts/bazi/reverse-search`），
出入参跟着路由走，不需要为 4 个类单开一个文件。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domains.bazi.schemas import BaziInput, Convention
from app.domains.calendar_core.jiazi import BRANCHES, STEMS


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


# ---------------------------------------------------------------- 四柱反查
#
# 四柱反查（干支 → 公历日期）的入参 / 出参。
# 
# 反查是纯计算：不落库、不写日志、不要求登录。
# 柱位越少结果越多，`truncated` 会明确提示；无解时 `diagnosis` 逐柱给出排查线索，
# 而不是丢一个空数组让用户自己猜记错了哪一柱。


MAX_YEARS = 200
POSITION_LABELS = {"year": "年柱", "month": "月柱", "day": "日柱", "hour": "时柱"}


def validate_pillar_text(text: str, label: str) -> str:
    """校验「干支」二字：必须在十干十二支内，且阴阳相配（六十甲子只有 60 个合法组合）。"""
    cleaned = text.strip()
    if len(cleaned) != 2:
        raise ValueError(f"{label}必须是两个字，例如「甲子」，收到「{cleaned}」")
    stem, branch = cleaned[0], cleaned[1]
    if stem not in STEMS:
        raise ValueError(f"{label}天干「{stem}」不在十天干（{'、'.join(STEMS)}）内")
    if branch not in BRANCHES:
        raise ValueError(f"{label}地支「{branch}」不在十二地支（{'、'.join(BRANCHES)}）内")
    if STEMS.index(stem) % 2 != BRANCHES.index(branch) % 2:
        raise ValueError(
            f"{label}「{cleaned}」不是六十甲子中的合法组合（阳干只配阳支、阴干只配阴支）"
        )
    return cleaned


class PillarQuery(BaseModel):
    """待反查的柱位；`None` 表示该柱不参与筛选。"""

    year: str | None = Field(default=None, description="年柱，如「庚午」")
    month: str | None = Field(default=None)
    day: str | None = Field(default=None)
    hour: str | None = Field(default=None)

    model_config = {"extra": "forbid"}

    @field_validator("year", "month", "day", "hour")
    @classmethod
    def _check_pillar(cls, value: str | None, info) -> str | None:
        if value is None or not value.strip():
            return None
        return validate_pillar_text(value, POSITION_LABELS.get(info.field_name, info.field_name))

    @model_validator(mode="after")
    def _at_least_one(self) -> PillarQuery:
        if not any((self.year, self.month, self.day, self.hour)):
            raise ValueError("至少填写一个柱位，否则等同于列出两百年的全部日期")
        return self

    def as_dict(self) -> dict[str, str | None]:
        return {"year": self.year, "month": self.month, "day": self.day, "hour": self.hour}

    def filled(self) -> list[str]:
        return [key for key in ("year", "month", "day", "hour") if getattr(self, key)]


class ReverseSearchIn(BaseModel):
    pillars: PillarQuery
    range_start: date = date(1900, 1, 1)
    range_end: date = date(2100, 12, 31)
    timezone: str = "Asia/Shanghai"
    longitude: float | None = Field(default=None, ge=-180, le=180)
    convention: Convention = Field(default_factory=Convention)
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0, le=100_000)

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _check_range(self) -> ReverseSearchIn:
        if self.range_end < self.range_start:
            raise ValueError("结束日期不能早于开始日期")
        span = (self.range_end - self.range_start).days
        if span > MAX_YEARS * 366:
            raise ValueError(f"反查范围不能超过 {MAX_YEARS} 年，请缩小起止日期")
        return self


class ReverseCandidate(BaseModel):
    """一个命中的钟表日期。`hour_windows` 为空表示该查询未约束时柱。"""

    date: date
    hour_windows: list[str] = Field(default_factory=list)
    pillars: dict[str, str] = Field(default_factory=dict)
    confidence: Literal["exact", "partial"] = "exact"
    notes: list[str] = Field(default_factory=list)


class ReverseSearchOut(BaseModel):
    query: dict[str, str | None]
    convention: dict
    searched_days: int
    total_matches: int
    truncated: bool
    offset: int
    limit: int
    candidates: list[ReverseCandidate] = Field(default_factory=list)
    diagnosis: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    algorithm_version: str
