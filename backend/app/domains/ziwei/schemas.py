"""紫微斗数入参 / 口径结构。

入参刻意保持与四柱一致的字段名（`birth_datetime` / `timezone` / `time_known` / `gender`），
前端表单与「保存命盘」接口无需为紫微另写一套。

`calendar="lunar"` 时 `birth_datetime` 的年月日按农历解读，`is_leap_month=true` 表示闰月；
`calendar="gregorian"` 时按公历解读，引擎内部先转农历再安星。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

#: lunar-python 覆盖 1800–2200，与四柱引擎的年份范围保持一致
MIN_YEAR = 1800
MAX_YEAR = 2200


class ZiweiConvention(BaseModel):
    """紫微口径。全部字段回显到 `ChartResult.convention`，不做隐式默认。"""

    #: 安星基准是农历，不是节气
    calendar_basis: Literal["lunar"] = "lunar"
    #: 年干支以正月初一为界（紫微不用立春）
    year_boundary: Literal["lunar_new_year"] = "lunar_new_year"
    #: 本版本只实现三合派，其他值一律校验失败而不是静默套用
    school: Literal["sanhe_default_v1"] = "sanhe_default_v1"
    #: 闰月按本月计（不并入下月）
    leap_month: Literal["as_current_month"] = "as_current_month"
    #: 23:00–24:00 按当日之子时计（不跳到次日）
    zi_hour: Literal["same_day"] = "same_day"

    model_config = {"extra": "forbid"}


class ZiweiInput(BaseModel):
    calendar: Literal["gregorian", "lunar"] = "gregorian"
    birth_datetime: datetime
    #: 仅 calendar="lunar" 时有意义
    is_leap_month: bool = False
    timezone: str = "Asia/Shanghai"
    time_known: bool = True
    gender: Literal["male", "female", "unknown"] = "unknown"
    #: 可选：虚岁年龄。给定时才计算「大限四化」，不给就不猜。
    review_age: int | None = Field(default=None, ge=0, le=120)
    #: 可选：农历年份。给定时才计算「流年四化」与流年命宫。
    review_year: int | None = Field(default=None, ge=MIN_YEAR, le=MAX_YEAR)
    #: 飞星串联深度（1=只看一跳，2=两跳，3=三跳）；只列链路，不推事件
    flying_depth: Literal[1, 2, 3] = 2

    @field_validator("birth_datetime")
    @classmethod
    def _naive_local_time(cls, value: datetime) -> datetime:
        if value.tzinfo is not None:
            raise ValueError("birth_datetime 必须是不带时区的当地时间，时区请用 timezone 字段")
        if not MIN_YEAR <= value.year <= MAX_YEAR:
            raise ValueError(f"仅支持 {MIN_YEAR}-{MAX_YEAR} 年之间的出生时间")
        return value

    @model_validator(mode="after")
    def _leap_flag_only_for_lunar(self) -> ZiweiInput:
        if self.is_leap_month and self.calendar != "lunar":
            raise ValueError("is_leap_month 只在使用农历输入（calendar=lunar）时有效")
        return self

    model_config = {"extra": "forbid"}


class ZiweiCalculateIn(ZiweiInput):
    convention: ZiweiConvention = Field(default_factory=ZiweiConvention)
