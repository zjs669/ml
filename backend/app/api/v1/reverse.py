"""四柱反查接口：免登录、纯计算、按 IP 限流。

反查不落库，也不产生任何用户数据：输入干支、输出候选日期。
需要 AI 解读时由前端把命中盘面送进既有的「保存命盘 → 生成报告」流程。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.deps import get_optional_user
from app.core.ratelimit import client_key, hit
from app.domains.bazi.reverse import resolve_timezone, reverse_search
from app.domains.calendar_core.solar_terms import get_term_service
from app.models.user import User
from app.schemas.reverse import ReverseSearchIn, ReverseSearchOut

router = APIRouter(tags=["reverse"])

REVERSE_LIMIT_PER_MINUTE = 30


@router.post("/charts/bazi/reverse-search", response_model=ReverseSearchOut)
def reverse(
    payload: ReverseSearchIn,
    request: Request,
    _: User | None = Depends(get_optional_user),
) -> ReverseSearchOut:
    """由年月日时四柱反推公历日期与时辰窗口。"""
    hit(client_key(request, "reverse"), limit=REVERSE_LIMIT_PER_MINUTE, window_seconds=60)
    result = reverse_search(
        payload.pillars,
        start=payload.range_start,
        end=payload.range_end,
        tz=resolve_timezone(payload.timezone),
        conv=payload.convention,
        service=get_term_service(),
        longitude=payload.longitude,
        limit=payload.limit,
        offset=payload.offset,
    )
    return ReverseSearchOut.model_validate(result)
