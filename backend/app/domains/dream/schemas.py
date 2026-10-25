"""解梦入参 / 口径结构。

输入是「梦的原文描述」，本域做两件事：
1. 从原文里抽取可检索的关键词（用固定词表匹配，不做分词库依赖）；
2. 按命中的关键词归类，给出该类的传统象征说法（标注为传统说法）。

三件事显式化并回显：
- `max_keywords`：最多抽几个关键词；
- `include_traditional`：是否输出传统象征说法（关掉则只出关键词）；
- `store_text`：是否保存梦境原文（默认保存，可关闭）。

红线：不解梦、不预示、不判断吉凶、不做心理诊断。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

MIN_TEXT = 2
MAX_TEXT = 2000


class DreamConvention(BaseModel):
    """解梦口径。全部字段回显到 `ChartResult.convention`。"""

    #: 本版本只做关键词抽取与归类，不做象征体系推演
    school: Literal["keyword_lookup_v1"] = "keyword_lookup_v1"
    #: 关键词来源：内置词表（不依赖分词库）
    lexicon: Literal["builtin_v1"] = "builtin_v1"
    #: 传统说法的定位：文化背景，不是解释结论
    traditional_scope: Literal["cultural_reference"] = "cultural_reference"

    model_config = {"extra": "forbid"}


class DreamInput(BaseModel):
    text: str
    max_keywords: int = Field(default=8, ge=1, le=20)
    include_traditional: bool = True
    store_text: bool = True

    @field_validator("text")
    @classmethod
    def _text_shape(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < MIN_TEXT:
            raise ValueError(f"梦境描述至少 {MIN_TEXT} 个字")
        if len(cleaned) > MAX_TEXT:
            raise ValueError(f"梦境描述不超过 {MAX_TEXT} 字")
        return cleaned

    model_config = {"extra": "forbid"}


class DreamCalculateIn(DreamInput):
    convention: DreamConvention = Field(default_factory=DreamConvention)
