"""八字流年：只在显式给起始年时计算，且必须能被独立复算。

流年是「展示层窗口」，不是命盘本身。因此：
- 不传 `liunian_start_year` 就不出 `liunian`（同一输入永远同一结果）；
- 年干支用 (year-4)%60 复算，虚岁用公历年差 +1，所属大运按大运起止年归属。
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.domains.bazi.engine import calculate
from app.domains.bazi.schemas import BaziInput, Convention
from app.domains.calendar_core.jiazi import BRANCHES, STEMS

BASE = dict(birth_datetime=datetime(1990, 5, 20, 12, 0), timezone="Asia/Shanghai", gender="male")


def _calc(**extra):
    return calculate(BaziInput(**BASE, **extra), Convention())


@pytest.fixture(scope="module")
def with_liunian():
    return _calc(liunian_start_year=2024, liunian_years=10)


def test_absent_when_not_requested() -> None:
    result = _calc()
    assert "liunian" not in result.chart_facts


def test_ten_years_by_default() -> None:
    result = _calc(liunian_start_year=2020)
    rows = result.chart_facts["liunian"]["list"]
    assert len(rows) == 10
    assert [row["year"] for row in rows] == list(range(2020, 2030))


def test_year_pillar_matches_known_anchors(with_liunian) -> None:
    rows = {row["year"]: row for row in with_liunian.chart_facts["liunian"]["list"]}
    # 1984 = 甲子，2024 = 甲辰，2026 = 丙午；三点足以锁死 60 甲子的相位
    assert rows[2024]["pillar"] == "甲辰"
    assert rows[2026]["pillar"] == "丙午"
    index = (1984 - 4) % 60
    assert STEMS[index % 10] + BRANCHES[index % 12] == "甲子"


def test_virtual_age_is_year_delta_plus_one(with_liunian) -> None:
    rows = with_liunian.chart_facts["liunian"]["list"]
    assert rows[0]["virtual_age"] == 2024 - 1990 + 1
    assert rows[-1]["virtual_age"] == rows[0]["virtual_age"] + 9


def test_dayun_membership_follows_start_year(with_liunian) -> None:
    facts = with_liunian.chart_facts
    dayun = {item["index"]: item for item in facts["dayun"]["list"]}
    for row in facts["liunian"]["list"]:
        if row["dayun_index"] is None:
            continue
        item = dayun[row["dayun_index"]]
        assert item["start_year"] <= row["year"] <= item["start_year"] + 9
        assert row["dayun_pillar"] == item["pillar"]


def test_lichun_boundary_is_reported(with_liunian) -> None:
    for row in with_liunian.chart_facts["liunian"]["list"]:
        # 立春恒在 2 月 3–5 日，格式固定到分钟
        assert row["lichun_local"].startswith(f"{row['year']}-02-0")


def test_boundary_follows_year_boundary_convention() -> None:
    day_mode = calculate(
        BaziInput(**BASE, liunian_start_year=2024, liunian_years=2),
        Convention(year_boundary="lichun_day"),
    )
    rows = day_mode.chart_facts["liunian"]["list"]
    assert all(row["lichun_local"].endswith("00:00") for row in rows)
    assert day_mode.chart_facts["liunian"]["boundary_rule"] == "lichun_day"


def test_input_validation() -> None:
    with pytest.raises(Exception):
        BaziInput(**BASE, liunian_start_year=2024, liunian_years=0)
    with pytest.raises(Exception):
        BaziInput(**BASE, liunian_start_year=1700)


def test_api_exposes_liunian(client: TestClient) -> None:
    payload = {
        "birth_datetime": "1990-05-20T12:00:00",
        "timezone": "Asia/Shanghai",
        "gender": "male",
        "liunian_start_year": 2024,
        "liunian_years": 3,
        "convention": {},
    }
    response = client.post("/api/v1/charts/bazi/calculate", json=payload)
    assert response.status_code == 200, response.text
    rows = response.json()["chart_facts"]["liunian"]["list"]
    assert [row["pillar"] for row in rows] == ["甲辰", "乙巳", "丙午"]
    assert rows[0]["ten_god"]
