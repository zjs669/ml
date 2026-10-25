"""紫微接口层测试：通用计算入口、通用保存入口、列表摘要、校验链分派。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi.testclient import TestClient

from app.domains.llm.validator import validate
from app.domains.llm.mock import SAFETY_NOTE
from app.domains.ziwei.engine import calculate
from app.domains.ziwei.schemas import ZiweiInput

PASSWORD = "Passw0rd123"
CALC = "/api/v1/charts/ziwei/calculate"


def _headers(client: TestClient) -> dict[str, str]:
    email = f"zw_{uuid.uuid4().hex[:10]}@example.com"
    response = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _payload(**overrides: Any) -> dict[str, Any]:
    body = {
        "birth_datetime": "1990-05-20T12:00:00",
        "timezone": "Asia/Shanghai",
        "gender": "male",
        "time_known": True,
        "convention": {},
    }
    body.update(overrides)
    return body


def test_calculate_is_anonymous(client: TestClient) -> None:
    response = client.post(CALC, json=_payload())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["domain"] == "ziwei"
    assert len(body["chart_facts"]["palaces"]) == 12
    assert body["chart_facts"]["life_palace"]["text"] == "丁亥"
    assert body["convention"]["school"] == "sanhe_default_v1"
    assert body["convention"]["school_note"]
    assert "id" not in body


def test_unsupported_domain_returns_400(client: TestClient) -> None:
    response = client.post("/api/v1/charts/tarot/calculate", json=_payload())
    assert response.status_code == 400, response.text
    error = response.json()["error"]
    assert error["code"] == "DOMAIN_NOT_SUPPORTED"
    assert "ziwei" in error["message"]


def test_unknown_school_returns_422(client: TestClient) -> None:
    response = client.post(CALC, json=_payload(convention={"school": "zhongzhou_v1"}))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_bad_datetime_returns_422(client: TestClient) -> None:
    response = client.post(CALC, json=_payload(birth_datetime="1990-05-20T12:00:00+08:00"))
    assert response.status_code == 422


def test_save_requires_login(client: TestClient) -> None:
    response = client.post("/api/v1/charts/ziwei", json=_payload(title="紫微盘"))
    assert response.status_code == 401


def test_save_and_read_ziwei_chart(client: TestClient) -> None:
    headers = _headers(client)
    saved = client.post("/api/v1/charts/ziwei", json=_payload(title="紫微盘"), headers=headers)
    assert saved.status_code == 201, saved.text
    chart = saved.json()
    assert chart["domain"] == "ziwei"
    assert chart["title"] == "紫微盘"
    assert chart["chart_facts"]["five_element_bureau"]["name"] == "土五局"

    detail = client.get(f"/api/v1/charts/{chart['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["convention"]["school"] == "sanhe_default_v1"

    listing = client.get("/api/v1/charts", headers=headers).json()
    assert listing["total"] == 1
    # 列表摘要对非四柱术数回落到农历日期 + 五行局，不留空
    assert "土五局" in listing["items"][0]["pillars_text"]


def test_save_rejects_bad_meta(client: TestClient) -> None:
    headers = _headers(client)
    bad_days = client.post("/api/v1/charts/ziwei", json=_payload(delete_after_days=0), headers=headers)
    assert bad_days.status_code == 422
    bad_title = client.post("/api/v1/charts/ziwei", json=_payload(title="x" * 200), headers=headers)
    assert bad_title.status_code == 422


def test_save_rejects_client_supplied_facts(client: TestClient) -> None:
    headers = _headers(client)
    response = client.post(
        "/api/v1/charts/ziwei",
        json=_payload(chart_facts={"palaces": []}),
        headers=headers,
    )
    assert response.status_code == 422


def _report_payload(observations: list[dict[str, Any]], summary: str) -> dict[str, Any]:
    return {
        "summary": summary,
        "observations": observations,
        "traditional_interpretations": [],
        "practical_reflections": ["先核对出生时刻与农历日期，再判断解释是否成立。"],
        "uncertainties": ["不同流派对闰月与四化的处理不同。"],
        "citations": [],
        "safety_note": SAFETY_NOTE,
    }


def test_validator_accepts_correct_star_placement() -> None:
    chart = calculate(ZiweiInput(birth_datetime=datetime(1990, 5, 20, 12, 0), gender="male"))
    raw = _report_payload(
        [{"fact": "紫微坐命，命宫为丁亥。", "rule_ids": [], "citation_ids": []}],
        "命宫在亥，紫微与七杀同宫，五行局为土五局。",
    )
    result = validate(
        raw,
        triggered_rule_ids={item["rule_id"] for item in chart.triggered_rules},
        chunk_ids=set(),
        chart_facts=chart.chart_facts,
        domain="ziwei",
    )
    assert result.ok, result.to_dict()


def test_validator_blocks_wrong_star_placement() -> None:
    chart = calculate(ZiweiInput(birth_datetime=datetime(1990, 5, 20, 12, 0), gender="male"))
    raw = _report_payload(
        [{"fact": "紫微坐在迁移宫。", "rule_ids": [], "citation_ids": []}],
        "命宫在亥，紫微在迁移宫，天府坐命。",
    )
    result = validate(
        raw,
        triggered_rule_ids={item["rule_id"] for item in chart.triggered_rules},
        chunk_ids=set(),
        chart_facts=chart.chart_facts,
        domain="ziwei",
    )
    assert result.ok is False
    assert "fact_mismatch" in result.fatal_codes
