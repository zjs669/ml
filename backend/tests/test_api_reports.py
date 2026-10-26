"""报告接口测试：生成、幂等重放、额度、越权、知识库引用。"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import KnowledgeChunk, KnowledgeSource

PASSWORD = "Passw0rd123"
APPROVED_TOPICS = ("六合", "三合", "相冲", "十神", "藏干", "大运")


@pytest.fixture
def knowledge(session: Session) -> dict[str, Any]:
    """直接落库两条 approved + 一条 pending，用于验证审核态过滤。"""
    key = uuid.uuid4().hex[:8]
    source = KnowledgeSource(
        title=f"测试知识源-{key}",
        author="测试",
        edition="测试版",
        license_status="public_domain",
        status="approved",
    )
    session.add(source)
    session.flush()

    chunks: list[KnowledgeChunk] = []
    for index, topic in enumerate(APPROVED_TOPICS):
        chunk = KnowledgeChunk(
            source_id=source.id,
            domain="bazi",
            topic=topic,
            content=f"{topic}的测试释义片段 {index}：用于验证报告引用链路，不带任何吉凶判断。",
            citation_label=f"测试出处·{topic}",
            location=f"测试章节·{topic}",
            keywords=topic,
            content_hash=f"{key}-{index}",
            approval_status="approved",
        )
        session.add(chunk)
        chunks.append(chunk)

    pending = KnowledgeChunk(
        source_id=source.id,
        domain="bazi",
        topic="六合",
        content="六合未审核片段：不应出现在任何检索结果中。",
        citation_label="未审核出处",
        content_hash=f"{key}-pending",
        approval_status="pending",
    )
    session.add(pending)
    session.flush()
    return {"source_id": source.id, "approved": [c.id for c in chunks], "pending": pending.id}


def _signup(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"rep_{uuid.uuid4().hex[:10]}@example.com", "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _chart(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = client.post(
        "/api/v1/charts",
        json={
            "birth_datetime": "2001-02-04T15:20:00",
            "timezone": "Asia/Shanghai",
            "gender": "male",
            "title": "报告用命盘",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _generate(
    client: TestClient,
    headers: dict[str, str],
    chart_id: int,
    *,
    key: str | None = None,
    depth: str = "brief",
    topic: str | None = None,
) -> Any:
    return client.post(
        f"/api/v1/charts/{chart_id}/reports",
        json={"depth": depth, "topic": topic},
        headers={**headers, "Idempotency-Key": key or f"test-{uuid.uuid4().hex}"},
    )


def _buy(client: TestClient, headers: dict[str, str], plan_code: str = "report_once") -> dict[str, Any]:
    created = client.post("/api/v1/billing/orders", json={"plan_code": plan_code}, headers=headers)
    assert created.status_code == 201, created.text
    callback = created.json()["mock_callback"]
    paid = client.post(
        callback["url"],
        content=callback["body_raw"].encode("utf-8"),
        headers={callback["header"]: callback["signature"]},
    )
    assert paid.status_code == 200, paid.text
    return created.json()


def test_report_requires_login(client: TestClient) -> None:
    response = client.post(
        "/api/v1/charts/1/reports", json={}, headers={"Idempotency-Key": "anonymous-key"}
    )
    assert response.status_code == 401


def test_idempotency_key_is_mandatory(client: TestClient) -> None:
    headers = _signup(client)
    chart = _chart(client, headers)
    response = client.post(f"/api/v1/charts/{chart['id']}/reports", json={}, headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_brief_report_is_complete(client: TestClient, knowledge: dict[str, Any]) -> None:
    headers = _signup(client)
    chart = _chart(client, headers)
    response = _generate(client, headers, chart["id"])
    assert response.status_code == 201, response.text

    body = response.json()
    assert body["status"] == "complete"
    assert body["model_provider"] == "mock"
    assert body["skill_version"].startswith("bazi.")
    assert body["prompt_version"]
    assert body["algorithm_version"] == chart["algorithm_version"]
    assert body["chart_snapshot_hash"]
    assert body["validation"]["ok"] is True

    report = body["report"]
    assert set(report) == {
        "summary",
        "observations",
        "traditional_interpretations",
        "practical_reflections",
        "uncertainties",
        "citations",
        "safety_note",
    }
    assert report["observations"]
    assert report["safety_note"]
    # Mock 只陈述事实与引用，不得输出吉凶断言
    text = " ".join(
        [report["summary"]]
        + [item["fact"] for item in report["observations"]]
        + [item["claim"] for item in report["traditional_interpretations"]]
    )
    assert not any(term in text for term in ("必定", "注定", "血光之灾"))


def test_report_citations_only_include_approved_chunks(
    client: TestClient, knowledge: dict[str, Any]
) -> None:
    headers = _signup(client)
    chart = _chart(client, headers)
    body = _generate(client, headers, chart["id"]).json()

    cited = {item["chunk_id"] for item in body["citations"]}
    assert cited
    assert knowledge["pending"] not in cited
    assert cited <= set(knowledge["approved"])
    # 每条传统解释都必须带真实引用
    for item in body["report"]["traditional_interpretations"]:
        assert item["citation_ids"]
        assert set(item["citation_ids"]) <= cited


def test_report_replay_with_same_key(client: TestClient, knowledge: dict[str, Any]) -> None:
    headers = _signup(client)
    chart = _chart(client, headers)
    key = f"replay-{uuid.uuid4().hex}"

    first = _generate(client, headers, chart["id"], key=key)
    second = _generate(client, headers, chart["id"], key=key)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert second.json()["validation"]["replayed"] is True

    usage = client.get("/api/v1/me/usage", headers=headers).json()
    assert usage["daily_free_used"] == 1  # 重放不重复计费


def test_detailed_report_needs_paid_quota(client: TestClient, knowledge: dict[str, Any]) -> None:
    headers = _signup(client)
    chart = _chart(client, headers)
    response = _generate(client, headers, chart["id"], depth="detailed")
    assert response.status_code == 402
    assert response.json()["error"]["code"] == "QUOTA_EXCEEDED"


def test_detailed_report_after_purchase(client: TestClient, knowledge: dict[str, Any]) -> None:
    headers = _signup(client)
    chart = _chart(client, headers)
    order = _buy(client, headers)
    assert order["order"]["status"] == "pending"

    response = _generate(client, headers, chart["id"], depth="detailed")
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "complete"

    usage = client.get("/api/v1/me/usage", headers=headers).json()
    assert usage["paid_balance"] == 0
    assert usage["can_generate"] is True  # 当日免费额度仍未使用


def test_free_quota_exhausted_after_one_brief_report(
    client: TestClient, knowledge: dict[str, Any]
) -> None:
    headers = _signup(client)
    chart = _chart(client, headers)
    assert _generate(client, headers, chart["id"]).status_code == 201
    second = _generate(client, headers, chart["id"], topic="十神")
    assert second.status_code == 402
    assert second.json()["error"]["code"] == "QUOTA_EXCEEDED"


def test_report_on_others_chart_is_404(client: TestClient, knowledge: dict[str, Any]) -> None:
    owner = _signup(client)
    chart = _chart(client, owner)
    intruder = _signup(client)
    response = _generate(client, intruder, chart["id"])
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CHART_NOT_FOUND"


def test_report_detail_and_list(client: TestClient, knowledge: dict[str, Any]) -> None:
    headers = _signup(client)
    chart = _chart(client, headers)
    created = _generate(client, headers, chart["id"]).json()

    detail = client.get(f"/api/v1/reports/{created['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["id"] == created["id"]

    listing = client.get(f"/api/v1/charts/{chart['id']}/reports", headers=headers)
    assert listing.status_code == 200
    items = listing.json()
    assert len(items) == 1
    assert items[0]["summary"]
    assert items[0]["status"] == "complete"


def test_report_detail_cross_user_is_404(client: TestClient, knowledge: dict[str, Any]) -> None:
    owner = _signup(client)
    chart = _chart(client, owner)
    report = _generate(client, owner, chart["id"]).json()

    intruder = _signup(client)
    assert client.get(f"/api/v1/reports/{report['id']}", headers=intruder).status_code == 404
    assert client.get(f"/api/v1/charts/{chart['id']}/reports", headers=intruder).status_code == 404


def test_unknown_skill_key_is_rejected(client: TestClient, knowledge: dict[str, Any]) -> None:
    headers = _signup(client)
    chart = _chart(client, headers)
    response = client.post(
        f"/api/v1/charts/{chart['id']}/reports",
        json={"depth": "brief", "skill_key": "bazi.no_such_skill"},
        headers={**headers, "Idempotency-Key": f"sk-{uuid.uuid4().hex}"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "SKILL_REJECTED"


def test_knowledge_search_endpoint(client: TestClient, knowledge: dict[str, Any]) -> None:
    response = client.get("/api/v1/knowledge/search", params={"q": "六合", "domain": "bazi"})
    assert response.status_code == 200
    items = response.json()["items"]
    assert items
    assert all(item["chunk_id"] in set(knowledge["approved"]) for item in items)
    assert knowledge["pending"] not in {item["chunk_id"] for item in items}


def test_knowledge_chunk_detail(client: TestClient, knowledge: dict[str, Any]) -> None:
    chunk_id = knowledge["approved"][0]
    response = client.get(f"/api/v1/knowledge/chunks/{chunk_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["source"]["license_status"] == "public_domain"
    assert body["content"]
    assert client.get("/api/v1/knowledge/chunks/99999999").status_code == 404
