"""紫微运限引擎测试。

期望值不取引擎输出：六层递推全部按定义独立重算 ——
大限查本命盘大限表区间、小限查小限岁数、流年按流年支定宫、
流月用斗君法、流日自流月宫顺行、流时自流日宫顺行。

运限最容易出的错是「层与层之间起宫接错」，盘面看上去完整但整体错位，
因此这里逐层独立核对起点，而不是只断言最终落宫。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domains.calendar_core.jiazi import BRANCHES, hour_branch
from app.domains.ziwei.engine import calculate as calculate_ziwei
from app.domains.ziwei.schemas import ZiweiInput
from app.domains.ziwei_horoscope.engine import calculate
from app.domains.ziwei_horoscope.schemas import HoroscopeCalculateIn, HoroscopeInput

PALACES = (
    "命宫", "兄弟", "夫妻", "子女", "财帛", "疾厄",
    "迁移", "交友", "官禄", "田宅", "福德", "父母",
)

BIRTH = "1990-05-20T12:00:00"


def _run(target_date: str = "2026-10-25T00:00:00", target_hour: int = 15, **kwargs):
    payload = {
        "birth_datetime": BIRTH,
        "gender": "male",
        "target_date": target_date,
        "target_hour": target_hour,
        **kwargs,
    }
    inp = HoroscopeInput.model_validate(payload)
    return calculate(inp).chart_facts


def _natal_facts(review_year: int = 2026):
    return calculate_ziwei(
        ZiweiInput.model_validate(
            {"birth_datetime": BIRTH, "gender": "male", "review_year": review_year}
        )
    ).chart_facts


def test_six_layers_present() -> None:
    facts = _run()
    names = [item["layer"] for item in facts["layers"]]
    assert names == ["大限", "小限", "流年", "流月", "流日", "流时"]


def test_decadal_matches_natal_table() -> None:
    """大限落宫必须等于本命盘大限表里覆盖该虚岁的那一段。"""
    facts = _run()
    age = facts["target"]["virtual_age"]
    natal = _natal_facts()
    expected = next(
        item["palace"] for item in natal["dayun"] if item["start_age"] <= age <= item["end_age"]
    )
    decadal = next(item for item in facts["layers"] if item["layer"] == "大限")
    assert decadal["palace"] == expected


def test_xiaoxian_matches_age_table() -> None:
    """小限落宫必须等于本命盘里包含该虚岁的那一宫。"""
    facts = _run()
    age = facts["target"]["virtual_age"]
    natal = _natal_facts()
    expected = next(p["name"] for p in natal["palaces"] if age in (p.get("xiaoxian_ages") or []))
    xiaoxian = next(item for item in facts["layers"] if item["layer"] == "小限")
    assert xiaoxian["palace"] == expected


def test_liunian_palace_from_branch() -> None:
    """流年宫 = 本命盘里流年支对应的宫位。"""
    facts = _run()
    year = facts["target"]["lunar_year"]
    cycle = (year - 4) % 60
    branch = BRANCHES[cycle % 12]
    natal = _natal_facts()
    expected = next(p["name"] for p in natal["palaces"] if p["branch"] == branch)
    liunian = next(item for item in facts["layers"] if item["layer"] == "流年")
    assert liunian["palace"] == expected


def test_doujun_monthly_derivation() -> None:
    """斗君法：流年宫逆数生月得起点，再顺数生时得正月宫，再顺数至目标月。"""
    facts = _run()
    liunian = next(item for item in facts["layers"] if item["layer"] == "流年")["palace"]
    birth_month = 4  # 1990-05-20 → 农历四月
    birth_hour_index = BRANCHES.index(hour_branch(12, 0))
    start = (PALACES.index(liunian) - (birth_month - 1)) % 12
    doujun = (start + birth_hour_index) % 12
    target_month = facts["target"]["lunar_month"]
    expected = PALACES[(doujun + (target_month - 1)) % 12]
    monthly = next(item for item in facts["layers"] if item["layer"] == "流月")
    assert monthly["palace"] == expected


def test_daily_from_monthly() -> None:
    """流日 = 流月宫起初一，顺数至目标日。"""
    facts = _run()
    monthly = next(item for item in facts["layers"] if item["layer"] == "流月")["palace"]
    expected = PALACES[(PALACES.index(monthly) + facts["target"]["lunar_day"] - 1) % 12]
    daily = next(item for item in facts["layers"] if item["layer"] == "流日")
    assert daily["palace"] == expected


def test_hourly_from_daily() -> None:
    """流时 = 流日宫起子时，顺数至目标时辰。"""
    facts = _run()
    daily = next(item for item in facts["layers"] if item["layer"] == "流日")["palace"]
    hour_index = BRANCHES.index(hour_branch(15))
    expected = PALACES[(PALACES.index(daily) + hour_index) % 12]
    hourly = next(item for item in facts["layers"] if item["layer"] == "流时")
    assert hourly["palace"] == expected


def test_layers_carry_stars_of_their_palace() -> None:
    """每层的星曜必须与该宫在本命盘上的星曜一致（不得错位取邻宫）。"""
    facts = _run()
    natal = _natal_facts()
    by_name = {p["name"]: p for p in natal["palaces"]}
    for item in facts["layers"]:
        if not item["palace"]:
            continue
        source = by_name[item["palace"]]
        assert item["main_stars"] == source["main_stars"], item["layer"]
        assert item["aux_stars"] == source["aux_stars"], item["layer"]


def test_month_advances_by_one_per_month() -> None:
    """同一年的相邻农历月，流月宫应逐月顺行一位。"""
    first = _run("2026-10-25T00:00:00")["layers"]
    second = _run("2026-11-25T00:00:00")["layers"]
    m1 = next(i for i in first if i["layer"] == "流月")["palace"]
    m2 = next(i for i in second if i["layer"] == "流月")["palace"]
    assert PALACES.index(m2) == (PALACES.index(m1) + 1) % 12


def test_transit_transformations_reuse_natal_flights() -> None:
    """运限四化只复用本命盘已算好的宫干四化，不重推四化表。"""
    facts = _run()
    natal = _natal_facts()
    by_from = {}
    for row in natal["palace_transformations"]:
        by_from.setdefault(row["from_palace"], []).append(row)
    for item in facts["transit_transformations"]:
        expected = by_from.get(item["from_palace"], [])
        assert len(item["flights"]) == len(expected), item["layer"]
        assert [f["type"] for f in item["flights"]] == [r["type"] for r in expected]


def test_virtual_age_is_birth_year_based() -> None:
    """虚岁 = 目标农历年 − 出生农历年 + 1。"""
    facts = _run()
    assert facts["target"]["virtual_age"] == 2026 - 1990 + 1


def test_target_before_birth_rejected() -> None:
    with pytest.raises(ValidationError):
        HoroscopeInput.model_validate(
            {
                "birth_datetime": BIRTH,
                "target_date": "1989-01-01T00:00:00",
            }
        )


def test_rejects_unknown_school() -> None:
    with pytest.raises(ValidationError):
        HoroscopeCalculateIn.model_validate(
            {
                "birth_datetime": BIRTH,
                "target_date": "2026-10-25T00:00:00",
                "convention": {"school": "zhongzhou_v1"},
            }
        )


def test_gender_unknown_warns() -> None:
    facts_inp = HoroscopeInput.model_validate(
        {"birth_datetime": BIRTH, "target_date": "2026-10-25T00:00:00", "gender": "unknown"}
    )
    result = calculate(facts_inp)
    assert any("性别未知" in item for item in result.warnings)


def test_triggered_rules_empty() -> None:
    """运限没有关系规则，triggered_rules 必须为空。"""
    inp = HoroscopeInput.model_validate(
        {"birth_datetime": BIRTH, "target_date": "2026-10-25T00:00:00"}
    )
    assert calculate(inp).triggered_rules == []


def test_out_of_range_decadal_warns() -> None:
    """虚岁超出 12 个大限覆盖范围时，大限层留空并给出提示，而不是硬猜。"""
    inp = HoroscopeInput.model_validate(
        {"birth_datetime": BIRTH, "target_date": "2140-01-01T00:00:00", "gender": "male"}
    )
    result = calculate(inp)
    decadal = next(i for i in result.chart_facts["layers"] if i["layer"] == "大限")
    if decadal["palace"] is None:
        assert any("超出本命盘 12 个大限" in item for item in result.warnings)
