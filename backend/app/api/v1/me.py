"""账号接口：额度、订单、资料、数据导出、注销。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_optional_user
from app.core.db import get_session, utcnow
from app.core.errors import Unauthorized
from app.core.security import verify_password
from app.domains.billing import ledger
from app.domains.billing import orders as order_service
from app.models import AuditLog, Feedback, UsageLedger
from app.models import ChartRecord
from app.models import AiReport
from app.models import User, UserConsent
from app.repositories import user_repo
from app.schemas.auth import DeleteAccountIn, UserOut

class ProfileIn(BaseModel):
    """改昵称请求体。"""

    display_name: str = Field(min_length=1, max_length=40)

    model_config = {"extra": "forbid"}


router = APIRouter(prefix="/me", tags=["me"])


@router.get("/usage")
def usage(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    return ledger.snapshot(session, user.id)


@router.get("/orders")
def my_orders(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    items = order_service.list_owned(session, user_id=user.id)
    return {"count": len(items), "items": [order_service.summary(order) for order in items]}


@router.get("/ledger")
def my_ledger(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    rows = session.scalars(
        select(UsageLedger)
        .where(UsageLedger.user_id == user.id)
        .order_by(UsageLedger.created_at.desc(), UsageLedger.id.desc())
        .limit(100)
    ).all()
    return {
        "count": len(rows),
        "items": [
            {
                "id": row.id,
                "event_type": row.event_type,
                "units": row.units,
                "reference_type": row.reference_type,
                "reference_id": row.reference_id,
                "note": row.note,
                "created_at": row.created_at.isoformat() + "Z",
            }
            for row in rows
        ],
    }


@router.patch("/profile", response_model=UserOut)
def update_profile(
    payload: ProfileIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> UserOut:
    user.display_name = payload.display_name
    session.add(user)
    session.commit()
    return UserOut.model_validate(user)


@router.get("/consents")
def my_consents(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    rows = session.scalars(
        select(UserConsent).where(UserConsent.user_id == user.id).order_by(UserConsent.consent_at.desc())
    ).all()
    return {
        "items": [
            {
                "doc_type": row.doc_type,
                "doc_version": row.doc_version,
                "consent_at": row.consent_at.isoformat() + "Z",
                "revoked_at": row.revoked_at.isoformat() + "Z" if row.revoked_at else None,
            }
            for row in rows
        ]
    }


@router.get("/export")
def export_my_data(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    """个人信息副本导出（个人信息保护法第二十条的可携带权）。"""
    charts = session.scalars(
        select(ChartRecord).where(ChartRecord.owner_user_id == user.id, ChartRecord.deleted_at.is_(None))
    ).all()
    reports = session.scalars(select(AiReport).where(AiReport.user_id == user.id)).all()
    orders = order_service.list_owned(session, user_id=user.id)
    consents = session.scalars(select(UserConsent).where(UserConsent.user_id == user.id)).all()

    payload = {
        "exported_at": utcnow().isoformat() + "Z",
        "user": {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "created_at": user.created_at.isoformat() + "Z",
        },
        "consents": [
            {"doc_type": row.doc_type, "doc_version": row.doc_version, "consent_at": row.consent_at.isoformat() + "Z"}
            for row in consents
        ],
        "charts": [
            {
                "id": row.id,
                "title": row.title,
                "domain": row.domain,
                "algorithm_version": row.algorithm_version,
                "convention": row.convention_json,
                "chart": row.chart_json,
                "created_at": row.created_at.isoformat() + "Z",
            }
            for row in charts
        ],
        "reports": [
            {
                "id": row.id,
                "chart_id": row.chart_id,
                "status": row.status,
                "depth": row.depth,
                "skill_version": row.skill_version,
                "report": row.report_json,
                "created_at": row.created_at.isoformat() + "Z",
            }
            for row in reports
        ],
        "orders": [order_service.summary(order) for order in orders],
        "notice": "本文件含个人信息，请妥善保管；数据口径与算法版本随每条记录一并给出。",
    }
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return Response(
        content=body,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="xuanshu-account-export.json"'},
    )


@router.delete("", status_code=204)
def delete_account(
    payload: DeleteAccountIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    """注销账号：立即失效登录态、立即隐藏数据，30 天后物理清理。"""
    if not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise Unauthorized("密码不正确，无法注销账号")
    user_repo.soft_delete(session, user)
    session.add(
        AuditLog(
            actor=f"user:{user.id}",
            action="account.delete_requested",
            target_type="user",
            target_id=str(user.id),
            detail_json={"requested_at": utcnow().isoformat() + "Z", "retention_days": 30},
        )
    )
    session.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- 反馈
#
# 反馈与投诉入口（合规必备）。
# 
# 反馈默认不进入训练集：`Feedback` 表只用于运营跟进，且不允许写入用户原文之外的内容。
#
# 路径是根级 `/feedback`（不在 `/me` 下）：未登录用户也能提交投诉，
# 这是合规要求。因此单独一个 router，由 main.py 一并注册。


feedback_router = APIRouter(tags=["feedback"])


class FeedbackIn(BaseModel):
    """反馈请求体。不进入训练集，只用于运营跟进。"""

    rating: int | None = Field(default=None, ge=1, le=5)
    category: str = Field(default="general", max_length=40)
    content: str = Field(default="", max_length=2000)
    report_id: int | None = None

    model_config = {"extra": "forbid"}





@feedback_router.post("/feedback", status_code=201)
def create_feedback(
    payload: FeedbackIn,
    user: User | None = Depends(get_optional_user),
    session: Session = Depends(get_session),
) -> dict:
    entry = Feedback(
        user_id=user.id if user else None,
        report_id=payload.report_id,
        rating=payload.rating,
        category=payload.category,
        content=payload.content,
    )
    session.add(entry)
    session.commit()
    return {
        "id": entry.id,
        "received": True,
        "note": "反馈已记录。内容仅用于改进服务，不用于模型训练；如需删除请联系支持。",
    }
