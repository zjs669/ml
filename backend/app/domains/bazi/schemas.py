"""四柱引擎的入参 / 出参结构（文档 6.6 ChartEngine 契约）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.domains.bazi.constants import DayBoundary, SolarTimeMethod, YearBoundary


class Convention(BaseModel):
    """排盘口径。任何一项都不允许"隐式默认"——全部回显并随命盘存档。"""

    year_boundary: YearBoundary = "lichun"
    day_boundary: DayBoundary = "zi_hour_policy_a"
    solar_time: SolarTimeMethod = "none"
    school: str = "default_v1"
    five_element_weight: Literal["weight-v1"] = "weight-v1"
    #: 神煞范围：common=10 类无争议，extended=额外算勾绞/童子（起法有分歧）
    shensha_variant: Literal["common", "extended"] = "common"

    model_config = {"extra": "forbid"}


class BaziInput(BaseModel):
    calendar: Literal["gregorian"] = "gregorian"
    birth_datetime: datetime
    timezone: str = "Asia/Shanghai"
    longitude: float | None = Field(default=None, ge=-180, le=180)
    time_known: bool = True
    gender: Literal["male", "female", "unknown"] = "unknown"
    #: 可选：流年展示窗口的起始公历年（含）。不传则不计算流年，
    #: 保证「同一输入同一结果」——不会因为今天是哪一年而偷偷变化。
    liunian_start_year: int | None = Field(default=None, ge=1800, le=2200)
    #: 流年条数，默认 10 年
    liunian_years: int = Field(default=10, ge=1, le=30)

    @field_validator("birth_datetime")
    @classmethod
    def _naive_only(cls, value: datetime) -> datetime:
        # 输入必须是"当地钟表时间"，时区由 timezone 字段单独给出，避免双重换算
        if value.tzinfo is not None:
            raise ValueError("birth_datetime 必须是不带时区的当地时间，时区请用 timezone 字段")
        if not 1800 <= value.year <= 2200:
            raise ValueError("仅支持 1800-2200 年之间的出生时间")
        return value

    model_config = {"extra": "forbid"}


class ChartResult(BaseModel):
    """统一排盘结果。任何术数模块都返回这个外壳，AI 无权修改 chart_facts。"""

    domain: str
    algorithm_version: str
    input_summary: dict[str, Any]
    convention: dict[str, Any]
    chart_facts: dict[str, Any]
    triggered_rules: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
