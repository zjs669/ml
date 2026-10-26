"""面相 / 手相分析编排：上传 → 落盘 → 视觉模型 → 校验 → 存档。

为什么不做成 `ChartResult` 的引擎：
- 引擎的契约是「同一输入同一输出」，而视觉模型每次调用结果都不同；
- 引擎的 `chart_facts` 是**事实**，而这里只有模型的观察，不能当事实存档；
- 引擎不接触数据库与计费，而这里必须走额度预扣、失败退款、图片留存期。

因此本模块是「服务」，不是「引擎」：它自己建 `chart_records` 行（`domain=face/palm`），
`chart_facts` 只放用户输入摘要与媒体元信息，模型输出走 `ai_reports` 的既有管线。

红线：不把模型输出写进 `chart_facts`，不给吉凶结论，不推断身份。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import utcnow
from app.core.errors import AppError
from app.domains.billing import ledger
from app.domains.llm.base import ImagePart, LLMRequest, LLMResponse, LLMUnavailable
from app.domains.llm.openai_compatible import OpenAICompatibleProvider
from app.domains.vision import prompts
from app.models import ChartMedia, ChartRecord
from app.repositories import chart_repo
from app.services import media

#: 视觉任务每次固定消耗 1 次额度（与报告同口径），降级时全额退回
UNITS_PER_ANALYSIS = 1


class VisionNotConfigured(AppError):
    def __init__(self) -> None:
        super().__init__(
            "VISION_NOT_CONFIGURED",
            "未配置可用的视觉模型：请在 backend/.env 设置 LLM_VISION_MODEL / LLM_VISION_API_KEY",
            status_code=503,
        )


@dataclass
class AnalysisOutcome:
    chart: ChartRecord
    media_row: ChartMedia
    response: LLMResponse | None
    degraded_reason: str | None

    @property
    def degraded(self) -> bool:
        return self.response is None


def _provider() -> OpenAICompatibleProvider:
    """按视觉模型配置构造 provider；缺配置直接拒绝，不回落到文本模型。

    不回落的理由：文本模型看不懂图片，会一本正经地编造「照片里的形态」，
    这比直接报「未配置」危险得多。
    """
    if not settings.llm_vision_configured:
        raise VisionNotConfigured()
    return OpenAICompatibleProvider(
        base_url=settings.llm_vision_base_url_value,
        api_key=settings.llm_vision_api_key_value,
        model=settings.llm_vision_model,
        timeout_seconds=settings.llm_vision_timeout_seconds,
        max_output_tokens=settings.llm_vision_max_output_tokens,
    )


def _store_media(session: Session, *, owner_id: int, kind: str, raw: bytes, mime: str) -> ChartMedia:
    stored = media.store(raw, mime)
    # 同一用户重复上传同一张图时复用已有行，避免同一张脸在库里出现多份记录
    existing = session.scalar(
        select(ChartMedia).where(
            ChartMedia.owner_user_id == owner_id,
            ChartMedia.sha256 == stored.sha256,
            ChartMedia.media_kind == kind,
            ChartMedia.deleted_at.is_(None),
        )
    )
    if existing is not None:
        return existing
    row = ChartMedia(
        owner_user_id=owner_id,
        media_kind=kind,
        mime=stored.mime,
        size_bytes=stored.size_bytes,
        width=stored.width,
        height=stored.height,
        sha256=stored.sha256,
        storage_key=stored.storage_key,
        delete_after=stored.delete_after,
    )
    session.add(row)
    session.flush()
    return row


def _facts(kind: str, media_row: ChartMedia, analysis_type: str, hand_type: str | None, question: str | None, store_question: bool) -> dict[str, Any]:
    """`chart_facts` 只放「用户输入 + 媒体元信息」，不放模型输出。"""
    facts: dict[str, Any] = {
        "media": {
            "kind": kind,
            "sha256": media_row.sha256,
            "mime": media_row.mime,
            "width": media_row.width,
            "height": media_row.height,
            "size_bytes": media_row.size_bytes,
        },
        "analysis_type": analysis_type,
    }
    if hand_type:
        facts["hand_type"] = hand_type
    if question and store_question:
        facts["question"] = question
    return facts


def analyze(
    session: Session,
    *,
    user_id: int,
    kind: str,
    raw: bytes,
    mime: str,
    analysis_type: str,
    hand_type: str | None = None,
    question: str | None = None,
    store_question: bool = True,
    idempotency_key: str,
) -> AnalysisOutcome:
    """执行一次分析。额度按「预扣 → 成功结算 / 失败退回」三态处理。"""
    if kind not in ("face", "palm"):
        raise AppError("INVALID_REQUEST", f"未知分析类型「{kind}」", status_code=400)
    provider = _provider()  # 先确认配置可用，再消耗额度

    if kind == "face":
        system_prompt = prompts.build_face_system_prompt(analysis_type)
        user_prompt = prompts.build_face_user_prompt(analysis_type, question)
        title = prompts.generate_face_title(analysis_type)
        disclaimer = prompts.FACE_DISCLAIMER
    else:
        hand = hand_type or "left"
        if hand not in prompts.HAND_TYPES:
            raise AppError("INVALID_REQUEST", f"未知手别「{hand}」", status_code=422)
        system_prompt = prompts.build_palm_system_prompt(analysis_type)
        user_prompt = prompts.build_palm_user_prompt(analysis_type, hand, question)
        title = prompts.generate_palm_title(analysis_type, hand)
        disclaimer = prompts.PALM_DISCLAIMER

    media_row = _store_media(session, owner_id=user_id, kind=kind, raw=raw, mime=mime)

    facts = _facts(kind, media_row, analysis_type, hand_type, question, store_question)
    warnings = [
        disclaimer,
        "本页内容由视觉模型生成，属描述性整理，未经人工核验。",
    ]
    chart_json = {
        "domain": kind,
        "algorithm_version": f"{kind}-prompt-0.1.0",
        "input_summary": {
            "analysis_type": analysis_type,
            **({"hand_type": hand_type} if hand_type else {}),
            **({"question": question} if question and store_question else {}),
        },
        "convention": {
            "school": f"{kind}_vision_v1",
            "school_note": "视觉模型描述性整理，无确定性算法，不做吉凶判断。",
        },
        "chart_facts": facts,
        "triggered_rules": [],
        "warnings": warnings,
        "source_refs": [
            {"type": "media", "id": media_row.sha256, "note": "用户上传的图片内容哈希"},
            {"type": "prompt", "id": f"{kind}.{analysis_type}.v1", "note": "本次使用的提示词模板"},
        ],
    }

    chart = chart_repo.create_chart(
        session,
        owner_id=user_id,
        domain=kind,
        title=title,
        input_json=chart_json["input_summary"],
        chart_json=chart_json,
        convention_json=chart_json["convention"],
        algorithm_version=chart_json["algorithm_version"],
        delete_after=utcnow() + timedelta(days=settings.media_retention_days),
    )
    media_row.chart_id = chart.id

    reservation = ledger.reserve(
        session,
        user_id=user_id,
        reference_type=kind,
        reference_id=str(chart.id),
        idempotency_key=idempotency_key,
        units=UNITS_PER_ANALYSIS,
        allow_free=False,
    )

    request = LLMRequest(
        task=f"{kind}.{analysis_type}",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        images=[ImagePart(base64_data=__import__("base64").b64encode(raw).decode("ascii"), mime_type=mime)],
        max_output_tokens=settings.llm_vision_max_output_tokens,
    )

    response: LLMResponse | None = None
    reason: str | None = None
    try:
        response = provider.generate_json(request)
    except LLMUnavailable as exc:
        reason = str(exc)

    if response is None:
        ledger.refund(session, reservation, reason="vision_unavailable")
        session.commit()
        return AnalysisOutcome(chart=chart, media_row=media_row, response=None, degraded_reason=reason)

    ledger.settle(session, reservation)
    session.commit()
    return AnalysisOutcome(chart=chart, media_row=media_row, response=response, degraded_reason=None)


def list_media(session: Session, *, user_id: int, limit: int = 20) -> list[ChartMedia]:
    return list(
        session.scalars(
            select(ChartMedia)
            .where(ChartMedia.owner_user_id == user_id, ChartMedia.deleted_at.is_(None))
            .order_by(ChartMedia.created_at.desc())
            .limit(limit)
        )
    )


def purge_expired_media(session: Session, now: datetime | None = None) -> int:
    """清理过期图片：先删文件，再把数据库行标记为已删除。"""
    moment = now or utcnow()
    rows = list(
        session.scalars(
            select(ChartMedia).where(
                ChartMedia.deleted_at.is_(None),
                ChartMedia.delete_after.is_not(None),
                ChartMedia.delete_after < moment,
            )
        )
    )
    for row in rows:
        try:
            media.resolve(row.storage_key).unlink(missing_ok=True)
        except media.MediaError:
            pass
        row.deleted_at = moment
    if rows:
        session.commit()
    return len(rows)
