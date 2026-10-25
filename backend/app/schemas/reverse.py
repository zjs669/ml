"""四柱反查（干支 → 公历日期）的入参 / 出参。

反查是纯计算：不落库、不写日志、不要求登录。
柱位越少结果越多，`truncated` 会明确提示；无解时 `diagnosis` 逐柱给出排查线索，
而不是丢一个空数组让用户自己猜记错了哪一柱。
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domains.bazi.schemas import Convention
from app.domains.calendar_core.jiazi import BRANCHES, STEMS

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
