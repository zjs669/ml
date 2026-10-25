"""模型调用账本。

产品文档 10.1 要求每次调用记录 provider / model / 耗时 / token / 成本 / 技能版本 / 错误类型。
这里只记"调用元数据"，不记提示词正文，也不记用户原始问题——排障靠 code + 指标，
而不是靠把用户数据再复制一份。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import utcnow
from app.models.base import Base


class LlmCall(Base):
    __tablename__ = "llm_calls"
    __table_args__ = (
        Index("idx_llm_created", "created_at"),
        Index("idx_llm_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    chart_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chart_records.id", ondelete="SET NULL"), nullable=True
    )
    report_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ai_reports.id", ondelete="SET NULL"), nullable=True
    )
    task: Mapped[str] = mapped_column(String(80), nullable=False)
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False, default="system_v1")
    skill_key: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimate: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    meta_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
