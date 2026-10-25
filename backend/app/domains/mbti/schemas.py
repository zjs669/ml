"""MBTI 式问卷入参 / 口径结构。

输入是「40 道题的作答」，不是时间。三件事影响结果：
- 作答是否齐全（缺题必须拒绝，不能按缺省值补）；
- 平票如何表示（本版本记 `X`，不强行归到某一极）；
- 是否保存作答原文（默认保存，可关闭）。

红线：只输出四维倾向与每题的选择分布，不给人格断言、不给职业建议。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class MbtiConvention(BaseModel):
    """MBTI 式问卷口径。全部字段回显到 `ChartResult.convention`。"""

    #: 自编题库版本，必须显式写明
    school: Literal["self_authored_four_dim_v1"] = "self_authored_four_dim_v1"
    #: 平票处理：X = 记为未分化（不强行归极）
    tie_rule: Literal["undifferentiated"] = "undifferentiated"
    #: 计分方式：每题一票，不做加权
    scoring: Literal["equal_weight"] = "equal_weight"

    model_config = {"extra": "forbid"}


class MbtiInput(BaseModel):
    #: 题 id → 选择（"A" 或 "B"）
    answers: dict[str, str]
    #: 是否保存作答原文（关掉后只保留四维计数）
    store_answers: bool = True

    @field_validator("answers")
    @classmethod
    def _answers_shape(cls, value: dict[str, str]) -> dict[str, str]:
        from app.domains.mbti.items import QUESTIONS

        known = {item.id for item in QUESTIONS}
        cleaned: dict[str, str] = {}
        for key, choice in value.items():
            if key not in known:
                raise ValueError(f"未知题目 id「{key}」")
            picked = str(choice).strip().upper()
            if picked not in ("A", "B"):
                raise ValueError(f"题目「{key}」的作答必须是 A 或 B，收到「{choice}」")
            cleaned[key] = picked
        return cleaned

    @model_validator(mode="after")
    def _all_answered(self) -> "MbtiInput":
        from app.domains.mbti.items import QUESTIONS

        missing = [item.id for item in QUESTIONS if item.id not in self.answers]
        if missing:
            preview = "、".join(missing[:5])
            raise ValueError(f"还有 {len(missing)} 题未作答（如 {preview}）；缺题不做推断。")
        return self

    model_config = {"extra": "forbid"}


class MbtiCalculateIn(MbtiInput):
    convention: MbtiConvention = Field(default_factory=MbtiConvention)
