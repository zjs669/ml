"""太乙九星入参 / 口径结构。

本版本实现的是**太乙九星观测**（九星在年月日时四层的位置与属性），
不是完整的太乙神数（七十二局、主客算、大小将、十六神）。两者差别很大，
因此口径字段显式写明，避免用户误以为拿到的是完整太乙盘。

四层：
- `year`：年盘，看年层九星；
- `month`：月盘；
- `day`：日盘；
- `hour`：时盘，需要给 hour。

红线：只列九星编号、太乙名、五行、方位与传统吉凶分类，
不给事件判断、不给行动建议。
"""

from __future__ import annotations

from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MIN_YEAR = 1800
MAX_YEAR = 2200
MAX_QUESTION_LENGTH = 200


class TaiyiConvention(BaseModel):
    """太乙口径。全部字段回显到 `ChartResult.convention`。"""

    #: 本版本只实现九星观测体系，不实现七十二局
    school: Literal["jiuxing_observation_v1"] = "jiuxing_observation_v1"
    #: 时层按十二时辰划分
    hour_basis: Literal["shichen"] = "shichen"
    #: 九星顺逆：本版本只做顺推，不提供逆推
    direction: Literal["forward"] = "forward"

    model_config = {"extra": "forbid"}


class TaiyiInput(BaseModel):
    date: Date
    timezone: str = "Asia/Shanghai"
    mode: Literal["year", "month", "day", "hour"] = "day"
    #: mode=hour 时必填，0–23
    hour: int | None = Field(default=None, ge=0, le=23)
    question: str | None = None
    store_question: bool = True

    @field_validator("date")
    @classmethod
    def _year_range(cls, value: Date) -> Date:
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
    def _mode_payload(self) -> "TaiyiInput":
        if self.mode == "hour" and self.hour is None:
            raise ValueError("mode=hour 时必须提供 hour（0–23）")
        return self

    model_config = {"extra": "forbid"}


class TaiyiCalculateIn(TaiyiInput):
    convention: TaiyiConvention = Field(default_factory=TaiyiConvention)
