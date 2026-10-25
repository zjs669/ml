"""西洋占星入参 / 口径结构。

**范围声明（重要）**：本版本是**简化版**，只算太阳与月亮的视黄经，
加上升点（ASC）与天顶（MC）与整宫制宫位。十行星、交点、莉莉丝、
高精度宫制（Placidus/Koch 等）**均未实现**，原因见 `docs/口径说明.md`：
- `pyswisseph` 需要 MSVC 编译，当前环境装不上（实测报 "Microsoft Visual C++ 14.0 or greater is required"）；
- 自研十行星摄动级数精度不足，贸然输出会被误当成专业星历。

因此 `planets` 字段只包含 sun 与 moon，其余行星以 `unavailable` 显式列出，
不静默省略 —— 用户必须能看出「这里少算了什么」。

红线：只输出位置与角度，不给吉凶、不给事件预测、不做性格判断。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MIN_YEAR = 1800
MAX_YEAR = 2200


class AstrologyConvention(BaseModel):
    """占星口径。全部字段回显到 `ChartResult.convention`。"""

    #: 简化版：只有太阳与月亮
    school: Literal["simplified_sun_moon_v1"] = "simplified_sun_moon_v1"
    #: 宫制：本版本只支持整宫制（whole sign），不做 Placidus 等
    house_system: Literal["whole_sign"] = "whole_sign"
    #: 黄道：回归黄道（tropical），不做恒星黄道（sidereal）
    zodiac: Literal["tropical"] = "tropical"
    #: 相位容许度（度）
    aspect_orb: float = Field(default=6.0, ge=1.0, le=12.0)

    model_config = {"extra": "forbid"}


class AstrologyInput(BaseModel):
    #: 本地钟表时间（不带时区）
    birth_datetime: datetime
    timezone: str = "Asia/Shanghai"
    #: 出生地纬度（北纬为正），上升/天顶必须
    latitude: float = Field(ge=-66.0, le=66.0)
    #: 出生地经度（东经为正）
    longitude: float = Field(ge=-180.0, le=180.0)
    time_known: bool = True

    @field_validator("birth_datetime")
    @classmethod
    def _naive_local_time(cls, value: datetime) -> datetime:
        if value.tzinfo is not None:
            raise ValueError("birth_datetime 必须是不带时区的当地时间，时区请用 timezone 字段")
        if not MIN_YEAR <= value.year <= MAX_YEAR:
            raise ValueError(f"仅支持 {MIN_YEAR}-{MAX_YEAR} 年之间的出生时间")
        return value

    @model_validator(mode="after")
    def _latitude_limit(self) -> "AstrologyInput":
        if abs(self.latitude) > 66.0:
            raise ValueError(
                "纬度绝对值超过 66°（极圈内）时上升点可能不存在，本版本不支持；"
                "这是明确拒绝而不是给一个错误值。"
            )
        return self

    model_config = {"extra": "forbid"}


class AstrologyCalculateIn(AstrologyInput):
    convention: AstrologyConvention = Field(default_factory=AstrologyConvention)
