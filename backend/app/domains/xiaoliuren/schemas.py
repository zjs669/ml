"""小六壬入参 / 口径结构。

小六壬的输入不是出生时间，而是「所问之事的时刻」：
月、日、时各落一宫，三宫顺序递推，最后一宫即断事落点。

口径上只有三件事会改变结果，因此全部显式化并回显：
- `hour_type`：`clock` 按 0–23 小时换算时辰，`shichen` 直接给 1–12 时辰序号；
- `leap_month_strategy`：闰月按本月重数（repeat）还是顺延一月（advance）；
- `input_mode`：公历日期自动转农历，还是手工指定农历月日。

红线：只输出宫位落点与各宫属性，不给吉凶结论、不给应期、不给建议。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MIN_YEAR = 1800
MAX_YEAR = 2200
#: 占问原文上限，超出直接拒绝而不是静默截断
MAX_QUESTION_LENGTH = 200


class XiaoliurenConvention(BaseModel):
    """小六壬口径。全部字段回显到 `ChartResult.convention`，不做隐式默认。"""

    #: 本版本只实现通行六宫递推法；其他值校验失败，不静默套用
    school: Literal["liugong_digui_v1"] = "liugong_digui_v1"
    #: 闰月处理：repeat = 闰月按本月数（同月重数），advance = 顺延为下一月
    leap_month_strategy: Literal["repeat", "advance"] = "repeat"
    #: 时辰来源：clock = 由钟表小时换算，shichen = 直接给时辰序号
    hour_type: Literal["clock", "shichen"] = "clock"

    model_config = {"extra": "forbid"}


class XiaoliurenInput(BaseModel):
    #: gregorian = 给 date + hour；lunar = 直接给 lunar_month + lunar_day + hour
    input_mode: Literal["gregorian", "lunar"] = "gregorian"
    #: input_mode=gregorian 时必填：所问之事的公历日期（只取年月日）
    date: datetime | None = None
    #: input_mode=lunar 时必填
    lunar_month: int | None = Field(default=None, ge=1, le=12)
    lunar_day: int | None = Field(default=None, ge=1, le=30)
    is_leap_month: bool = False
    #: clock 模式下为 0–23；shichen 模式下为 1–12
    hour: int = Field(ge=0, le=23)
    timezone: str = "Asia/Shanghai"
    question: str | None = None
    store_question: bool = True

    @field_validator("date")
    @classmethod
    def _naive_local_date(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is not None:
            raise ValueError("date 必须是不带时区的当地日期，时区请用 timezone 字段")
        if not MIN_YEAR <= value.year <= MAX_YEAR:
            raise ValueError(f"仅支持 {MIN_YEAR}-{MAX_YEAR} 年之间的日期")
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

    @model_validator(mode="after")
    def _mode_payload(self) -> "XiaoliurenInput":
        if self.input_mode == "gregorian":
            if self.date is None:
                raise ValueError("input_mode=gregorian 时必须提供 date")
            if self.lunar_month is not None or self.lunar_day is not None:
                raise ValueError("公历输入与农历月日不能同时提供")
            if self.is_leap_month:
                raise ValueError("is_leap_month 只在 input_mode=lunar 时有意义")
        else:
            if self.lunar_month is None or self.lunar_day is None:
                raise ValueError("input_mode=lunar 时必须提供 lunar_month 与 lunar_day")
            if self.date is not None:
                raise ValueError("农历输入不要再给 date")
        return self

    model_config = {"extra": "forbid"}


class XiaoliurenCalculateIn(XiaoliurenInput):
    convention: XiaoliurenConvention = Field(default_factory=XiaoliurenConvention)
