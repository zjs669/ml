"""计费相关出入参。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class OrderIn(BaseModel):
    plan_code: str = Field(min_length=1, max_length=40)


class FeedbackIn(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=5)
    category: str = Field(default="general", max_length=40)
    content: str = Field(default="", max_length=2000)
    report_id: int | None = None

    model_config = {"extra": "forbid"}


class ProfileIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=40)

    model_config = {"extra": "forbid"}
