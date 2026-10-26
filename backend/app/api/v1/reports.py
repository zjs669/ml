"""报告接口：生成、详情、列表、追问。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_session
from app.core.errors import AppError
from app.core.throttle import client_key, hit
from app.domains.reporting import followup as followup_service
from app.domains.reporting import service as reporting
from app.models import User
from app.repositories import chart_repo, report_repo
from app.schemas.report import (
    FollowupIn,
    FollowupOut,
    ReportGenerateIn,
    ReportListItem,
    ReportOut,
)

router = APIRouter(tags=["reports"])

REPORT_HOURLY_LIMIT = 20
FOLLOWUP_HOURLY_LIMIT = 30


@router.post("/charts/{chart_id}/reports", response_model=ReportOut, status_code=201)
def create_report(
    chart_id: int,
    payload: ReportGenerateIn,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=80),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ReportOut:
    """生成 AI 解读。`Idempotency-Key` 必填：同一键重放不会重复扣费。"""
    hit(client_key(request, "report"), limit=REPORT_HOURLY_LIMIT, window_seconds=3600)
    chart = chart_repo.get_owned(session, chart_id=chart_id, owner_id=user.id)
    report, replayed = reporting.generate(
        session,
        chart=chart,
        user_id=user.id,
        depth=payload.depth,
        topic=payload.topic,
        skill_key=payload.skill_key,
        idempotency_key=f"report:{user.id}:{idempotency_key}",
    )
    data = reporting.serialize(report)
    if replayed:
        data["validation"] = {**(data.get("validation") or {}), "replayed": True}
    return ReportOut.model_validate(data)


@router.get("/reports/{report_id}", response_model=ReportOut)
def get_report(
    report_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ReportOut:
    report = report_repo.get_owned(session, report_id=report_id, user_id=user.id)
    return ReportOut.model_validate(reporting.serialize(report))


@router.get("/charts/{chart_id}/reports", response_model=list[ReportListItem])
def list_reports(
    chart_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[ReportListItem]:
    chart_repo.get_owned(session, chart_id=chart_id, owner_id=user.id)
    items = report_repo.list_for_chart(session, chart_id=chart_id, user_id=user.id)
    return [
        ReportListItem(
            id=item.id,
            chart_id=item.chart_id,
            depth=item.depth,
            status=item.status,
            created_at=(item.created_at.isoformat() + "Z"),
            summary=(item.report_json or {}).get("summary"),
        )
        for item in items
    ]


@router.post("/reports/{report_id}/followups", response_model=FollowupOut, status_code=201)
def create_followup(
    report_id: int,
    payload: FollowupIn,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> FollowupOut:
    """追问：不扣额度，但受每小时限流与日预算约束。"""
    hit(client_key(request, "followup"), limit=FOLLOWUP_HOURLY_LIMIT, window_seconds=3600)
    report = report_repo.get_owned(session, report_id=report_id, user_id=user.id)
    if report.chart_id is None:
        raise AppError(
            "CHART_NOT_FOUND",
            "这份报告关联的命盘已删除，无法继续追问。",
            status_code=400,
        )
    chart = chart_repo.get_owned(session, chart_id=report.chart_id, owner_id=user.id)
    row = followup_service.answer(
        session, chart=chart, report=report, user_id=user.id, question=payload.question.strip()
    )
    return FollowupOut.model_validate(followup_service.serialize(row))


@router.get("/reports/{report_id}/followups", response_model=list[FollowupOut])
def list_followups(
    report_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[FollowupOut]:
    report_repo.get_owned(session, report_id=report_id, user_id=user.id)
    rows = report_repo.list_followups(session, report_id=report_id)
    return [FollowupOut.model_validate(followup_service.serialize(row)) for row in rows]
