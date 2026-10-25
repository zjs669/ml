"""紫微引擎测试。

分两层锁死：
1. `fixtures/ziwei_cases.json` 的 10 例（按古籍安星诀手推）逐项比对命宫、身宫、五行局、
   紫微落宫与十四主星分布——这是唯一能挡住「改一处公式悄悄算错」的护栏；
2. 不变量与口径：十二宫齐全、十四主星各一、四化四条、大限连续、流派与闰月/时辰的显式声明。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domains.calendar_core.lunar import LunarRangeError, lunar_to_solar, solar_to_lunar
from app.domains.ziwei import constants as C
from app.domains.ziwei.engine import _ziwei_index, calculate
from app.domains.ziwei.schemas import ZiweiConvention, ZiweiInput

FIXTURE = Path(__file__).parent / "fixtures" / "ziwei_cases.json"
CASES = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]


def _input(case: dict) -> ZiweiInput:
    payload = dict(case["input"])
    payload["birth_datetime"] = datetime.fromisoformat(payload["birth_datetime"])
    return ZiweiInput(**payload)


def _by_branch(facts: dict) -> dict[str, list[str]]:
    return {palace["branch"]: palace["main_stars"] for palace in facts["palaces"]}


@pytest.mark.parametrize("case", CASES, ids=[item["case_id"] for item in CASES])
def test_hand_derived_cases(case: dict) -> None:
    facts = calculate(_input(case)).chart_facts
    expect = case["expect"]

    assert facts["life_palace"]["branch"] == expect["life_palace_branch"], case["derivation"]
    assert facts["body_palace"]["branch"] == expect["body_palace_branch"], case["derivation"]
    assert facts["five_element_bureau"]["name"] == expect["bureau"], case["derivation"]
    assert facts["ziwei_star"]["branch"] == expect["ziwei_branch"], case["derivation"]

    placed = _by_branch(facts)
    for branch, stars in expect["main_stars"].items():
        assert sorted(placed[branch]) == sorted(stars), f"{branch} 宫主星不符：{case['derivation']}"
    # 期望里没列出的宫位必须没有主星，否则说明多安了星
    for branch, stars in placed.items():
        if branch not in expect["main_stars"]:
            assert stars == [], f"{branch} 宫不应有主星"


@pytest.mark.parametrize("case", CASES, ids=[item["case_id"] for item in CASES])
def test_invariants(case: dict) -> None:
    result = calculate(_input(case))
    facts = result.chart_facts
    palaces = facts["palaces"]

    assert [p["order"] for p in palaces] == list(range(12))
    assert [p["name"] for p in palaces] == list(C.PALACES)
    assert len({p["branch"] for p in palaces}) == 12
    assert sum(1 for p in palaces if p["is_body"]) == 1

    placed = [star for palace in palaces for star in palace["main_stars"]]
    assert sorted(placed) == sorted(C.MAIN_STARS)

    # 天府与紫微关于寅申轴对称：天府宫 = (TIANFU_MIRROR - 紫微宫) % 12
    ziwei_index = C.BRANCHES.index(facts["ziwei_star"]["branch"])
    tianfu_branch = next(p["branch"] for p in palaces if "天府" in p["main_stars"])
    assert C.BRANCHES.index(tianfu_branch) == (C.TIANFU_MIRROR - ziwei_index) % 12

    assert len(facts["transformations"]) == 4
    assert {item["type"] for item in facts["transformations"]} == {"禄", "权", "科", "忌"}

    assert len(facts["dayun"]) == 12
    ages = [item["start_age"] for item in facts["dayun"]]
    bureau = facts["five_element_bureau"]["number"]
    assert ages == [bureau + index * 10 for index in range(12)]

    assert result.domain == "ziwei"
    assert result.algorithm_version
    assert result.source_refs


ZIWEI_ANCHORS = [
    # 水二局：初一丑、初二寅、初三寅、初四卯
    (2, 1, "丑"),
    (2, 2, "寅"),
    (2, 3, "寅"),
    (2, 4, "卯"),
    # 木三局：初一辰、初二丑、初三寅、初四巳、初五寅、初七午、初十未
    (3, 1, "辰"),
    (3, 2, "丑"),
    (3, 3, "寅"),
    (3, 4, "巳"),
    (3, 5, "寅"),
    (3, 7, "午"),
    (3, 10, "未"),
    # 金四局初一亥、土五局初一午、火六局初一酉
    (4, 1, "亥"),
    (5, 1, "午"),
    (6, 1, "酉"),
]


@pytest.mark.parametrize(("bureau", "day", "branch"), ZIWEI_ANCHORS)
def test_ziwei_index_anchors(bureau: int, day: int, branch: str) -> None:
    """安紫微星起例：补数奇偶决定进退，进退方向反了这几例会先挂。"""
    assert C.BRANCHES[_ziwei_index(bureau, day)] == branch


def test_lunar_input_matches_gregorian() -> None:
    """农历入参与等价公历入参必须得到同一张盘。"""
    gregorian = calculate(
        ZiweiInput(birth_datetime=datetime(1990, 5, 20, 12, 0), gender="male")
    ).chart_facts
    lunar = calculate(
        ZiweiInput(
            calendar="lunar",
            birth_datetime=datetime(1990, 4, 26, 12, 0),
            gender="male",
        )
    ).chart_facts
    assert lunar["lunar_date"]["text"] == gregorian["lunar_date"]["text"]
    assert lunar["life_palace"] == gregorian["life_palace"]
    assert lunar["palaces"] == gregorian["palaces"]


def test_leap_month_is_flagged_and_counted_as_current_month() -> None:
    result = calculate(
        ZiweiInput(
            calendar="lunar",
            birth_datetime=datetime(2020, 4, 1, 10, 0),
            is_leap_month=True,
            gender="female",
        )
    )
    facts = result.chart_facts
    assert facts["lunar_date"]["is_leap_month"] is True
    assert lunar_to_solar(2020, -4, 1) == datetime(2020, 5, 23, 0, 0)
    assert any("闰" in item for item in result.warnings)

    # 非闰月的「四月」必须落在正常四月，不能被静默当成闰月
    normal = calculate(
        ZiweiInput(
            calendar="lunar",
            birth_datetime=datetime(2020, 4, 1, 10, 0),
            gender="female",
        )
    ).chart_facts
    assert normal["lunar_date"]["is_leap_month"] is False
    assert normal["lunar_date"]["text"] != facts["lunar_date"]["text"]


def test_unknown_leap_month_raises() -> None:
    with pytest.raises(LunarRangeError):
        lunar_to_solar(2020, -5, 1)


def test_solar_to_lunar_matches_reference() -> None:
    lunar = solar_to_lunar(datetime(1990, 5, 20, 12, 0))
    assert lunar.text == "1990年四月廿六"
    assert lunar.year_ganzhi == "庚午"
    assert lunar.is_leap_month is False


def test_unknown_hour_uses_noon_and_warns() -> None:
    result = calculate(
        ZiweiInput(birth_datetime=datetime(1990, 5, 20, 3, 0), time_known=False)
    )
    assert result.chart_facts["hour_branch"] == "午"
    assert result.chart_facts["hour_known"] is False
    assert any("时辰未知" in item for item in result.warnings)


def test_late_zi_hour_keeps_same_lunar_day_and_warns() -> None:
    result = calculate(ZiweiInput(birth_datetime=datetime(1999, 12, 31, 23, 30)))
    facts = result.chart_facts
    assert facts["hour_branch"] == "子"
    assert facts["lunar_date"]["day"] == 24
    assert any("23:00" in item for item in result.warnings)


def test_other_school_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ZiweiConvention(school="zhongzhou_v1")


def test_leap_flag_only_for_lunar_input() -> None:
    with pytest.raises(ValidationError):
        ZiweiInput(
            calendar="gregorian",
            birth_datetime=datetime(1990, 5, 20, 12, 0),
            is_leap_month=True,
        )


def test_gender_unknown_warns_about_dayun_direction() -> None:
    result = calculate(ZiweiInput(birth_datetime=datetime(1990, 5, 20, 12, 0)))
    assert result.chart_facts["dayun_forward"] is True  # 庚为阳干，占位取顺行
    assert any("性别未知" in item for item in result.warnings)


def test_yang_male_and_yin_female_run_forward() -> None:
    # 庚午年（阳）：男顺行、女逆行
    male = calculate(
        ZiweiInput(birth_datetime=datetime(1990, 5, 20, 12, 0), gender="male")
    ).chart_facts
    female = calculate(
        ZiweiInput(birth_datetime=datetime(1990, 5, 20, 12, 0), gender="female")
    ).chart_facts
    assert male["dayun_forward"] is True
    assert female["dayun_forward"] is False
    # 顺行第二限走父母宫，逆行第二限走兄弟宫
    assert male["dayun"][1]["palace"] == "父母"
    assert female["dayun"][1]["palace"] == "兄弟"


def test_empty_life_palace_gets_structural_marker() -> None:
    result = calculate(
        ZiweiInput(birth_datetime=datetime(1976, 11, 7, 6, 0), gender="male")
    )
    ids = [item["rule_id"] for item in result.triggered_rules]
    assert "ziwei.palace.life_empty" in ids
    # 紫微不在命宫（在巳），因此不应出现紫微坐命
    assert "ziwei.star.ziwei_in_life" not in ids


def test_ziwei_in_life_marker() -> None:
    result = calculate(
        ZiweiInput(birth_datetime=datetime(1990, 5, 20, 12, 0), gender="male")
    )
    ids = [item["rule_id"] for item in result.triggered_rules]
    assert "ziwei.star.ziwei_in_life" in ids
    assert "ziwei.palace.life_body_same" in ids
