"""面相 / 手相接口：上传图片 → 视觉分析 → 返回结构化观察。

与 `/charts/{domain}/calculate` 的分工：
- 计算入口是**免登录、无副作用**的纯函数调用；
- 这里是**必须登录、消耗额度、落盘图片**的有副作用操作，因此独立成路由，
  不塞进计算入口 —— 否则匿名请求可以刷爆视觉模型账单。

红线：图片不出服务端（除非显式取图），模型输出不回写 `chart_facts`。
"""

from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, File, Form, Header, Request, Response, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_session
from app.core.errors import AppError
from app.core.throttle import client_key, hit
from app.domains.vision import prompts, service as vision_service
from app.models import User
from app.services import media

router = APIRouter(tags=["vision"])

#: 视觉模型按次计费且较贵，限流比文本报告更紧
VISION_HOURLY_LIMIT = 10


def _check_rate(request: Request, kind: str) -> None:
    hit(client_key(request, f"vision:{kind}"), limit=VISION_HOURLY_LIMIT, window_seconds=3600)


async def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    """读取上传文件并做基础校验。真正的 MIME 校验在 media.store 里按内容做。"""
    raw = await file.read()
    if not raw:
        raise AppError("INVALID_REQUEST", "上传的图片为空", status_code=422)
    mime = (file.content_type or "").strip().lower()
    if mime not in media.ALLOWED_MIME:
        raise AppError(
            "UNSUPPORTED_MEDIA_TYPE",
            f"不支持的图片格式「{mime or '未知'}」，只接受 jpeg / png / webp",
            status_code=415,
        )
    return raw, mime


@router.get("/vision/types")
def list_types() -> dict:
    """分析类型与免责声明。前端据此渲染选项，不在 Vue 里硬编码。"""
    def dump(items: tuple[prompts.AnalysisType, ...]) -> list[dict]:
        return [
            {"id": item.id, "name": item.name, "description": item.description}
            for item in items
        ]

    return {
        "face": {"types": dump(prompts.FACE_TYPES), "disclaimer": prompts.FACE_DISCLAIMER},
        "palm": {
            "types": dump(prompts.PALM_TYPES),
            "hand_types": prompts.HAND_TYPES,
            "disclaimer": prompts.PALM_DISCLAIMER,
        },
        "max_bytes": media.MAX_EDGE,
    }


def _outcome_payload(outcome: vision_service.AnalysisOutcome) -> dict:
    chart_json = outcome.chart.chart_json or {}
    payload: dict = {
        "chart_id": outcome.chart.id,
        "title": outcome.chart.title,
        "domain": outcome.chart.domain,
        "algorithm_version": outcome.chart.algorithm_version,
        "media": {
            "sha256": outcome.media_row.sha256,
            "mime": outcome.media_row.mime,
            "width": outcome.media_row.width,
            "height": outcome.media_row.height,
            "size_bytes": outcome.media_row.size_bytes,
            "delete_after": outcome.media_row.delete_after.isoformat()
            if outcome.media_row.delete_after
            else None,
        },
        "chart_facts": chart_json.get("chart_facts", {}),
        "warnings": chart_json.get("warnings", []),
        "source_refs": chart_json.get("source_refs", []),
        "degraded": outcome.degraded,
        "degraded_reason": outcome.degraded_reason,
    }
    if outcome.response is not None:
        payload["result"] = outcome.response.payload
        payload["usage"] = {
            "provider": outcome.response.provider,
            "model": outcome.response.model,
            "input_tokens": outcome.response.input_tokens,
            "output_tokens": outcome.response.output_tokens,
            "latency_ms": outcome.response.latency_ms,
        }
    return payload


@router.post("/vision/face/analyze", status_code=201)
async def analyze_face(
    request: Request,
    file: UploadFile = File(...),
    analysis_type: str = Form("full"),
    question: str | None = Form(None),
    store_question: bool = Form(True),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=80),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    _check_rate(request, "face")
    raw, mime = await _read_upload(file)
    outcome = vision_service.analyze(
        session,
        user_id=user.id,
        kind="face",
        raw=raw,
        mime=mime,
        analysis_type=analysis_type,
        question=question,
        store_question=store_question,
        idempotency_key=f"vision:face:{user.id}:{idempotency_key}",
    )
    return _outcome_payload(outcome)


@router.post("/vision/palm/analyze", status_code=201)
async def analyze_palm(
    request: Request,
    file: UploadFile = File(...),
    analysis_type: str = Form("full"),
    hand_type: str = Form("left"),
    question: str | None = Form(None),
    store_question: bool = Form(True),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=80),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    _check_rate(request, "palm")
    raw, mime = await _read_upload(file)
    outcome = vision_service.analyze(
        session,
        user_id=user.id,
        kind="palm",
        raw=raw,
        mime=mime,
        analysis_type=analysis_type,
        hand_type=hand_type,
        question=question,
        store_question=store_question,
        idempotency_key=f"vision:palm:{user.id}:{idempotency_key}",
    )
    return _outcome_payload(outcome)


@router.get("/vision/media/{media_id}")
def get_media(
    media_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    """取回自己上传的图片。只允许本人，不提供公开链接。"""
    rows = vision_service.list_media(session, user_id=user.id, limit=200)
    row = next((item for item in rows if item.id == media_id), None)
    if row is None:
        raise AppError("NOT_FOUND", "图片不存在或无权访问", status_code=404)
    try:
        path = media.resolve(row.storage_key)
    except media.MediaError as exc:
        raise AppError("NOT_FOUND", str(exc), status_code=404) from exc
    if not path.exists():
        raise AppError("NOT_FOUND", "图片文件已过期删除", status_code=404)
    return Response(
        content=base64.b64encode(path.read_bytes()),
        media_type=row.mime,
        headers={"Cache-Control": "private, max-age=300"},
    )
