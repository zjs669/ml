"""报告出参 / 入参 Schema。

报告正文结构固定为 7 个字段（产品文档 10.3），少一个字段就视为模型输出不合格：
summary / observations / traditional_interpretations / practical_reflections /
uncertainties / citations / safety_note。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Observation(BaseModel):
    """盘面事实复述。必须能在 chart_facts 里找到依据，rule_ids 必须是已触发规则。"""

    fact: str = Field(min_length=1, max_length=800)
    rule_ids: list[str] = Field(default_factory=list)
    citation_ids: list[int] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class Interpretation(BaseModel):
    """传统解释。必须带知识库引用；没有引用就只能写进 uncertainties。"""

    claim: str = Field(min_length=1, max_length=1200)
    citation_ids: list[int] = Field(default_factory=list)
    school_note: str | None = Field(default=None, max_length=400)

    model_config = {"extra": "forbid"}


class ReportPayload(BaseModel):
    summary: str = Field(min_length=1, max_length=1200)
    observations: list[Observation] = Field(default_factory=list, max_length=40)
    traditional_interpretations: list[Interpretation] = Field(default_factory=list, max_length=20)
    practical_reflections: list[str] = Field(default_factory=list, max_length=20)
    uncertainties: list[str] = Field(default_factory=list, max_length=20)
    citations: list[int] = Field(default_factory=list, max_length=40)
    safety_note: str = Field(min_length=1, max_length=800)

    model_config = {"extra": "forbid"}


class ReportGenerateIn(BaseModel):
    depth: Literal["brief", "detailed"] = "brief"
    topic: str | None = Field(default=None, max_length=40)
    skill_key: str | None = Field(default=None, max_length=120)

    model_config = {"extra": "forbid"}


class ReportOut(BaseModel):
    id: int
    chart_id: int | None
    domain: str
    depth: str
    status: str
    model_provider: str
    model_name: str
    skill_version: str
    prompt_version: str
    algorithm_version: str
    chart_snapshot_hash: str
    report: dict[str, Any]
    citations: list[dict[str, Any]]
    validation: dict[str, Any] | None
    created_at: str


class ReportListItem(BaseModel):
    id: int
    chart_id: int | None
    depth: str
    status: str
    created_at: str
    summary: str | None = None


class FollowupIn(BaseModel):
    """一轮追问。问题长度上限 500 字：再长就不是「追问」，而是重新写一份报告。"""

    question: str = Field(min_length=2, max_length=500)

    model_config = {"extra": "forbid"}


class FollowupPayload(BaseModel):
    """追问答案：比报告窄得多，但仍保留引用与免责声明。"""

    answer: str = Field(min_length=1, max_length=1200)
    points: list[str] = Field(default_factory=list, max_length=8)
    citations: list[int] = Field(default_factory=list, max_length=20)
    uncertainties: list[str] = Field(default_factory=list, max_length=8)
    safety_note: str = Field(min_length=1, max_length=400)

    model_config = {"extra": "forbid"}


class FollowupOut(BaseModel):
    id: int
    report_id: int
    seq: int
    question: str
    answer: dict[str, Any]
    citations: list[dict[str, Any]]
    status: str
    model_provider: str
    model_name: str
    validation: dict[str, Any] | None = None
    created_at: str
