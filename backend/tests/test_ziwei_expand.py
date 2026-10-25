"""紫微第二轮扩充：杂曜 / 长生十二神 / 博士十二神 / 飞星四化。

断言原则：能用口诀独立复算的就不抄引擎结果。
年支 1990 = 庚午，所以「午」年对应的三合、三会、四正关系都能手算：
- 三合 寅午戌 → 华盖戌、咸池卯
- 三会 巳午未 → 孤辰申、寡宿辰
- 四正 子午卯酉 → 破碎巳
- 红鸾 卯宫逆数至午 → 酉；天喜恒为对宫 → 卯
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.domains.calendar_core.jiazi import BRANCHES, STEMS
from app.domains.ziwei import constants as C
from app.domains.ziwei.engine import calculate
from app.domains.ziwei.schemas import ZiweiConvention, ZiweiInput

BASE = dict(birth_datetime=datetime(1990, 5, 20, 12, 0), timezone="Asia/Shanghai", gender="male")


def _calc(**extra):
    return calculate(ZiweiInput(**BASE, **extra), ZiweiConvention())


@pytest.fixture(scope="module")
def chart():
    return _calc()


def _palace_of(chart, star: str) -> dict:
    for palace in chart.chart_facts["palaces"]:
        if star in palace["stars"]:
            return palace
    raise AssertionError(f"{star} 不在盘上")


def test_minor_stars_all_present_and_unique(chart) -> None:
    seen = [star for palace in chart.chart_facts["palaces"] for star in palace["minor_stars"]]
    assert sorted(seen) == sorted(C.MINOR_STARS)
    assert len(seen) == len(set(seen)) == 16


def test_minor_stars_by_year_branch(chart) -> None:
    assert _palace_of(chart, "华盖")["branch"] == "戌"
    assert _palace_of(chart, "咸池")["branch"] == "卯"
    assert _palace_of(chart, "孤辰")["branch"] == "申"
    assert _palace_of(chart, "寡宿")["branch"] == "辰"
    assert _palace_of(chart, "破碎")["branch"] == "巳"
    assert _palace_of(chart, "红鸾")["branch"] == "酉"
    assert _palace_of(chart, "天喜")["branch"] == "卯"


def test_hongluan_tianxi_are_opposite() -> None:
    for month in range(1, 13):
        for day in (3, 11, 19):
            result = calculate(
                ZiweiInput(
                    birth_datetime=datetime(1990, month, day, 9, 0),
                    timezone="Asia/Shanghai",
                    gender="female",
                ),
                ZiweiConvention(),
            )
            hu = BRANCHES.index(_palace_of(result, "红鸾")["branch"])
            xi = BRANCHES.index(_palace_of(result, "天喜")["branch"])
            assert (hu + 6) % 12 == xi


def test_tianxing_tianyao_follow_birth_month() -> None:
    """酉宫起正月：正月同宫酉，二月天刑顺到戌、天姚逆到申。"""
    jan = calculate(
        ZiweiInput(birth_datetime=datetime(1990, 1, 27, 12, 0), timezone="Asia/Shanghai"),
        ZiweiConvention(),
    )
    assert _palace_of(jan, "天刑")["branch"] == "酉"
    assert _palace_of(jan, "天姚")["branch"] == "酉"

    feb = calculate(
        ZiweiInput(birth_datetime=datetime(1990, 2, 25, 12, 0), timezone="Asia/Shanghai"),
        ZiweiConvention(),
    )
    assert _palace_of(feb, "天刑")["branch"] == "戌"
    assert _palace_of(feb, "天姚")["branch"] == "申"


def test_life_cycle_starts_from_bureau(chart) -> None:
    facts = chart.chart_facts
    bureau = facts["five_element_bureau"]["number"]
    names = [palace["life_cycle"] for palace in facts["palaces"]]
    assert sorted(names) == sorted(C.CHANG_SHENG_ORDER)
    start_index = C.CHANG_SHENG_START[bureau]
    start_palace = next(p for p in facts["palaces"] if p["branch"] == BRANCHES[start_index])
    assert start_palace["life_cycle"] == "长生"


def test_bo_shi_starts_from_lucun(chart) -> None:
    names = [palace["bo_shi"] for palace in chart.chart_facts["palaces"]]
    assert sorted(names) == sorted(C.BO_SHI_ORDER)
    lucun = _palace_of(chart, "禄存")
    assert lucun["bo_shi"] == "博士"


def test_palace_transformations_are_consistent(chart) -> None:
    facts = chart.chart_facts
    rows = facts["palace_transformations"]
    assert len(rows) == 12 * 4
    stems = {palace["name"]: palace["heavenly_stem"] for palace in facts["palaces"]}
    for row in rows:
        assert row["stem"] == stems[row["from_palace"]]
        # 四化目标必须真的落在那颗星所在的宫，不能自相矛盾
        assert _palace_of(chart, row["star"])["name"] == row["to_palace"]


def test_dayun_transformation_uses_that_palace_stem() -> None:
    result = _calc(review_age=30)
    facts = result.chart_facts
    block = facts["dayun_transformation"]
    assert block["age"] == 30
    palace = next(p for p in facts["palaces"] if p["name"] == block["palace"])
    assert block["stem"] == palace["heavenly_stem"]
    assert {item["type"] for item in block["items"]} == {"禄", "权", "科", "忌"}


def test_liunian_transformation_ganzhi() -> None:
    result = _calc(review_year=2026)
    facts = result.chart_facts
    block = facts["liunian_transformation"]
    assert block["ganzhi"] == "丙午"
    # 流年命宫 = 流年地支所在宫；午宫是什么宫由本命盘决定，不假定为命宫
    expected = next(p["name"] for p in facts["palaces"] if p["branch"] == "午")
    assert block["palace"] == expected
    assert len(block["items"]) == 4


def test_optional_layers_absent_when_not_requested(chart) -> None:
    assert "dayun_transformation" not in chart.chart_facts
    assert "liunian_transformation" not in chart.chart_facts
    assert "review_age" not in chart.input_summary


def test_age_before_first_dayun_warns_instead_of_guessing() -> None:
    """起限岁数等于五行局数（最小 2），所以 0 岁一定在第一大限之前。"""
    result = _calc(review_age=0)
    assert "dayun_transformation" not in result.chart_facts
    assert any("超出十二个大限" in item for item in result.warnings)


def test_input_validation_rejects_absurd_age() -> None:
    with pytest.raises(Exception):
        ZiweiInput(**BASE, review_age=200)


def test_api_exposes_new_layers(client: TestClient) -> None:
    payload = {
        "birth_datetime": "1990-05-20T12:00:00",
        "timezone": "Asia/Shanghai",
        "gender": "male",
        "review_age": 30,
        "review_year": 2026,
        "convention": {},
    }
    response = client.post("/api/v1/charts/ziwei/calculate", json=payload)
    assert response.status_code == 200, response.text
    facts = response.json()["chart_facts"]
    assert len(facts["palaces"][0]["minor_stars"]) >= 0
    assert facts["dayun_transformation"]["stem"] in STEMS
    assert facts["liunian_transformation"]["ganzhi"] == "丙午"
    assert len(facts["palace_transformations"]) == 48
