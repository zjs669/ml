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
