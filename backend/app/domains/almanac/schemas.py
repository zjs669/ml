"""黄历入参 / 口径结构。

黄历的输入是一个「日子」，不是出生时间。三件事会影响结果：
- 用哪一天（可显式给时区，按当地日期取日）；
- 是否个性化（给出生日期则额外标注日主与生肖，仅作对照，不参与宜忌判定）；
- 时辰吉凶的时段划分（`shichen` 按十二时辰，`hour` 按 24 小时）。

红线：只列传统黄历条目（宜、忌、值星、星宿、神煞、方位），
不输出「今天适合结婚」这类结论，也不输出任何灾祸断言。
"""

from __future__ import annotations

from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MIN_YEAR = 1800
MAX_YEAR = 2200


class AlmanacConvention(BaseModel):
    """黄历口径。全部字段回显到 `ChartResult.convention`。"""

    #: 本版本只实现「通书日级条目」一种口径
    school: Literal["tongshu_daily_v1"] = "tongshu_daily_v1"
    #: 日界：黄历按自然日（00:00 换日），不采用四柱的 23:00 换日
    day_boundary: Literal["midnight"] = "midnight"
    #: 时辰吉凶的时段粒度
    hour_granularity: Literal["shichen"] = "shichen"

    model_config = {"extra": "forbid"}


class AlmanacInput(BaseModel):
    #: 目标公历日期（只取年月日）
    date: Date
    timezone: str = "Asia/Shanghai"
    #: 可选：个性化对照用的出生日期（只取年月日，不参与宜忌判定）
    birth_date: Date | None = None

    @field_validator("date", "birth_date")
    @classmethod
    def _year_range(cls, value: Date | None) -> Date | None:
        if value is None:
            return None
        if not MIN_YEAR <= value.year <= MAX_YEAR:
            raise ValueError(f"仅支持 {MIN_YEAR}-{MAX_YEAR} 年之间的日期")
        return value

    @model_validator(mode="after")
    def _birth_not_after_date(self) -> "AlmanacInput":
        if self.birth_date and self.birth_date > self.date:
            raise ValueError("birth_date 不能晚于查询日期")
        return self

    model_config = {"extra": "forbid"}


class AlmanacCalculateIn(AlmanacInput):
    convention: AlmanacConvention = Field(default_factory=AlmanacConvention)
