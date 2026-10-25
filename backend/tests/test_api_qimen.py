"""奇门接口层测试：通用计算/保存入口、口径回显、校验链分派、元信息暴露。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi.testclient import TestClient

from app.domains.llm.base import LLMRequest
from app.domains.llm.mock import SAFETY_NOTE, MockProvider
from app.domains.llm.validator import validate
from app.domains.qimen.engine import calculate
from app.domains.qimen.schemas import QimenInput

PASSWORD = "Passw0rd123"
CALC = "/api/v1/charts/qimen/calculate"
SAVE = "/api/v1/charts/qimen"


def _headers(client: TestClient) -> dict[str, str]:
    email = f"qm_{uuid.uuid4().hex[:10]}@example.com"
    response = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _payload(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "cast_datetime": "2026-01-01T12:00:00",
        "timezone": "Asia/Shanghai",
        "convention": {},
    }
    body.update(overrides)
    return body


def _chart(moment: datetime = datetime(2026, 1, 1, 12, 0)):
    return calculate(QimenInput(cast_datetime=moment, timezone="Asia/Shanghai"))


def test_calculate_is_anonymous(client: TestClient) -> None:
    response = client.post(CALC, json=_payload())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["domain"] == "qimen"
    assert body["algorithm_version"]
    facts = body["chart_facts"]
    assert [facts["pillars"][key]["text"] for key in ("year", "month", "day", "hour")] == [
        "乙巳",
        "戊子",
        "乙亥",
        "壬午",
    ]
    assert facts["dun"]["text"] == "阳遁四局"
    assert facts["zhifu"]["star"] == "天禽"
    assert facts["zhishi"]["door"] == "死门"
    assert len(facts["palaces"]) == 9
    # 口径回显 + 单一口径声明
    assert body["convention"]["school"] == "chaibu_zhuanpan_v1"
    assert body["convention"]["school_note"]
    assert "id" not in body


def test_calculate_returns_structural_markers_only(client: TestClient) -> None:
    body = client.post(CALC, json=_payload()).json()
    rule_ids = {item["rule_id"] for item in body["triggered_rules"]}
    assert {"qimen.ju.dun", "qimen.zhifu.star", "qimen.zhishi.door"} <= rule_ids
    assert {item["system"] for item in body["triggered_rules"]} == {"qimen"}
    # 红线：只陈述结构，不给吉凶
    joined = " ".join(item["note"] for item in body["triggered_rules"])
    for banned in ("吉", "凶", "宜", "忌"):
        assert banned not in joined


def test_unknown_domain_returns_400(client: TestClient) -> None:
    response = client.post("/api/v1/charts/liuyao2/calculate", json=_payload())
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "DOMAIN_NOT_SUPPORTED"
    assert "qimen" in error["message"]


def test_tz_aware_datetime_returns_422(client: TestClient) -> None:
    response = client.post(CALC, json=_payload(cast_datetime="2026-01-01T12:00:00+08:00"))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_unknown_school_returns_422(client: TestClient) -> None:
    response = client.post(CALC, json=_payload(convention={"school": "feipan_v1"}))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_unknown_dun_basis_returns_422(client: TestClient) -> None:
    response = client.post(CALC, json=_payload(convention={"dun_basis": "month"}))
    assert response.status_code == 422


def test_out_of_range_year_returns_422(client: TestClient) -> None:
    response = client.post(CALC, json=_payload(cast_datetime="1799-12-31T23:00:00"))
    assert response.status_code == 422


def test_manual_ju_is_rejected(client: TestClient) -> None:
    """局数由节气与符头推出，不接受手工指定——否则同一盘无法复核。"""
    response = client.post(CALC, json=_payload(ju=1))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_save_requires_login(client: TestClient) -> None:
    response = client.post(SAVE, json=_payload(title="奇门盘"))
    assert response.status_code == 401


def test_save_and_read_qimen_chart(client: TestClient) -> None:
    headers = _headers(client)
    saved = client.post(SAVE, json=_payload(title="奇门盘"), headers=headers)
    assert saved.status_code == 201, saved.text
    chart = saved.json()
    assert chart["domain"] == "qimen"
    assert chart["title"] == "奇门盘"
    assert chart["chart_facts"]["dun"]["text"] == "阳遁四局"

    detail = client.get(f"/api/v1/charts/{chart['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["convention"]["school"] == "chaibu_zhuanpan_v1"

    listing = client.get("/api/v1/charts", headers=headers).json()
    assert listing["total"] == 1
    item = listing["items"][0]
    assert item["domain"] == "qimen"
    # 列表摘要走四柱文本，不留空
    assert item["pillars_text"] == "乙巳 戊子 乙亥 壬午"


def test_save_dedupes_client_facts(client: TestClient) -> None:
    """客户端提交的 chart_facts 一律不采信：保存时服务端重算。"""
    headers = _headers(client)
    response = client.post(
        SAVE, json=_payload(title="奇门盘", chart_facts={"dun": {"text": "阳遁一局"}}), headers=headers
    )
    assert response.status_code == 422


def test_meta_reports_qimen_supported(client: TestClient) -> None:
    body = client.get("/api/v1/meta/about").json()
    assert "qimen" in body["supported_domains"]
    assert body["planned_domains"] == []
    assert any(skill["skill_key"] == "qimen.chart.v1" for skill in body["skills"])


def _report_payload(observations: list[dict[str, Any]], summary: str) -> dict[str, Any]:
    return {
        "summary": summary,
        "observations": observations,
        "traditional_interpretations": [],
        "practical_reflections": ["先核对起局时刻与节气来源，再判断解释是否成立。"],
        "uncertainties": ["奇门各派在置闰与拆补、转盘与飞盘上做法不同。"],
        "citations": [],
        "safety_note": SAFETY_NOTE,
    }


def _validate(chart, raw: dict[str, Any], chunk_ids: set[int] | None = None):
    return validate(
        raw,
        triggered_rule_ids={item["rule_id"] for item in chart.triggered_rules},
        chunk_ids=chunk_ids or set(),
        chart_facts=chart.chart_facts,
        domain="qimen",
    )


def test_validator_accepts_correct_palace_claims() -> None:
    chart = _chart()
    # 本盘：天禽随时干落艮八宫、死门落艮八宫（门伏吟）
    raw = _report_payload(
        [{"fact": "值符天禽落艮八宫，值使死门亦落艮八宫，属门伏吟。", "rule_ids": [], "citation_ids": []}],
        "本盘为阳遁四局（下元），四柱乙巳 戊子 乙亥 壬午。",
    )
    result = _validate(chart, raw)
    assert result.ok, result.to_dict()


def test_validator_blocks_wrong_palace_claim() -> None:
    chart = _chart()
    raw = _report_payload(
        [{"fact": "值符天禽落坎一宫。", "rule_ids": [], "citation_ids": []}],
        "本盘为阳遁四局。",
    )
    result = _validate(chart, raw)
    assert result.ok is False
    assert "fact_mismatch" in result.fatal_codes


def test_validator_blocks_fabricated_pillar() -> None:
    chart = _chart()
    raw = _report_payload(
        [{"fact": "四柱为甲子 乙丑 丙寅 丁卯。", "rule_ids": [], "citation_ids": []}],
        "本盘为阳遁四局。",
    )
    result = _validate(chart, raw)
    assert result.ok is False
    assert "fact_mismatch" in result.fatal_codes


def test_validator_accepts_xun_head_and_fu_tou_pillars() -> None:
    """旬首与符头是盘面事实，正文出现它们不算编造干支。"""
    chart = _chart()
    raw = _report_payload(
        [{"fact": "时柱壬午属甲戌旬，符头为甲戌，旬空在申酉。", "rule_ids": [], "citation_ids": []}],
        "本盘为阳遁四局（下元），符头甲戌，值符天禽。",
    )
    result = _validate(chart, raw)
    assert result.ok, result.to_dict()


def test_validator_ignores_native_position_description() -> None:
    """「天蓬本位在坎一宫」属于本宫描述而不是落宫断言，不得误判。"""
    chart = _chart()
    raw = _report_payload(
        [{"fact": "天蓬本位在坎一宫，休门本位亦在坎一宫。", "rule_ids": [], "citation_ids": []}],
        "本盘为阳遁四局。",
    )
    result = _validate(chart, raw)
    assert result.ok, result.to_dict()


QIMEN_CHUNKS: list[dict[str, Any]] = [
    {
        "chunk_id": 31,
        "topic": "值符值使",
        "title": "值符随时干而转",
        "citation_label": "《奇门遁甲统宗》",
        "location": "卷三·值符值使",
        "snippet": "值符为九星之首，随时干所在之宫而转；值使门按旬内步数顺逆而行。",
        "license_status": "public_domain_paraphrase",
    }
]


def test_mock_report_passes_validation() -> None:
    """演示模型的奇门报告必须能过自己那条校验链，否则真实模型一律会被误杀。"""
    chart = _chart()
    request = LLMRequest(
        task="qimen.chart",
        system_prompt="",
        user_prompt="",
        context={
            "domain": "qimen",
            "chart_facts": chart.chart_facts,
            "triggered_rules": chart.triggered_rules,
            "chunks": QIMEN_CHUNKS,
            "warnings": chart.warnings,
            "depth": "brief",
        },
    )
    payload = MockProvider().generate_json(request).payload
    result = _validate(chart, payload, {chunk["chunk_id"] for chunk in QIMEN_CHUNKS})
    assert result.ok, result.to_dict()
    assert all(item["citation_ids"] for item in payload["traditional_interpretations"])
    assert any("拆补" in item for item in payload["uncertainties"])
