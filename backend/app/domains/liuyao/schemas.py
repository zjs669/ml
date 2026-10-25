"""六爻入参 / 口径结构。

与四柱、紫微不同，六爻的输入不是「出生时间」而是「起卦方式 + 起卦时刻」：

- `method="coins"`：三枚铜钱六次，用 `seed` 复现（同 seed 同结果，便于校验与回归）；
- `method="time"`：时间起卦，用农历年支、月、日、时支取数，只产生一个动爻；
- `method="manual"`：手动填六爻数字（6 老阴 / 7 少阳 / 8 少阴 / 9 老阳），自下而上。

`question` 只写入 `input_summary`，`store_question=False` 时连它也一并丢弃。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MIN_YEAR = 1800
MAX_YEAR = 2200
#: 占问原文上限，超出直接拒绝而不是静默截断
MAX_QUESTION_LENGTH = 200
LINE_VALUES = (6, 7, 8, 9)


class LiuyaoConvention(BaseModel):
    """六爻口径。全部回显到 `ChartResult.convention`。"""

    #: 本版本只实现京房纳甲；其他值校验失败，不静默套用
    school: Literal["jingfang_najia_v1"] = "jingfang_najia_v1"
    #: 月建日辰依赖「日」的边界，23:00 归属哪个日与四柱同口径
    day_boundary: Literal["zi_hour_policy_a", "zi_hour_policy_b"] = "zi_hour_policy_a"
    #: 月建按节气（十二节）划分，不按农历月
    month_basis: Literal["solar_term"] = "solar_term"

    model_config = {"extra": "forbid"}


class LiuyaoInput(BaseModel):
    method: Literal["coins", "time", "manual"] = "coins"
    cast_datetime: datetime
    timezone: str = "Asia/Shanghai"
    #: 仅 method="coins" 使用；不填时由起卦时刻派生，保证同刻可复现
    seed: int | None = None
    #: 仅 method="manual" 使用，自下而上 6 个 6/7/8/9
    lines: list[int] | None = None
    question: str | None = None
    store_question: bool = True

    @field_validator("cast_datetime")
    @classmethod
    def _naive_local_time(cls, value: datetime) -> datetime:
        if value.tzinfo is not None:
            raise ValueError("cast_datetime 必须是不带时区的当地时间，时区请用 timezone 字段")
        if not MIN_YEAR <= value.year <= MAX_YEAR:
            raise ValueError(f"仅支持 {MIN_YEAR}-{MAX_YEAR} 年之间的起卦时间")
        return value

    @field_validator("question")
    @classmethod
    def _question_length(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        if len(text) > MAX_QUESTION_LENGTH:
            raise ValueError(f"占问原文不超过 {MAX_QUESTION_LENGTH} 字")
        return text

    @field_validator("seed")
    @classmethod
    def _seed_range(cls, value: int | None) -> int | None:
        if value is not None and not 0 <= value < 2**32:
            raise ValueError("seed 必须是 0 到 2^32-1 之间的整数")
        return value

    @model_validator(mode="after")
    def _method_payload(self) -> LiuyaoInput:
        if self.method == "manual":
            if not self.lines or len(self.lines) != 6:
                raise ValueError("手动起卦必须提供自下而上的 6 个数字")
            for index, value in enumerate(self.lines):
                if value not in LINE_VALUES:
                    raise ValueError(
                        f"第 {index + 1} 爻的取值 {value} 不合法，只接受 6/7/8/9"
                    )
        elif self.lines is not None:
            raise ValueError("lines 只在 method=manual 时可用")
        return self

    model_config = {"extra": "forbid"}


class LiuyaoCalculateIn(LiuyaoInput):
    convention: LiuyaoConvention = Field(default_factory=LiuyaoConvention)
