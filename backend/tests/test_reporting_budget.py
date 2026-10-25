"""预算熔断与降级退款语义。

三条硬约束（计划 R1-C）：
1. 当日调用条数达到 `LLM_DAILY_TOTAL_BUDGET` 时**不发请求**，直接降级；
2. 降级 / 上游失败 / 未配置 key 三种情况都必须把预扣额度**真正退回**（免费次数也要回来）；
3. 每次真实发生的调用（成功或失败）都要落 `llm_calls`，并能回填到报告。
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domains.llm.base import LLMRequest, LLMResponse, LLMUnavailable
from app.domains.reporting import service as reporting_service
from app.models.billing import UsageLedger
from app.models.knowledge import KnowledgeChunk, KnowledgeSource
from app.models.llm import LlmCall
from app.repositories import llm_repo

PASSWORD = "Passw0rd123"


class _StubProvider:
    """可控 Provider：按预设行为返回 payload 或抛错，并统计调用次数。"""

    name = "stub"
    model = "stub-v1"

    def __init__(self, behavior: Any) -> None:
        self.behavior = behavior
        self.calls = 0

    def generate_json(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        if isinstance(self.behavior, Exception):
            raise self.behavior
        return LLMResponse(
            payload=self.behavior,
            provider=self.name,
            model=self.model,
            input_tokens=100,
            output_tokens=50,
            latency_ms=42,
            finish_reason="stop",
        )


@pytest.fixture
def knowledge(session: Session) -> dict[str, Any]:
    key = uuid.uuid4().hex[:8]
    source = KnowledgeSource(
        title=f"预算测试知识源-{key}",
        author="测试",
        edition="测试版",
        license_status="public_domain",
        status="approved",
    )
    session.add(source)
    session.flush()
    chunk = KnowledgeChunk(
        source_id=source.id,
        domain="bazi",
        topic="六合",
        content="六合的测试释义片段：用于验证预算熔断时仍能给出引用条目。",
        citation_label="测试出处·六合",
        location="测试章节",
        keywords="六合",
        content_hash=f"{key}-0",
        approval_status="approved",
    )
    session.add(chunk)
    session.flush()
    return {"chunk_id": chunk.id}


def _signup(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"budget_{uuid.uuid4().hex[:10]}@example.com", "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _chart(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = client.post(
        "/api/v1/charts",
        json={
            "birth_datetime": "1990-05-20T12:10:00",
            "timezone": "Asia/Shanghai",
            "gender": "male",
            "title": "预算用命盘",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _generate(client: TestClient, headers: dict[str, str], chart_id: int) -> Any:
    return client.post(
        f"/api/v1/charts/{chart_id}/reports",
        json={"depth": "brief"},
        headers={**headers, "Idempotency-Key": f"budget-{uuid.uuid4().hex}"},
    )


def _uncertainties(body: dict[str, Any]) -> str:
    return " ".join(body["report"]["uncertainties"])


def test_budget_exhausted_skips_model_and_refunds(
    client: TestClient, session: Session, knowledge: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _signup(client)
    chart = _chart(client, headers)

    # 当天已经用掉一次调用额度，把上限压到 1 → 下一条请求必须被熔断
    llm_repo.record(
        session,
        task="bazi.overview.v1",
        provider="mock",
        model="mock-deterministic-v1",
        prompt_version=settings.prompt_version,
        skill_key="warm_up",
        ok=True,
    )
    session.flush()
    monkeypatch.setattr(settings, "llm_daily_total_budget", 1)

    stub = _StubProvider({"summary": "不应被调用"})
    monkeypatch.setattr(reporting_service, "get_provider", lambda *a, **k: stub)

    response = _generate(client, headers, chart["id"])
    assert response.status_code == 201, response.text

    body = response.json()
    assert body["status"] == "degraded"
    assert stub.calls == 0, "熔断后不得再发出模型请求"
    text = _uncertainties(body)
    assert "预算已用尽" in text
    assert "全额退还" in text
    assert body["model_provider"] == "fallback"
    assert body["validation"]["ok"] is False

    calls = session.scalars(select(LlmCall)).all()
    assert len(calls) == 1, "只应有那条预热记录，本次没有新增调用"
    assert calls[0].skill_key == "warm_up"

    # 免费额度必须回到手：今天仍然可以生成一次
    usage = client.get("/api/v1/me/usage", headers=headers).json()
    assert usage["daily_free_used"] == 0
    assert usage["can_generate"] is True

    refunds = session.scalars(
        select(UsageLedger).where(UsageLedger.event_type == "refund")
    ).all()
    assert refunds, "降级必须写退回记录"
    settles = session.scalars(select(UsageLedger).where(UsageLedger.event_type == "settle")).all()
    assert not settles, "降级不得结算"


def test_missing_api_key_degrades_without_calling_model(
    client: TestClient, session: Session, knowledge: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _signup(client)
    chart = _chart(client, headers)
    monkeypatch.setattr(settings, "llm_mode", "openai_compatible")
    monkeypatch.setattr(settings, "llm_api_key", "")

    response = _generate(client, headers, chart["id"])
    assert response.status_code == 201, response.text

    body = response.json()
    assert body["status"] == "degraded"
    text = _uncertainties(body)
    assert "LLM_API_KEY" in text
    assert "全额退还" in text

    usage = client.get("/api/v1/me/usage", headers=headers).json()
    assert usage["daily_free_used"] == 0


def test_upstream_failure_records_two_attempts_and_refunds(
    client: TestClient, session: Session, knowledge: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _signup(client)
    chart = _chart(client, headers)

    stub = _StubProvider(LLMUnavailable("上游服务异常（HTTP 500）"))
    monkeypatch.setattr(reporting_service, "get_provider", lambda *a, **k: stub)

    response = _generate(client, headers, chart["id"])
    assert response.status_code == 201, response.text

    body = response.json()
    assert body["status"] == "degraded"
    assert stub.calls == 2, "默认做一次受控重试"

    calls = session.scalars(
        select(LlmCall).where(LlmCall.chart_id == chart["id"]).order_by(LlmCall.attempt)
    ).all()
    assert [item.attempt for item in calls] == [1, 2]
    assert all(item.ok is False for item in calls)
    assert all(item.error_code == "llm_unavailable" for item in calls)
    assert all(item.report_id == body["id"] for item in calls)

    assert "上游" in _uncertainties(body)
    usage = client.get("/api/v1/me/usage", headers=headers).json()
    assert usage["daily_free_used"] == 0


def test_validation_failure_twice_degrades_with_hint(
    client: TestClient, session: Session, knowledge: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _signup(client)
    chart = _chart(client, headers)

    stub = _StubProvider({})  # 缺字段 → 两次都过不了校验
    monkeypatch.setattr(reporting_service, "get_provider", lambda *a, **k: stub)

    response = _generate(client, headers, chart["id"])
    assert response.status_code == 201, response.text

    body = response.json()
    assert body["status"] == "degraded"
    assert stub.calls == 2
    # 上游是成功的（拿到了 JSON），失败在于校验，所以 ok=True 但报告降级
    calls = session.scalars(select(LlmCall).where(LlmCall.chart_id == chart["id"])).all()
    assert len(calls) == 2
    assert all(item.ok is True for item in calls)
    assert "未通过服务端校验" in _uncertainties(body)


def test_successful_call_is_recorded_and_linked(
    client: TestClient, session: Session, knowledge: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _signup(client)
    chart = _chart(client, headers)

    payload = {
        "summary": "盘面事实陈述",
        "observations": [{"fact": "年柱为庚午", "rule_ids": [], "citation_ids": []}],
        "traditional_interpretations": [
            {
                "claim": "六合为地支关系的传统称谓之一。",
                "citation_ids": [knowledge["chunk_id"]],
                "school_note": "测试章节",
            }
        ],
        "practical_reflections": ["以现实证据为准。"],
        "uncertainties": ["不同流派口径存在差异。"],
        "citations": [knowledge["chunk_id"]],
        "safety_note": "仅供传统文化研习，不构成任何专业建议。",
    }
    stub = _StubProvider(payload)
    monkeypatch.setattr(reporting_service, "get_provider", lambda *a, **k: stub)

    response = _generate(client, headers, chart["id"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "complete", body["validation"]
    assert stub.calls == 1

    calls = session.scalars(select(LlmCall).where(LlmCall.chart_id == chart["id"])).all()
    assert len(calls) == 1
    call = calls[0]
    assert call.provider == "stub"
    assert call.model == "stub-v1"
    assert call.latency_ms == 42
    assert (call.input_tokens, call.output_tokens) == (100, 50)
    assert call.report_id == body["id"]
    assert call.user_id is not None
    assert call.ok is True
    # dropped_keys 为空说明模型本来就按契约输出，没有被整形层改结构；
    # skills_used 是每轮必读技能的归因字段，不属于模型输出
    assert call.meta_json["finish_reason"] == "stop"
    assert call.meta_json["dropped_keys"] == []
    assert "common.skill" in call.meta_json["skills_used"]
