"""合盘入参 / 口径结构。

合盘的输入是**两张已经存在的四柱盘**，不是两组出生时间。理由：
- 出生时间到盘面的转换必须由 `bazi` 域负责，合盘不该重算一遍；
- 用户可能已经保存过盘，直接引用 `chart_id` 可复用口径与算法版本；
- 也支持直接给两组四柱干支（如从别处抄来的盘），但此时必须显式声明。

关系判定完全复用 `domains/relations` 的 YAML 规则引擎（66 条规则），
不另写一份 —— 关系规则只允许在本仓库有一份实现。

红线：只列触发的规则与结构标记，不给「合不合」「能不能成」这类结论。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MIN_YEAR = 1800
MAX_YEAR = 2200
#: 直接给干支时必须是四柱
PILLAR_KEYS = ("year", "month", "day", "hour")


class HepanConvention(BaseModel):
    """合盘口径。全部字段回显到 `ChartResult.convention`。"""

    #: 本版本只做干支层面的交互（四柱对四柱）
    school: Literal["bazi_cross_v1"] = "bazi_cross_v1"
    #: 交互范围：all = 双方四柱两两比较；day_only = 只比日柱
    scope: Literal["all", "day_only"] = "all"
    #: 规则来源：复用 relations 域的 YAML 规则
    rule_source: Literal["relations_yaml_v1"] = "relations_yaml_v1"

    model_config = {"extra": "forbid"}


class HepanSide(BaseModel):
    """合盘的一方。三选一：已保存的盘 / 出生时间 / 直接给四柱。"""

    label: str = Field(default="甲方", max_length=20)
    #: 已保存的四柱盘 id（推荐：口径与算法版本都随盘存档）
    chart_id: int | None = None
    #: 或直接给出生时间，由 bazi 域排盘
    birth_datetime: datetime | None = None
    timezone: str = "Asia/Shanghai"
    gender: Literal["male", "female", "unknown"] = "unknown"
    #: 或直接给四柱干支，形如 {"year": "庚午", ...}
    pillars: dict[str, str] | None = None

    @field_validator("birth_datetime")
    @classmethod
    def _naive_local_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is not None:
            raise ValueError("birth_datetime 必须是不带时区的当地时间，时区请用 timezone 字段")
        if not MIN_YEAR <= value.year <= MAX_YEAR:
            raise ValueError(f"仅支持 {MIN_YEAR}-{MAX_YEAR} 年之间的出生时间")
        return value

    @field_validator("pillars")
    @classmethod
    def _pillars_valid(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        if value is None:
            return None
        missing = [key for key in PILLAR_KEYS if not value.get(key)]
        if missing:
            raise ValueError(f"四柱缺项：{'、'.join(missing)}")
        for key in PILLAR_KEYS:
            text = value[key].strip()
            if len(text) != 2:
                raise ValueError(f"{key} 柱「{text}」必须是两个字（天干+地支）")
        return {key: value[key].strip() for key in PILLAR_KEYS}

    @model_validator(mode="after")
    def _exactly_one_source(self) -> "HepanSide":
        provided = [
            name
            for name, value in (
                ("chart_id", self.chart_id),
                ("birth_datetime", self.birth_datetime),
                ("pillars", self.pillars),
            )
            if value is not None
        ]
        if len(provided) != 1:
            raise ValueError(
                "每一方必须且只能提供一种来源：chart_id / birth_datetime / pillars"
            )
        return self

    model_config = {"extra": "forbid"}


class HepanInput(BaseModel):
    left: HepanSide
    right: HepanSide
    relation_type: Literal["couple", "business", "parent_child"] = "couple"
    question: str | None = None
    store_question: bool = True

    @field_validator("question")
    @classmethod
    def _question_length(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        if len(text) > 200:
            raise ValueError("占问原文不超过 200 字")
        return text

    model_config = {"extra": "forbid"}


class HepanCalculateIn(HepanInput):
    convention: HepanConvention = Field(default_factory=HepanConvention)
