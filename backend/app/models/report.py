"""AI 报告。快照哈希 + 口径 + 技能版本一起存档，保证旧报告不被静默覆盖。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import utcnow
from app.models.base import Base


class AiReport(Base):
    __tablename__ = "ai_reports"
    __table_args__ = (
        Index("idx_report_user_created", "user_id", "created_at"),
        Index("idx_report_chart", "chart_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    chart_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chart_records.id", ondelete="SET NULL"), nullable=True
    )
    domain: Mapped[str] = mapped_column(String(20), nullable=False)
    model_provider: Mapped[str] = mapped_column(String(60), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    skill_version: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False, default="system_v1")
    chart_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(80), nullable=False)
    depth: Mapped[str] = mapped_column(String(16), nullable=False, default="brief")
    report_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    citations_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimate: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    validation_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="complete", server_default="complete")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class ReportFollowup(Base):
    """报告追问：一轮问答一行。

    追问不重建报告，也不能改原报告：它读的是「原报告 + 原盘面事实 + 原报告引用过的片段」。
    单独建表的理由：追问有轮次上限、有自己的校验结果与降级状态，塞进 `report_json`
    会让报告本身变成可变对象，旧报告的可追溯性就没了。
    """

    __tablename__ = "report_followups"
    __table_args__ = (Index("idx_followup_report", "report_id", "seq"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ai_reports.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    citations_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    validation_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="complete", server_default="complete"
    )
    model_provider: Mapped[str] = mapped_column(String(60), nullable=False, default="fallback")
    model_name: Mapped[str] = mapped_column(String(100), nullable=False, default="degraded-template-v1")
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
