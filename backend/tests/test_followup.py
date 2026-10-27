"""报告追问：接口、轮次上限、预算降级、越权与引用边界。

追问的设计约束：
- 只能引用原报告 `citations_json` 里的 chunk_id；
- 不扣额度，但受日预算与限流约束；
- 模型输出不合格时返回确定性降级回答，且不污染原报告。
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.reporting import followup as followup_service
from app.models import KnowledgeChunk, KnowledgeSource
from app.repositories import llm_repo

PASSWORD = "Passw0rd123"
TOPICS = ("六合", "三合", "相冲", "十神", "藏干", "大运")


@pytest.fixture
def knowledge(session: Session) -> list[int]:
    key = uuid.uuid4().hex[:8]
    source = KnowledgeSource(
        title=f"追问测试源-{key}",
        author="测试",
        edition="测试版",
        license_status="public_domain",
        status="approved",
    )
    session.add(source)
    session.flush()
    chunks: list[KnowledgeChunk] = []
    for index, topic in enumerate(TOPICS):
        chunk = KnowledgeChunk(
            source_id=source.id,
            domain="bazi",
            topic=topic,
            content=f"{topic}的测试释义 {index}：仅用于验证引用链路。",
            citation_label=f"测试出处·{topic}",
            location=f"测试章节·{topic}",
            keywords=topic,
            content_hash=f"{key}-{index}",
            approval_status="approved",
        )
        session.add(chunk)
        chunks.append(chunk)
    session.flush()
    return [chunk.id for chunk in chunks]


def _signup(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"fu_{uuid.uuid4().hex[:10]}@example.com", "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _report(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    chart = client.post(
        "/api/v1/charts",
        json={
            "birth_datetime": "1990-05-20T12:00:00",
            "timezone": "Asia/Shanghai",
            "gender": "male",
            "title": "追问用命盘",
        },
        headers=headers,
    ).json()
    created = client.post(
        f"/api/v1/charts/{chart['id']}/reports",
        json={"depth": "brief"},
        headers={**headers, "Idempotency-Key": f"fu-{uuid.uuid4().hex}"},
    )
    assert created.status_code == 201, created.text
    return created.json()


def _ask(client: TestClient, headers: dict[str, str], report_id: int, question: str):
    return client.post(
        f"/api/v1/reports/{report_id}/followups", json={"question": question}, headers=headers
    )


class _StubProvider:
    """可控 Provider：返回预设 payload，用来触发校验失败分支。"""

    name = "stub"
    model = "stub-v1"

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def generate_json(self, request):
        from app.domains.llm.base import LLMResponse

        return LLMResponse(
            payload=self.payload,
            provider=self.name,
            model=self.model,
            input_tokens=10,
            output_tokens=10,
            latency_ms=1,
            finish_reason="stop",
        )


def test_followup_requires_login(client: TestClient) -> None:
    response = client.post("/api/v1/reports/1/followups", json={"question": "为什么？"})
    assert response.status_code == 401


def test_followup_roundtrip(client: TestClient, knowledge: list[int]) -> None:
    headers = _signup(client)
    report = _report(client, headers)

    response = _ask(client, headers, report["id"], "为什么日主是这样判断的？")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["seq"] == 1
    assert body["status"] == "complete"
    assert body["answer"]["answer"]
    assert body["answer"]["safety_note"]
    # 引用只能来自原报告的片段
    allowed = {item["chunk_id"] for item in report["citations"]}
    assert set(body["answer"]["citations"]) <= allowed
    assert {item["chunk_id"] for item in body["citations"]} <= allowed


def test_followup_list_is_ordered(client: TestClient, knowledge: list[int]) -> None:
    headers = _signup(client)
    report = _report(client, headers)
    for question in ("第一个问题是什么？", "第二个问题是什么？"):
        assert _ask(client, headers, report["id"], question).status_code == 201

    listed = client.get(f"/api/v1/reports/{report['id']}/followups", headers=headers)
    assert listed.status_code == 200
    seqs = [item["seq"] for item in listed.json()]
    assert seqs == [1, 2]


def test_followup_turn_limit(client: TestClient, knowledge: list[int], monkeypatch) -> None:
    monkeypatch.setattr(followup_service, "MAX_TURNS", 2)
    headers = _signup(client)
    report = _report(client, headers)
    assert _ask(client, headers, report["id"], "第一轮的问题").status_code == 201
    assert _ask(client, headers, report["id"], "第二轮的问题").status_code == 201

    blocked = _ask(client, headers, report["id"], "第三轮的问题")
    assert blocked.status_code == 400
    assert blocked.json()["error"]["code"] == "FOLLOWUP_LIMIT"


def test_budget_exhaustion_degrades_without_calling_model(
    client: TestClient, knowledge: list[int], monkeypatch
) -> None:
    headers = _signup(client)
    report = _report(client, headers)
    monkeypatch.setattr(llm_repo, "count_today", lambda session: 10**6)
    monkeypatch.setattr(followup_service.llm_repo, "count_today", lambda session: 10**6)

    response = _ask(client, headers, report["id"], "预算用尽时还能回答吗？")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "degraded"
    assert body["model_provider"] == "fallback"
    assert any("预算" in text for text in body["answer"]["uncertainties"])
    # 预算用尽属于「模型侧没跑起来」，不是「材料不够」：前端应引导稍后重试
    assert body["answer"]["reason_kind"] == "MODEL_UNAVAILABLE"
    # 降级只复述原报告已核验的事实，不编造新句子
    assert body["answer"]["citations"] == []


def test_cannot_ask_on_someone_elses_report(client: TestClient, knowledge: list[int]) -> None:
    owner = _signup(client)
    report = _report(client, owner)

    intruder = _signup(client)
    response = _ask(client, intruder, report["id"], "别人的报告也能问？")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "REPORT_NOT_FOUND"


def test_question_length_is_bounded(client: TestClient, knowledge: list[int]) -> None:
    headers = _signup(client)
    report = _report(client, headers)
    assert _ask(client, headers, report["id"], "问").status_code == 422
    assert _ask(client, headers, report["id"], "问" * 501).status_code == 422


def test_validation_failure_degrades_as_out_of_scope(
    client: TestClient, knowledge: list[int], monkeypatch
) -> None:
    """模型答了但引用越界 → 属于「材料不够」，引导用户重新生成报告。

    这是两类降级里更容易被误解的一类：用户看到「答不上来」会以为系统坏了，
    于是反复重试同一个问题 —— 而重试永远不会成功，因为材料本来就没有。
    """
    headers = _signup(client)
    report = _report(client, headers)

    # 引用一个不在原报告 citations 里的 chunk_id，校验必然判死
    bogus = max(knowledge) + 999
    payload = {
        "answer": "引用了不存在的片段。",
        "points": [],
        "citations": [bogus],
        "uncertainties": [],
        "safety_note": "仅供传统文化研习。",
    }
    stub = _StubProvider(payload)
    monkeypatch.setattr(followup_service, "get_provider", lambda *a, **k: stub)

    response = _ask(client, headers, report["id"], "这个报告里没提的问题？")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "degraded"
    assert body["answer"]["reason_kind"] == "OUT_OF_SCOPE"


def test_unconfigured_model_degrades_as_model_unavailable(
    client: TestClient, knowledge: list[int], monkeypatch
) -> None:
    """模型没配置 → 属于「模型侧没跑起来」，引导稍后重试。"""
    from app.domains.llm.base import LLMUnavailable

    headers = _signup(client)
    report = _report(client, headers)

    def _boom(*args, **kwargs):
        raise LLMUnavailable("未配置可用的大模型")

    monkeypatch.setattr(followup_service, "get_provider", _boom)

    response = _ask(client, headers, report["id"], "模型没配置时会怎样？")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "degraded"
    assert body["answer"]["reason_kind"] == "MODEL_UNAVAILABLE"


def test_reason_kind_maps_internal_kinds() -> None:
    """内部失败原因到对外两类的映射，未知值保守归为「模型不可用」。"""
    assert followup_service.reason_kind("validation") == "OUT_OF_SCOPE"
    assert followup_service.reason_kind("budget") == "MODEL_UNAVAILABLE"
    assert followup_service.reason_kind("upstream") == "MODEL_UNAVAILABLE"
    assert followup_service.reason_kind("unconfigured") == "MODEL_UNAVAILABLE"
    # 未知值：不引导用户重做报告（重做大概率也没用），让他先重试
    assert followup_service.reason_kind("something_new") == "MODEL_UNAVAILABLE"
