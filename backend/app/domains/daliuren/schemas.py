"""大六壬入参 / 口径结构。

**范围声明（重要）**：本版本实现大六壬的**主干**：
月将加时 → 天地盘 → 四课 → 贼克法三传（含比用法）。
涉害、遥克、昴星、别责、八专、伏吟、返吟等复杂课体**未实现**，
遇到这些情形时三传留空并在 `warnings` 里写明原因，不硬凑一个结果。

为什么不硬凑：课体判定是大六壬的核心难点，各版本教材的优先级也有差异
（taibu 的 `ALGORITHM_RULES.md` 明确写「涉害、遥克、昴星等全部课表并没有原典逐条金标准覆盖」）。
给一个「看起来完整但可能错」的三传，比明确说「本版本不判」危险得多。

口径上会改变结果的只有两件事，显式化并回显：
- `month_general`：月将由中气定（默认），或手工指定；
- `day_night`：昼贵/夜贵，按时辰（卯至申为昼）或强制指定。

红线：只出天地盘、四课、三传与神煞位置，不给吉凶、不给应期。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

MIN_YEAR = 1800
MAX_YEAR = 2200
MAX_QUESTION_LENGTH = 200
#: 十二地支，用于校验手工月将
BRANCHES = ("子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥")


class DaliurenConvention(BaseModel):
    """大六壬口径。全部字段回显到 `ChartResult.convention`。"""

    #: 本版本只实现贼克法三传
    school: Literal["zeike_zhugan_v1"] = "zeike_zhugan_v1"
    #: 月将来源：中气定将（默认）/ 手工指定
    month_general_source: Literal["prev_qi", "manual"] = "prev_qi"
    #: 昼夜判定：shichen = 卯至申为昼；day/night = 强制
    day_night: Literal["shichen", "day", "night"] = "shichen"
    #: 三传取法：只实现贼克法（含比用法），其余课体不判
    san_chuan_method: Literal["zeike"] = "zeike"

    model_config = {"extra": "forbid"}


class DaliurenInput(BaseModel):
    cast_datetime: datetime
    timezone: str = "Asia/Shanghai"
    #: 手工月将（地支），仅 convention.month_general_source=manual 时生效
    month_general: str | None = None
    question: str | None = None
    store_question: bool = True

    @field_validator("cast_datetime")
    @classmethod
    def _naive_local_time(cls, value: datetime) -> datetime:
        if value.tzinfo is not None:
            raise ValueError("cast_datetime 必须是不带时区的当地时间，时区请用 timezone 字段")
        if not MIN_YEAR <= value.year <= MAX_YEAR:
            raise ValueError(f"仅支持 {MIN_YEAR}-{MAX_YEAR} 年之间的起课时间")
        return value

    @field_validator("month_general")
    @classmethod
    def _month_general_valid(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if text not in BRANCHES:
            raise ValueError(f"月将必须是十二地支之一，收到「{value}」")
        return text

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

    model_config = {"extra": "forbid"}


class DaliurenCalculateIn(DaliurenInput):
    convention: DaliurenConvention = Field(default_factory=DaliurenConvention)
