"""塔罗入参 / 口径结构。

塔罗的输入不是时间，而是「牌阵 + 问题 + 可选复现种子」。
三件事会改变结果，因此全部显式化并回显：
- `deck`：全 78 张 / 仅大阿卡纳 22 张 / 仅小阿卡纳 56 张；
- `allow_reversed` 与 `reversed_probability`：是否出现逆位、逆位概率；
- `seed`：给定即完全可复现（同一 seed 同一次抽牌），不给则由当前时刻派生。

红线：只输出牌名、正逆位、位置与传统关键词，不给吉凶结论、不给事件预测。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MAX_QUESTION_LENGTH = 200
#: 单次牌阵最多位置数（凯尔特十字 10 张已足够，超出说明用错了牌阵）
MAX_POSITIONS = 12


class TarotConvention(BaseModel):
    """塔罗口径。全部字段回显到 `ChartResult.convention`。"""

    #: 本版本只实现 Rider–Waite 体系的牌名结构与关键词
    school: Literal["rider_waite_v1"] = "rider_waite_v1"
    #: 抽牌方式：seeded = 由 seed 决定的确定性伪随机（可复现）；不给 seed 时由时刻派生
    draw_mode: Literal["seeded"] = "seeded"
    #: 正逆位判定与牌序判定使用两个独立随机源，避免同一序列决定两件事
    rng_split: Literal["separate_streams"] = "separate_streams"

    model_config = {"extra": "forbid"}


class TarotInput(BaseModel):
    spread: str = "three"
    deck: Literal["all", "major", "minor"] = "all"
    allow_reversed: bool = True
    reversed_probability: float = Field(default=0.35, ge=0.0, le=1.0)
    #: 自定义位置名；给定时忽略 spread 的预设位置，但仍需 spread 合法
    custom_positions: list[str] | None = None
    question: str | None = None
    store_question: bool = True
    #: 复现种子。不给则由当前时刻派生并在结果里回显
    seed: str | None = None

    @field_validator("custom_positions")
    @classmethod
    def _positions_valid(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [item.strip() for item in value if item and item.strip()]
        if not cleaned:
            raise ValueError("custom_positions 不能为空列表")
        if len(cleaned) > MAX_POSITIONS:
            raise ValueError(f"牌阵位置最多 {MAX_POSITIONS} 个")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("牌阵位置名不能重复")
        return cleaned

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
    def _seed_length(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        if len(text) > 64:
            raise ValueError("seed 不超过 64 字符")
        return text

    @model_validator(mode="after")
    def _spread_known(self) -> "TarotInput":
        from app.domains.tarot.cards import SPREADS

        if self.spread not in SPREADS:
            raise ValueError(f"未知牌阵「{self.spread}」，可用：{'、'.join(SPREADS)}")
        return self

    model_config = {"extra": "forbid"}


class TarotCalculateIn(TarotInput):
    convention: TarotConvention = Field(default_factory=TarotConvention)
