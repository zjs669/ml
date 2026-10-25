"""奇门遁甲入参 / 口径结构。

时家奇门只需要「起局时刻 + 时区」两样输入：年月日时四柱、节气、符头全部由引擎推算，
不接受手工指定局数——手工指定会让「同一问题的盘」无法复核，也让回归测试失去意义。

口径只保留一个学派，其余取值直接校验失败而不是静默套用：
`school` 固定 `chaibu_zhuanpan_v1`（时家转盘拆补法）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

#: 与四柱、紫微、六爻保持一致的年份范围
MIN_YEAR = 1800
MAX_YEAR = 2200


class QimenConvention(BaseModel):
    """奇门口径。全部字段回显到 `ChartResult.convention`。"""

    #: 本版本只实现时家转盘拆补法
    school: Literal["chaibu_zhuanpan_v1"] = "chaibu_zhuanpan_v1"
    #: 阴阳遁以二十四节气为界（冬至→芒种阳遁，夏至→大雪阴遁）
    dun_basis: Literal["solar_term"] = "solar_term"
    #: 上中下元按符头（甲己日）地支拆补，不用置闰法
    yuan_method: Literal["chaibu"] = "chaibu"
    #: 中五宫寄坤二宫（天禽随天芮）
    center_palace: Literal["kun2"] = "kun2"
    #: 日柱边界：影响符头与旬空，与四柱同口径
    day_boundary: Literal["zi_hour_policy_a", "zi_hour_policy_b"] = "zi_hour_policy_a"

    model_config = {"extra": "forbid"}


class QimenInput(BaseModel):
    cast_datetime: datetime
    timezone: str = "Asia/Shanghai"

    @field_validator("cast_datetime")
    @classmethod
    def _naive_local_time(cls, value: datetime) -> datetime:
        if value.tzinfo is not None:
            raise ValueError("cast_datetime 必须是不带时区的当地时间，时区请用 timezone 字段")
        if not MIN_YEAR <= value.year <= MAX_YEAR:
            raise ValueError(f"仅支持 {MIN_YEAR}-{MAX_YEAR} 年之间的起局时间")
        return value

    model_config = {"extra": "forbid"}


class QimenCalculateIn(QimenInput):
    convention: QimenConvention = Field(default_factory=QimenConvention)
