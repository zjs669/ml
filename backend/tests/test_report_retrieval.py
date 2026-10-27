"""报告检索的端到端回归：盘面触发的关系，必须能检索到对应典籍条文。

这是一条真实失效链路的守卫：

    1990-05-20 12:10 的盘，triggered_rules 里有 天干五合 / 天干相克 / 天干相冲
      → bazi.relations.v1 的静态 topics 只有地支七项
      → 知识库里的《渊海子平·天干五合》《天干相冲》从不被召回
      → 模型照实说「本次提供的片段没有天干条文」，citations 为空
      → 用户看到「模型答不上来」

所以这里不测「检索函数返回了什么」，而是直接跑一遍报告链路，
断言**天干条文真的进了模型上下文**。上下文拿不到就断言 citations ——
两者都是「模型能看到什么」的代理，但 citations 更贴近用户可见结果。
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.llm.base import LLMRequest, LLMResponse
from app.domains.reporting import service as reporting_service
from app.models import KnowledgeChunk, KnowledgeSource

PASSWORD = "Passw0rd123"

#: 这份盘必然同时触发天干与地支关系（乙庚合、辛克乙、乙辛冲、午午自刑、巳午半会）
CHART_BIRTH = "1990-05-20T12:10:00"


class _RecordingProvider:
    """把模型实际收到的 user prompt 存下来，用于断言检索上下文。"""

    name = "recording"
    model = "recording-v1"

    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []
        self.payload: dict[str, Any] = {}

    def generate_json(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(
            payload=self.payload,
            provider=self.name,
            model=self.model,
            input_tokens=10,
            output_tokens=10,
            latency_ms=1,
            finish_reason="stop",
        )


def _signup(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"retrieval_{uuid.uuid4().hex[:10]}@example.com", "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _chart(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = client.post(
        "/api/v1/charts",
        json={"birth_datetime": CHART_BIRTH, "timezone": "Asia/Shanghai", "gender": "male"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def stem_chunks(session: Session) -> dict[str, int]:
    """造天干条文，模拟《渊海子平·天干五合》《天干相冲》在库里的样子。

    自带一份而不是依赖真实典籍片段：测试要验证的是「检索链路能不能把
    天干主题的片段送进模型上下文」，而不是「某本书里有没有这句话」。
    """
    key = uuid.uuid4().hex[:8]
    source = KnowledgeSource(
        title=f"天干条文源-{key}",
        author="测试",
        edition="测试版",
        license_status="public_domain",
        status="approved",
    )
    session.add(source)
    session.flush()

    payload = {
        "天干五合": "甲己合土、乙庚合金、丙辛合水、丁壬合木、戊癸合火。",
        "天干相冲": "甲庚相冲、乙辛相冲、丙壬相冲、丁癸相冲。天干之冲，同阴阳而相克。",
    }
    ids: dict[str, int] = {}
    for topic, body in payload.items():
        chunk = KnowledgeChunk(
            source_id=source.id,
            domain="bazi",
            topic=topic,
            content=body,
            citation_label=f"测试出处·{topic}",
            content_hash=f"{key}-{topic}",
            approval_status="approved",
        )
        session.add(chunk)
        session.flush()
        ids[topic] = chunk.id
    session.commit()
    return ids


def test_report_context_contains_stem_chunks(
    client: TestClient,
    session: Session,
    stem_chunks: dict[str, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """盘面触发了天干关系 → 模型上下文里必须出现天干条文。"""
    headers = _signup(client)
    chart = _chart(client, headers)

    provider = _RecordingProvider()
    provider.payload = {
        "summary": "盘面事实陈述",
        "observations": [{"fact": "日干为乙", "rule_ids": [], "citation_ids": []}],
        "traditional_interpretations": [],
        "practical_reflections": ["以现实证据为准。"],
        "uncertainties": [],
        "citations": [],
        "safety_note": "仅供传统文化研习。",
    }
    monkeypatch.setattr(reporting_service, "get_provider", lambda *a, **k: provider)

    response = client.post(
        f"/api/v1/charts/{chart['id']}/reports",
        json={"depth": "brief"},
        headers={**headers, "Idempotency-Key": f"retrieval-{uuid.uuid4().hex}"},
    )
    assert response.status_code == 201, response.text
    assert provider.requests, "模型必须被调用一次"

    context = provider.requests[0].user_prompt
    assert f"[{stem_chunks['天干五合']}]" in context or "天干五合" in context, (
        "盘面触发了天干五合，检索却没有把对应条文放进上下文"
    )
    assert f"[{stem_chunks['天干相冲']}]" in context or "天干相冲" in context, (
        "盘面触发了天干相冲，检索却没有把对应条文放进上下文"
    )


def test_stem_citations_reach_report(
    client: TestClient,
    session: Session,
    stem_chunks: dict[str, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """模型引用了天干条文时，服务端校验必须通过（引用确实在检索结果里）。"""
    headers = _signup(client)
    chart = _chart(client, headers)

    chunk_id = stem_chunks["天干相冲"]
    provider = _RecordingProvider()
    provider.payload = {
        "summary": "盘面事实陈述",
        "observations": [{"fact": "日干为乙", "rule_ids": [], "citation_ids": []}],
        "traditional_interpretations": [
            {
                "claim": "天干之冲，同阴阳而相克。",
                "citation_ids": [chunk_id],
                "school_note": None,
            }
        ],
        "practical_reflections": ["以现实证据为准。"],
        "uncertainties": [],
        "citations": [chunk_id],
        "safety_note": "仅供传统文化研习。",
    }
    monkeypatch.setattr(reporting_service, "get_provider", lambda *a, **k: provider)

    response = client.post(
        f"/api/v1/charts/{chart['id']}/reports",
        json={"depth": "brief"},
        headers={**headers, "Idempotency-Key": f"retrieval-{uuid.uuid4().hex}"},
    )
    assert response.status_code == 201, response.text

    body = response.json()
    assert body["status"] == "complete", body["validation"]
    assert chunk_id in {item["chunk_id"] for item in body["citations"]}
    assert body["validation"]["ok"] is True
