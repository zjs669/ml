"""报告数据访问层。所有查询都带 owner_user_id，越权一律 NotFound。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.models.report import AiReport, ReportFollowup


def create_report(session: Session, **fields: Any) -> AiReport:
    report = AiReport(**fields)
    session.add(report)
    session.flush()
    return report


def get_owned(session: Session, *, report_id: int, user_id: int) -> AiReport:
    report = session.scalar(
        select(AiReport).where(AiReport.id == report_id, AiReport.user_id == user_id)
    )
    if report is None:
        raise NotFound("REPORT_NOT_FOUND", "报告不存在或无权访问")
    return report


def list_for_chart(session: Session, *, chart_id: int, user_id: int, limit: int = 20) -> list[AiReport]:
    return list(
        session.scalars(
            select(AiReport)
            .where(AiReport.chart_id == chart_id, AiReport.user_id == user_id)
            .order_by(AiReport.created_at.desc(), AiReport.id.desc())
            .limit(limit)
        ).all()
    )


def find_replay(
    session: Session, *, chart_id: int, user_id: int, depth: str, since
) -> AiReport | None:
    """同一幂等键重放时，返回此前那次生成的结果，避免重复扣费。"""
    return session.scalar(
        select(AiReport)
        .where(
            AiReport.chart_id == chart_id,
            AiReport.user_id == user_id,
            AiReport.depth == depth,
            AiReport.created_at >= since,
        )
        .order_by(AiReport.created_at.desc())
        .limit(1)
    )


def latest_for_chart(session: Session, chart_id: int) -> AiReport | None:
    return session.scalar(
        select(AiReport)
        .where(AiReport.chart_id == chart_id)
        .order_by(AiReport.created_at.desc())
        .limit(1)
    )


def mark_status(session: Session, report: AiReport, status: str) -> AiReport:
    report.status = status
    session.add(report)
    return report


# ---- 追问 ----


def create_followup(session: Session, **fields: Any) -> ReportFollowup:
    row = ReportFollowup(**fields)
    session.add(row)
    session.flush()
    return row


def count_followups(session: Session, *, report_id: int) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(ReportFollowup)
            .where(ReportFollowup.report_id == report_id)
        )
        or 0
    )


def list_followups(
    session: Session, *, report_id: int, limit: int | None = None
) -> list[ReportFollowup]:
    """按 seq 升序返回；`limit` 用于取「最近 N 轮」做上下文。"""
    statement = (
        select(ReportFollowup)
        .where(ReportFollowup.report_id == report_id)
        .order_by(ReportFollowup.seq.asc())
    )
    if limit is not None:
        statement = (
            select(ReportFollowup)
            .where(ReportFollowup.report_id == report_id)
            .order_by(ReportFollowup.seq.desc())
            .limit(limit)
        )
        return list(reversed(list(session.scalars(statement).all())))
    return list(session.scalars(statement).all())
