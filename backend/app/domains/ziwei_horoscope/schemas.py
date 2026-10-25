"""紫微运限入参 / 口径结构。

运限不是另起一张盘，而是在本命盘上叠时间层。因此入参与 `ziwei` 完全一致
（`birth_datetime` / `timezone` / `gender` / `calendar`），只多三件事：
- `target_date`：要看哪一天；
- `target_hour`：要看哪个时辰（流时层需要）；
- `convention`：流月/流日/流时的起宫法，各派不同，必须显式选择。

红线：只输出各层落在哪一宫、该宫有哪些星，不输出吉凶、不断事件。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MIN_YEAR = 1800
MAX_YEAR = 2200


class HoroscopeConvention(BaseModel):
    """运限口径。全部字段回显到 `ChartResult.convention`。"""

    #: 本命盘口径沿用三合派单一口径，不在这里重复开关
    school: Literal["sanhe_default_v1"] = "sanhe_default_v1"
    #: 流月起宫法：doujun = 斗君法（流年支起正月逆数生月，再起子时顺数生时）
    monthly_start: Literal["doujun"] = "doujun"
    #: 流日：自流月宫起初一顺行
    daily_start: Literal["from_monthly"] = "from_monthly"
    #: 流时：自流日宫起子时顺行
    hourly_start: Literal["from_daily"] = "from_daily"
    #: 年龄口径：虚岁（与本命盘大限一致）
    age_basis: Literal["virtual_age"] = "virtual_age"

    model_config = {"extra": "forbid"}


class HoroscopeInput(BaseModel):
    #: 本命盘入参（与 ziwei 域同构）
    birth_datetime: datetime
    timezone: str = "Asia/Shanghai"
    gender: Literal["male", "female", "unknown"] = "unknown"
    calendar: Literal["gregorian", "lunar"] = "gregorian"
    is_leap_month: bool = False
    time_known: bool = True
    #: 运限目标日期（只取年月日）
    target_date: datetime
    #: 运限目标时辰：0–23 小时
    target_hour: int = Field(default=12, ge=0, le=23)

    @field_validator("birth_datetime", "target_date")
    @classmethod
    def _naive_local_time(cls, value: datetime) -> datetime:
        if value.tzinfo is not None:
            raise ValueError("时间必须是不带时区的当地时间，时区请用 timezone 字段")
        if not MIN_YEAR <= value.year <= MAX_YEAR:
            raise ValueError(f"仅支持 {MIN_YEAR}-{MAX_YEAR} 年之间的日期")
        return value

    @model_validator(mode="after")
    def _target_not_before_birth(self) -> "HoroscopeInput":
        if self.target_date < self.birth_datetime:
            raise ValueError("target_date 不能早于出生时间")
        return self

    model_config = {"extra": "forbid"}


class HoroscopeCalculateIn(HoroscopeInput):
    convention: HoroscopeConvention = Field(default_factory=HoroscopeConvention)
