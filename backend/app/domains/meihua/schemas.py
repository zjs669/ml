"""梅花易数入参 / 口径结构。

梅花易数的输入是「起卦依据」，不是出生时间。本版本支持六种起卦法：
- `time`：年月日时起卦（年支数 + 农历月 + 农历日 → 上卦；再加时支数 → 下卦与动爻）；
- `numbers`：两数或三数报数起卦；
- `text`：字占（字数分上下卦，总笔画数定动爻）；
- `measure`：丈尺尺寸起卦；
- `direction`：方位类象起卦；
- `hexagram`：直接指定上下卦与动爻（校验用）。

口径上会改变结果的只有两件事，因此显式化并回显：
- `time_basis`：年支取农历年支（不取立春换年）；
- `moving_rule`：动爻取「总数除六取余」，余 0 作 6。

红线：只出卦象结构与体用五行关系，不给吉凶结论、不给应期断言。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MIN_YEAR = 1800
MAX_YEAR = 2200
MAX_QUESTION_LENGTH = 200
MAX_TEXT_LENGTH = 40


class MeihuaConvention(BaseModel):
    """梅花易数口径。全部字段回显到 `ChartResult.convention`。"""

    #: 本版本只实现邵雍《梅花易数》通行法（体用生克 + 互错综）
    school: Literal["shaoyong_tongxing_v1"] = "shaoyong_tongxing_v1"
    #: 年支取农历年支，不按立春换年（与四柱的年界不同口径）
    time_basis: Literal["lunar_year_branch"] = "lunar_year_branch"
    #: 动爻：总数除 6 取余，余 0 作上爻
    moving_rule: Literal["mod6_zero_as_six"] = "mod6_zero_as_six"
    #: 体用：动爻所在卦为用，另一卦为体
    body_rule: Literal["moving_is_use"] = "moving_is_use"

    model_config = {"extra": "forbid"}


class MeihuaInput(BaseModel):
    method: Literal["time", "numbers", "text", "measure", "direction", "hexagram"] = "time"

    #: method=time 时必填
    cast_datetime: datetime | None = None
    timezone: str = "Asia/Shanghai"

    #: method=numbers：两数或三数报数
    numbers: list[int] | None = None

    #: method=text：字占原文（不超过 40 字）
    text: str | None = None

    #: method=measure：长度（寸）与宽度（寸），或单一长度
    length_value: int | None = Field(default=None, ge=1, le=9999)
    width_value: int | None = Field(default=None, ge=1, le=9999)

    #: method=direction：方位（八卦方位名）
    direction: str | None = None

    #: method=hexagram：直接给上下卦与动爻
    upper: str | None = None
    lower: str | None = None
    moving_line: int | None = Field(default=None, ge=1, le=6)

    question: str | None = None
    store_question: bool = True

    @field_validator("cast_datetime")
    @classmethod
    def _naive_local_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
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

    @field_validator("text")
    @classmethod
    def _text_length(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = "".join(value.split())
        if not cleaned:
            return None
        if len(cleaned) > MAX_TEXT_LENGTH:
            raise ValueError(f"字占原文不超过 {MAX_TEXT_LENGTH} 字")
        return cleaned

    @model_validator(mode="after")
    def _method_payload(self) -> "MeihuaInput":
        from app.domains.liuyao.constants import TRIGRAM_BITS

        if self.method == "time":
            if self.cast_datetime is None:
                raise ValueError("method=time 时必须提供 cast_datetime")
        elif self.method == "numbers":
            if not self.numbers or len(self.numbers) not in (2, 3):
                raise ValueError("method=numbers 时必须提供 2 个或 3 个整数")
            if any(item <= 0 or item > 9999 for item in self.numbers):
                raise ValueError("报数必须是 1–9999 的整数")
        elif self.method == "text":
            if not self.text:
                raise ValueError("method=text 时必须提供 text")
        elif self.method == "measure":
            if self.length_value is None:
                raise ValueError("method=measure 时必须提供 length_value")
        elif self.method == "direction":
            if not self.direction:
                raise ValueError("method=direction 时必须提供 direction")
        elif self.method == "hexagram":
            if self.upper not in TRIGRAM_BITS or self.lower not in TRIGRAM_BITS:
                raise ValueError("method=hexagram 时必须提供合法的上下卦名")
            if self.moving_line is None:
                raise ValueError("method=hexagram 时必须提供 moving_line（1–6）")
        return self

    model_config = {"extra": "forbid"}


class MeihuaCalculateIn(MeihuaInput):
    convention: MeihuaConvention = Field(default_factory=MeihuaConvention)
