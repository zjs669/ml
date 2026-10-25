"""四柱每柱附项与神煞：纳音、旬空、地势、自坐、神煞。

锚点用 2006-07-29 17:38 男命：丙戌 / 乙未 / 己未 / 癸酉。
纳音与旬空可直接查表复算；地势/自坐按「土寄水、阳顺阴逆」复算；
神煞只断言「落在哪一柱」，不评价好坏。
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.domains.bazi.engine import calculate
from app.domains.bazi.schemas import BaziInput, Convention

BIRTH = dict(birth_datetime=datetime(2006, 7, 29, 17, 38), timezone="Asia/Shanghai", gender="male")


def _calc(**kwargs):
    return calculate(BaziInput(**BIRTH), Convention(**kwargs))


@pytest.fixture(scope="module")
def chart():
    return _calc()


def test_nayin_and_xunkong(chart) -> None:
    pillars = chart.chart_facts["pillars"]
    assert [pillars[k]["text"] for k in ("year", "month", "day", "hour")] == [
        "丙戌", "乙未", "己未", "癸酉"
    ]
    assert [pillars[k]["nayin"] for k in ("year", "month", "day", "hour")] == [
        "屋上土", "沙中金", "天上火", "剑锋金"
    ]
    assert pillars["year"]["xun_kong"] == ["午", "未"]
    assert pillars["month"]["xun_kong"] == ["辰", "巳"]
    assert pillars["day"]["xun_kong"] == ["子", "丑"]
    assert pillars["hour"]["xun_kong"] == ["戌", "亥"]


def test_dishi_and_zizuo_use_tu_jishui(chart) -> None:
    pillars = chart.chart_facts["pillars"]
    # 己土：长生在申，阴干逆排 → 未=沐浴、酉=养
    assert pillars["day"]["dishi"] == "沐浴"
    assert pillars["hour"]["dishi"] == "养"
    # 自坐：丙戌=墓（阳火顺排）、癸酉=养（阴水逆排）
    assert pillars["year"]["zizuo"] == "墓"
    assert pillars["hour"]["zizuo"] == "养"


def test_default_shensha_are_ten_known_items(chart) -> None:
    facts = chart.chart_facts["shensha"]
    names = {item["name"] for item in facts["items"]}
    assert {
        "太极贵人", "文昌贵人", "福星贵人", "华盖", "寡宿",
        "六厄", "天德合", "月德合", "六秀日", "金神",
    } <= names
    assert facts["variant"] == "common"
    assert "勾绞" not in names and "童子" not in names
    # 只报位置，不出现吉凶字段
    for item in facts["items"]:
        assert set(item) >= {"name", "positions", "basis", "source_ref"}
        assert "good" not in item and "bad" not in item


def test_extended_variant_is_opt_in_and_warned() -> None:
    result = _calc(shensha_variant="extended")
    names = {item["name"] for item in result.chart_facts["shensha"]["items"]}
    assert "勾绞" in names
    assert any("extended" in warning for warning in result.warnings)


def test_shensha_by_pillar_matches_items(chart) -> None:
    facts = chart.chart_facts["shensha"]
    for item in facts["items"]:
        for position in item["positions"]:
            assert item["name"] in facts["by_pillar"][position]


def test_api_exposes_pillar_extra_fields(client: TestClient) -> None:
    payload = {
        "birth_datetime": "2006-07-29T17:38:00",
        "timezone": "Asia/Shanghai",
        "gender": "male",
        "convention": {},
    }
    response = client.post("/api/v1/charts/bazi/calculate", json=payload)
    assert response.status_code == 200, response.text
    facts = response.json()["chart_facts"]
    assert facts["pillars"]["year"]["nayin"] == "屋上土"
    assert facts["pillars"]["day"]["zizuo"] == "沐浴"
    assert facts["shensha"]["by_pillar"]["day"]
