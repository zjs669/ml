"""反馈与投诉入口（合规必备）。

反馈默认不进入训练集：`Feedback` 表只用于运营跟进，且不允许写入用户原文之外的内容。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_optional_user
from app.core.db import get_session
from app.models.billing import Feedback
from app.models.user import User
from app.schemas.billing import FeedbackIn

router = APIRouter(tags=["feedback"])


@router.post("/feedback", status_code=201)
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
