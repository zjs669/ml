"""六爻接口层测试：通用计算/保存入口、列表摘要、校验链分派、占问原文的存储策略。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi.testclient import TestClient

from app.domains.liuyao.engine import calculate
from app.domains.liuyao.schemas import LiuyaoInput
from app.domains.llm.mock import SAFETY_NOTE
from app.domains.llm.validator import validate

PASSWORD = "Passw0rd123"
CALC = "/api/v1/charts/liuyao/calculate"
SAVE = "/api/v1/charts/liuyao"


def _headers(client: TestClient) -> dict[str, str]:
    email = f"ly_{uuid.uuid4().hex[:10]}@example.com"
    response = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _payload(**overrides: Any) -> dict[str, Any]:
    body = {
        "method": "manual",
        "cast_datetime": "2026-01-01T12:00:00",
        "timezone": "Asia/Shanghai",
        "lines": [7, 7, 7, 7, 7, 7],
        "convention": {},
    }
    body.update(overrides)
    return body


def _chart(lines: list[int] | None = None):
    return calculate(
        LiuyaoInput(
            method="manual",
            cast_datetime=datetime(2026, 1, 1, 12, 0),
            lines=lines or [7, 7, 7, 7, 7, 7],
        )
    )


def test_calculate_is_anonymous(client: TestClient) -> None:
    response = client.post(CALC, json=_payload())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["domain"] == "liuyao"
    assert body["chart_facts"]["original"]["name"] == "乾为天"
    assert body["chart_facts"]["original"]["palace"] == "乾"
    assert body["convention"]["school"] == "jingfang_najia_v1"
    assert body["convention"]["school_note"]
    assert body["chart_facts"]["question"] is None
    assert "id" not in body


def test_calculate_keeps_question_when_requested(client: TestClient) -> None:
    response = client.post(CALC, json=_payload(question="这次合作能否推进"))
    assert response.status_code == 200
    facts = response.json()["chart_facts"]
    assert facts["question"] == "这次合作能否推进"
    assert facts["question_stored"] is True


def test_calculate_drops_question_when_asked(client: TestClient) -> None:
    response = client.post(CALC, json=_payload(question="这次合作能否推进", store_question=False))
    assert response.status_code == 200
    facts = response.json()["chart_facts"]
    assert facts["question"] is None
    assert facts["question_stored"] is False
    assert "这次合作能否推进" not in response.text


def test_coins_method_via_api(client: TestClient) -> None:
    body = _payload(method="coins", seed=42)
    body.pop("lines")
    response = client.post(CALC, json=body)
    assert response.status_code == 200, response.text
    facts = response.json()["chart_facts"]
    assert facts["seed"] == 42
    assert facts["original"]["name"] == "山火贲"


def test_bad_lines_returns_invalid_request(client: TestClient) -> None:
    response = client.post(CALC, json=_payload(lines=[7, 7, 7]))
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "INVALID_REQUEST"
    assert error["details"]


def test_lines_not_allowed_for_coins(client: TestClient) -> None:
    response = client.post(CALC, json=_payload(method="coins"))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_unknown_school_returns_422(client: TestClient) -> None:
    response = client.post(CALC, json=_payload(convention={"school": "meihua_v1"}))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_tz_aware_datetime_returns_422(client: TestClient) -> None:
    response = client.post(CALC, json=_payload(cast_datetime="2026-01-01T12:00:00+08:00"))
    assert response.status_code == 422


def test_save_requires_login(client: TestClient) -> None:
    response = client.post(SAVE, json=_payload(title="六爻盘"))
    assert response.status_code == 401


def test_save_and_read_liuyao_chart(client: TestClient) -> None:
    headers = _headers(client)
    saved = client.post(SAVE, json=_payload(title="六爻盘"), headers=headers)
    assert saved.status_code == 201, saved.text
    chart = saved.json()
    assert chart["domain"] == "liuyao"
    assert chart["title"] == "六爻盘"
    assert chart["chart_facts"]["original"]["name"] == "乾为天"

    detail = client.get(f"/api/v1/charts/{chart['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["convention"]["school"] == "jingfang_najia_v1"

    listing = client.get("/api/v1/charts", headers=headers).json()
    assert listing["total"] == 1
    # 列表摘要对六爻回落到农历日期 + 本卦卦名，不留空
    assert "乾为天" in listing["items"][0]["pillars_text"]


def test_save_drops_question_when_asked(client: TestClient) -> None:
    headers = _headers(client)
    payload = _payload(question="是否该接手这个项目", store_question=False)
    saved = client.post(SAVE, json=payload, headers=headers)
    assert saved.status_code == 201, saved.text
    detail = client.get(f"/api/v1/charts/{saved.json()['id']}", headers=headers).json()
    assert detail["chart_facts"]["question"] is None
    assert "是否该接手这个项目" not in str(detail)


def test_save_rejects_bad_meta(client: TestClient) -> None:
    headers = _headers(client)
    bad_days = client.post(SAVE, json=_payload(delete_after_days=0), headers=headers)
    assert bad_days.status_code == 422
    bad_title = client.post(SAVE, json=_payload(title="x" * 200), headers=headers)
    assert bad_title.status_code == 422


def test_save_rejects_client_supplied_facts(client: TestClient) -> None:
    headers = _headers(client)
    response = client.post(
        SAVE, json=_payload(chart_facts={"original": {"name": "坤为地"}}), headers=headers
    )
    assert response.status_code == 422


def _report_payload(observations: list[dict[str, Any]], summary: str) -> dict[str, Any]:
    return {
        "summary": summary,
        "observations": observations,
        "traditional_interpretations": [],
        "practical_reflections": ["先核对起卦时刻与输入方式，再判断解释是否成立。"],
        "uncertainties": ["铜钱起卦为可复现模拟，不等同于实体铜钱。"],
        "citations": [],
        "safety_note": SAFETY_NOTE,
    }


def _validate(chart, raw: dict[str, Any]):
    return validate(
        raw,
        triggered_rule_ids={item["rule_id"] for item in chart.triggered_rules},
        chunk_ids=set(),
        chart_facts=chart.chart_facts,
        domain="liuyao",
    )


def test_validator_accepts_correct_hexagram_names() -> None:
    chart = _chart()
    raw = _report_payload(
        [{"fact": "本卦为乾为天，卦宫属乾宫，世爻在上爻。", "rule_ids": [], "citation_ids": []}],
        "六爻皆静，本卦乾为天，纳甲自甲子起。",
    )
    result = _validate(chart, raw)
    assert result.ok, result.to_dict()


def test_validator_blocks_hexagram_not_on_chart() -> None:
    chart = _chart()
    raw = _report_payload(
        [{"fact": "本卦天风姤，世爻在初爻。", "rule_ids": [], "citation_ids": []}],
        "盘面为天风姤。",
    )
    result = _validate(chart, raw)
    assert result.ok is False
    assert "fact_mismatch" in result.fatal_codes


def test_validator_blocks_wrong_palace_claim() -> None:
    chart = _chart()
    raw = _report_payload(
        [{"fact": "本卦属坤宫。", "rule_ids": [], "citation_ids": []}],
        "本卦乾为天，卦宫属坤宫。",
    )
    result = _validate(chart, raw)
    assert result.ok is False
    assert "fact_mismatch" in result.fatal_codes


def test_validator_does_not_flag_generic_trigram_words() -> None:
    """「乾坤」「上下卦」这类普通表述不是卦名断言，不得误判为事实错误。"""
    chart = _chart()
    raw = _report_payload(
        [{"fact": "上下卦同为乾，属八纯之列，乾坤之气相通。", "rule_ids": [], "citation_ids": []}],
        "本卦乾为天，六爻纯阳，取象天地之间的刚健之德。",
    )
    result = _validate(chart, raw)
    assert result.ok, result.to_dict()


def test_validator_accepts_changed_hexagram_on_moving_chart() -> None:
    chart = _chart([9, 7, 7, 7, 7, 9])
    raw = _report_payload(
        [{"fact": "本卦乾为天，初上两爻动，变卦泽风大过，互卦乾为天。", "rule_ids": [], "citation_ids": []}],
        "本卦乾为天变为泽风大过。",
    )
    result = _validate(chart, raw)
    assert result.ok, result.to_dict()
