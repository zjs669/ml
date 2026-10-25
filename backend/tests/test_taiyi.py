"""太乙九星引擎测试。

期望值不取引擎输出：
- 年月日三层用 `lunar-python` 的九星表**独立读取**核对（这是数据源，不是引擎）；
- 时层按九星入中宫规则**独立重算**（阳起 7 / 阴起 3，子午卯酉与辰戌丑未另有起数）；
- 九星索引与太乙名的对应关系用独立常量表核对。

时层最容易出错：阳遁顺推、阴遁逆推、起数随日支变化，写反方向盘面依然完整。
因此这里逐项核对起数与方向，而不是只断言最终编号。
"""

from __future__ import annotations

import pytest
from lunar_python import Solar
from pydantic import ValidationError

from app.domains.calendar_core.jiazi import BRANCHES, hour_branch
from app.domains.taiyi.engine import TAIYI_STAR_NAMES, _hour_star_index, calculate
from app.domains.taiyi.schemas import TaiyiCalculateIn, TaiyiInput

ANCHOR = "2026-10-25"


def _run(**kwargs):
    inp = TaiyiInput.model_validate({"date": ANCHOR, **kwargs})
    return calculate(inp).chart_facts


def _lunar(day: str = ANCHOR):
    year, month, date = (int(part) for part in day.split("-"))
    return Solar.fromYmd(year, month, date).getLunar()


# ---- 常量与结构 ----

def test_star_names_cover_nine() -> None:
    assert len(TAIYI_STAR_NAMES) == 9
    assert len(set(TAIYI_STAR_NAMES)) == 9


def test_star_index_matches_name() -> None:
    """每层的太乙名必须与索引对应（索引是数据源给的，名称是本地常量）。"""
    facts = _run(mode="day")
    for scale, block in facts["layers"].items():
        index = block["index"] - 1
        assert block["taiyi_name"] == TAIYI_STAR_NAMES[index], f"{scale} 层名称与索引不符"


def test_layers_present() -> None:
    facts = _run(mode="day", hour=15)
    assert set(facts["layers"]) == {"year", "month", "day", "hour"}
    facts_no_hour = _run(mode="day")
    assert "hour" not in facts_no_hour["layers"]


def test_primary_follows_mode() -> None:
    for mode, hour in (("year", None), ("month", None), ("day", None), ("hour", 9)):
        facts = _run(mode=mode, hour=hour)
        assert facts["primary"]["scale"] == mode, mode
        assert facts["primary"]["taiyi_name"] == facts["layers"][mode]["taiyi_name"]


# ---- 年月日三层与数据源一致 ----

def test_year_month_day_match_source() -> None:
    facts = _run(mode="day")
    lunar = _lunar()
    assert facts["layers"]["year"]["index"] == lunar.getYearNineStar().getIndex() + 1
    assert facts["layers"]["month"]["index"] == lunar.getMonthNineStar().getIndex() + 1
    assert facts["layers"]["day"]["index"] == lunar.getDayNineStar().getIndex() + 1


def test_lunar_date_block() -> None:
    facts = _run(mode="day")
    assert facts["lunar_date"]["year_ganzhi"] == "丙午"
    assert facts["lunar_date"]["day_ganzhi"] == "壬申"
    assert facts["date"]["solar"] == ANCHOR


def test_day_officer_and_tian_shen_present() -> None:
    facts = _run(mode="day")
    assert facts["day_officer"] in tuple("建除满平定执破危成收开闭")
    assert facts["tian_shen"]["name"]
    assert facts["tian_shen"]["luck"] in ("吉", "凶", "中")


# ---- 时层独立重算 ----

def test_hour_star_formula_yang_period() -> None:
    """冬至后夏至前为阳：起数 7，顺推。"""
    index = _hour_star_index(
        solar_ymd="2026-01-15",
        winter_solstice="2025-12-21",
        summer_solstice="2026-06-21",
        day_branch="申",  # 非子午卯酉、非辰戌丑未 → 起数 7
        hour_index=0,
    )
    assert index == 6  # 7 + 0 - 1 = 6


def test_hour_star_formula_yin_period() -> None:
    """夏至后冬至前为阴：起数 3，逆推。"""
    index = _hour_star_index(
        solar_ymd="2026-10-25",
        winter_solstice="2025-12-21",
        summer_solstice="2026-06-21",
        day_branch="申",
        hour_index=0,
    )
    assert index == 2  # 3 - 0 - 1 = 2


def test_hour_star_zi_wu_mao_you_start() -> None:
    """日支属子午卯酉：阳起 1、阴起 9。"""
    assert (
        _hour_star_index(
            solar_ymd="2026-01-15",
            winter_solstice="2025-12-21",
            summer_solstice="2026-06-21",
            day_branch="子",
            hour_index=0,
        )
        == 0
    )
    assert (
        _hour_star_index(
            solar_ymd="2026-10-25",
            winter_solstice="2025-12-21",
            summer_solstice="2026-06-21",
            day_branch="子",
            hour_index=0,
        )
        == 8
    )


def test_hour_star_chen_xu_chou_wei_start() -> None:
    """日支属辰戌丑未：阳起 4、阴起 6。"""
    assert (
        _hour_star_index(
            solar_ymd="2026-01-15",
            winter_solstice="2025-12-21",
            summer_solstice="2026-06-21",
            day_branch="辰",
            hour_index=0,
        )
        == 3
    )
    assert (
        _hour_star_index(
            solar_ymd="2026-10-25",
            winter_solstice="2025-12-21",
            summer_solstice="2026-06-21",
            day_branch="辰",
            hour_index=0,
        )
        == 5
    )


def test_hour_star_wraps_in_range() -> None:
    """任意日支与时辰，索引必须落在 0–8。"""
    for branch in BRANCHES:
        for hour_index in range(12):
            for asc, (winter, summer, ymd) in (
                (True, ("2025-12-21", "2026-06-21", "2026-01-15")),
                (False, ("2025-12-21", "2026-06-21", "2026-10-25")),
            ):
                index = _hour_star_index(
                    solar_ymd=ymd,
                    winter_solstice=winter,
                    summer_solstice=summer,
                    day_branch=branch,
                    hour_index=hour_index,
                )
                assert 0 <= index <= 8, (branch, hour_index, asc)


def test_hour_layer_uses_formula() -> None:
    """引擎的时层结果必须与独立重算一致。"""
    facts = _run(mode="hour", hour=15)
    lunar = _lunar()
    jie_qi = lunar.getJieQiTable()
    expected = _hour_star_index(
        solar_ymd=lunar.getSolar().toYmd(),
        winter_solstice=jie_qi["冬至"].toYmd(),
        summer_solstice=jie_qi["夏至"].toYmd(),
        day_branch=lunar.getDayZhi(),
        hour_index=BRANCHES.index(hour_branch(15)),
    )
    assert facts["layers"]["hour"]["index"] == expected + 1


def test_hour_shichen_recorded() -> None:
    facts = _run(mode="hour", hour=15)
    assert facts["date"]["shichen"] == "申时"
    assert facts["date"]["hour"] == 15


# ---- 契约 ----

def test_question_dropped_when_not_stored() -> None:
    inp = TaiyiInput.model_validate(
        {"date": ANCHOR, "mode": "day", "question": "此事如何", "store_question": False}
    )
    result = calculate(inp)
    assert result.input_summary["question"] is None
    assert any("丢弃占问原文" in item for item in result.warnings)


def test_rejects_hour_mode_without_hour() -> None:
    with pytest.raises(ValidationError):
        TaiyiInput.model_validate({"date": ANCHOR, "mode": "hour"})


def test_rejects_out_of_range_date() -> None:
    with pytest.raises(ValidationError):
        TaiyiInput.model_validate({"date": "1799-12-31", "mode": "day"})
    with pytest.raises(ValidationError):
        TaiyiInput.model_validate({"date": "2201-01-01", "mode": "day"})


def test_rejects_unknown_school() -> None:
    with pytest.raises(ValidationError):
        TaiyiCalculateIn.model_validate(
            {"date": ANCHOR, "mode": "day", "convention": {"school": "qishier_ju_v1"}}
        )


def test_warns_when_hour_missing() -> None:
    inp = TaiyiInput.model_validate({"date": ANCHOR, "mode": "day"})
    result = calculate(inp)
    assert any("时层留空" in item for item in result.warnings)


def test_no_good_bad_conclusion_in_warnings() -> None:
    """红线：警告里不许出现吉凶结论式表述。"""
    inp = TaiyiInput.model_validate({"date": ANCHOR, "mode": "day"})
    result = calculate(inp)
    banned = ("宜", "忌", "建议", "大吉", "必凶")
    for item in result.warnings:
        for word in banned:
            assert word not in item, f"警告出现结论式表述「{word}」：{item}"


def test_triggered_rules_empty() -> None:
    inp = TaiyiInput.model_validate({"date": ANCHOR, "mode": "day"})
    assert calculate(inp).triggered_rules == []
