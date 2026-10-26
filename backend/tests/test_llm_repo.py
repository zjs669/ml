"""调用账本的读写语义。

账本是排查"为什么这份报告是降级"的唯一依据，所以字段完整性、错误码、
按天计数与报告回填都要锁死。提示词正文不进账本（避免二次留存用户数据）。
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import utcnow
from app.models import ChartRecord
from app.models import LlmCall
from app.models import AiReport
from app.repositories import llm_repo

TASK = "bazi.overview.v1"
PROMPT_VERSION = "system_v1"


def _report(session: Session) -> AiReport:
    """建一份最小可用的报告行：llm_calls.report_id 有外键，不能随便编一个数字。"""
    chart = ChartRecord(
        domain="bazi",
        input_json={},
        chart_json={},
        convention_json={},
        algorithm_version="bazi-engine-0.1.0",
        snapshot_hash="0" * 64,
    )
    session.add(chart)
    session.flush()
    report = AiReport(
        chart_id=chart.id,
        domain="bazi",
        model_provider="openai_compatible",
        model_name="test-chat-v1",
        skill_version=f"{TASK}@1.0.0",
        prompt_version=PROMPT_VERSION,
        chart_snapshot_hash="0" * 64,
        algorithm_version="bazi-engine-0.1.0",
        depth="brief",
        report_json={},
        citations_json=[],
    )
    session.add(report)
    session.flush()
    return report


def _record(session: Session, **overrides: object) -> LlmCall:
    params: dict[str, object] = {
        "task": TASK,
        "provider": "openai_compatible",
        "model": "test-chat-v1",
        "prompt_version": PROMPT_VERSION,
        "skill_key": TASK,
    }
    params.update(overrides)
    return llm_repo.record(session, **params)  # type: ignore[arg-type]


def test_record_fills_all_fields(session: Session) -> None:
    call = _record(
        session,
        attempt=2,
        latency_ms=880,
        input_tokens=1200,
        output_tokens=640,
        ok=True,
        user_id=None,
        chart_id=None,
        meta={"finish_reason": "stop"},
    )
    session.flush()

    assert call.id is not None
    assert call.task == TASK
    assert call.provider == "openai_compatible"
    assert call.model == "test-chat-v1"
    assert call.prompt_version == PROMPT_VERSION
    assert call.skill_key == TASK
    assert call.attempt == 2
    assert call.latency_ms == 880
    assert (call.input_tokens, call.output_tokens) == (1200, 640)
    assert call.ok is True
    assert call.error_code is None
    assert call.meta_json == {"finish_reason": "stop"}
    assert call.created_at is not None


def test_failed_call_keeps_error_code(session: Session) -> None:
    call = _record(session, ok=False, error_code="llm_unavailable")
    session.flush()

    assert call.ok is False
    assert call.error_code == "llm_unavailable"
    assert call.latency_ms is None


def test_error_code_is_truncated_to_column_width(session: Session) -> None:
    call = _record(session, ok=False, error_code="x" * 300)
    session.flush()

    assert call.error_code is not None
    assert len(call.error_code) == 120


def test_cost_is_estimated_only_when_price_configured(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "llm_price_input_per_1k", 0.0)
    monkeypatch.setattr(settings, "llm_price_output_per_1k", 0.0)
    free_call = _record(session, input_tokens=1000, output_tokens=1000)
    session.flush()
    assert free_call.cost_estimate is None

    monkeypatch.setattr(settings, "llm_price_input_per_1k", 2.0)
    monkeypatch.setattr(settings, "llm_price_output_per_1k", 8.0)
    priced = _record(session, input_tokens=1500, output_tokens=500)
    session.flush()
    assert float(priced.cost_estimate) == pytest.approx(3.0 + 4.0)


def test_count_today_ignores_yesterday(session: Session) -> None:
    today = _record(session)
    session.flush()
    old = _record(session)
    old.created_at = utcnow() - timedelta(days=1)
    session.flush()

    before = llm_repo.count_today(session)
    assert before >= 1
    assert session.get(LlmCall, old.id).created_at.date() < utcnow().date()

    _record(session)
    session.flush()
    assert llm_repo.count_today(session) == before + 1
    assert session.get(LlmCall, today.id) is not None


def test_attach_report_links_calls(session: Session) -> None:
    first = _record(session)
    second = _record(session, attempt=2, ok=False, error_code="llm_unavailable")
    session.flush()

    report_id = _report(session).id
    llm_repo.attach_report(session, call_ids=[first.id, second.id], report_id=report_id)
    session.flush()

    linked = session.scalars(
        select(LlmCall).where(LlmCall.report_id == report_id).order_by(LlmCall.attempt)
    ).all()
    assert [item.id for item in linked] == [first.id, second.id]


def test_attach_report_with_empty_list_is_noop(session: Session) -> None:
    call = _record(session)
    session.flush()
    llm_repo.attach_report(session, call_ids=[], report_id=_report(session).id)
    session.flush()
    assert call.report_id is None


def test_recent_stats_success_rate(session: Session) -> None:
    _record(session)
    _record(session, ok=False, error_code="llm_unavailable", attempt=2)
    session.flush()

    stats = llm_repo.recent_stats(session, hours=24)
    assert stats["window_hours"] == 24
    assert stats["calls"] >= 2
    assert stats["failed"] >= 1
    assert stats["success_rate"] is not None
    assert 0 <= stats["success_rate"] <= 1


def test_recent_stats_without_calls_reports_none(session: Session) -> None:
    stats = llm_repo.recent_stats(session, hours=0)
    assert stats["calls"] == 0
    assert stats["success_rate"] is None
