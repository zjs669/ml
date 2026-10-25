"""紫微飞星入参 / 口径结构。

与 `ziwei` 域的区别：`ziwei` 只做「命宫起两跳的串联概览」，
本域是**定向查询**——问「某宫的某几个化飞到哪些宫」或「哪一宫飞入某宫」。

三类查询：
- `flies_to`：指定起点宫与终点宫，看哪些化把起点连到终点；
- `flies_from`：指定起点宫，列出它的全部四化去向；
- `flies_into`：指定终点宫，反查哪些宫飞入它。

红线：只输出链路（起点宫 → 化 → 星 → 终点宫），不解读吉凶。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MIN_YEAR = 1800
MAX_YEAR = 2200
MUTAGENS = ("禄", "权", "科", "忌")


class FlyingConvention(BaseModel):
    """飞星口径。全部字段回显到 `ChartResult.convention`。"""

    #: 本命盘口径沿用三合派单一口径
    school: Literal["sanhe_default_v1"] = "sanhe_default_v1"
    #: 四化名称固定四种，不接受别名（避免「禄转忌」这类复合说法混进数据层）
    mutagen_names: tuple[str, ...] = MUTAGENS
    #: 空 mutagens 时按「全部四化」处理，而不是当作「无四化」
    empty_means_all: bool = True

    model_config = {"extra": "forbid"}


class FlyingInput(BaseModel):
    birth_datetime: datetime
    timezone: str = "Asia/Shanghai"
    gender: Literal["male", "female", "unknown"] = "unknown"
    calendar: Literal["gregorian", "lunar"] = "gregorian"
    is_leap_month: bool = False
    time_known: bool = True

    query_type: Literal["flies_to", "flies_from", "flies_into"] = "flies_from"
    #: flies_to / flies_from 必填；flies_into 忽略
    from_palace: str | None = None
    #: flies_to / flies_into 必填；flies_from 忽略
    to_palace: str | None = None
    #: 只查指定四化；空表示全部（由 convention.empty_means_all 决定）
    mutagens: list[str] = Field(default_factory=list)

    @field_validator("birth_datetime")
    @classmethod
    def _naive_local_time(cls, value: datetime) -> datetime:
        if value.tzinfo is not None:
            raise ValueError("birth_datetime 必须是不带时区的当地时间，时区请用 timezone 字段")
        if not MIN_YEAR <= value.year <= MAX_YEAR:
            raise ValueError(f"仅支持 {MIN_YEAR}-{MAX_YEAR} 年之间的出生时间")
        return value

    @field_validator("mutagens")
    @classmethod
    def _mutagens_valid(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item and item.strip()]
        unknown = [item for item in cleaned if item not in MUTAGENS]
        if unknown:
            raise ValueError(f"未知四化：{'、'.join(unknown)}；只接受 禄/权/科/忌")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("四化不能重复")
        return cleaned

    @model_validator(mode="after")
    def _query_payload(self) -> "FlyingInput":
        from app.domains.ziwei.constants import PALACES

        def check(name: str | None, field: str) -> None:
            if name is not None and name not in PALACES:
                raise ValueError(f"{field}「{name}」不是合法宫位；可用：{'、'.join(PALACES)}")

        check(self.from_palace, "from_palace")
        check(self.to_palace, "to_palace")
        if self.query_type in ("flies_to", "flies_from") and not self.from_palace:
            raise ValueError(f"query_type={self.query_type} 时必须提供 from_palace")
        if self.query_type in ("flies_to", "flies_into") and not self.to_palace:
            raise ValueError(f"query_type={self.query_type} 时必须提供 to_palace")
        return self

    model_config = {"extra": "forbid"}


class FlyingCalculateIn(FlyingInput):
    convention: FlyingConvention = Field(default_factory=FlyingConvention)
