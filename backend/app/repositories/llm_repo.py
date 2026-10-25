"""模型调用账本的读写。

预算熔断读的是"当天调用条数"，不是 token 数：条数可以在不依赖上游计价的前提下
给出稳定的上限，避免因为价格表变动导致预算失效。
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import utcnow
from app.models.llm import LlmCall


def record(
    session: Session,
    *,
    task: str,
    provider: str,
    model: str,
    prompt_version: str,
    skill_key: str = "",
    attempt: int = 1,
    latency_ms: int | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    ok: bool = True,
    error_code: str | None = None,
    user_id: int | None = None,
    chart_id: int | None = None,
    report_id: int | None = None,
    meta: dict[str, Any] | None = None,
) -> LlmCall:
    entry = LlmCall(
        user_id=user_id,
        chart_id=chart_id,
        report_id=report_id,
        task=task,
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        skill_key=skill_key,
        attempt=attempt,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_estimate=settings.estimate_cost(input_tokens, output_tokens),
        ok=ok,
        error_code=(error_code or None) and error_code[:120],
        meta_json=meta,
    )
    session.add(entry)
    session.flush()
    return entry


def attach_report(session: Session, *, call_ids: list[int], report_id: int) -> None:
    """报告落库后回填关联，便于"这份报告到底调了几次模型"一句 SQL 查清。"""
    if not call_ids:
        return
    session.execute(
        update(LlmCall).where(LlmCall.id.in_(call_ids)).values(report_id=report_id)
    )


def count_today(session: Session) -> int:
    midnight = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return int(
        session.scalar(select(func.count()).select_from(LlmCall).where(LlmCall.created_at >= midnight))
        or 0
    )


def recent_stats(session: Session, *, hours: int = 24) -> dict[str, Any]:
    since = utcnow() - timedelta(hours=hours)
    total = int(
        session.scalar(select(func.count()).select_from(LlmCall).where(LlmCall.created_at >= since))
        or 0
    )
    failed = int(
        session.scalar(
            select(func.count())
            .select_from(LlmCall)
            .where(LlmCall.created_at >= since, LlmCall.ok.is_(False))
        )
        or 0
    )
    return {
        "window_hours": hours,
        "calls": total,
        "failed": failed,
        "success_rate": round((total - failed) / total, 4) if total else None,
    }
