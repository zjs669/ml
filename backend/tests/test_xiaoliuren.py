"""小六壬引擎测试。

期望值不取引擎输出，而是按「月→日→时」三宫递推的歌诀独立重算：
月上起大安数到农历月，再从月宫数到农历日，再从日宫数到时辰。
递推本身只有取模，容易写反方向，因此这里显式写出每一步的起点与落点。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domains.xiaoliuren import constants as C
from app.domains.xiaoliuren.engine import _clock_to_shichen, calculate
from app.domains.xiaoliuren.schemas import (
    XiaoliurenCalculateIn,
    XiaoliurenConvention,
    XiaoliurenInput,
)

FIXTURES = Path(__file__).parent / "fixtures" / "xiaoliuren_cases.json"
DATA = json.loads(FIXTURES.read_text(encoding="utf-8"))

#: 独立重算用的六宫顺序（与引擎常量分开写一份，避免同源错误）
PALACES = ["大安", "留连", "速喜", "赤口", "小吉", "空亡"]


def _derive(lunar_month: int, lunar_day: int, shichen: int) -> tuple[str, str, str]:
    """按歌诀逐步推：月上起大安 → 日上从月宫起 → 时上从日宫起。"""
    month_pos = (lunar_month - 1) % 6
    day_pos = (month_pos + lunar_day - 1) % 6
    hour_pos = (day_pos + shichen - 1) % 6
    return PALACES[month_pos], PALACES[day_pos], PALACES[hour_pos]


def test_constants_are_consistent() -> None:
    """常量表必须自洽：六宫顺序、每宫属性、歌诀三张表键集合一致。"""
    assert len(C.STATUS_ORDER) == 6
    assert len(set(C.STATUS_ORDER)) == 6
    assert set(C.STATUS_INFO) == set(C.STATUS_ORDER)
    assert set(C.STATUS_POEMS) == set(C.STATUS_ORDER)
    for name in C.STATUS_ORDER:
        info = C.STATUS_INFO[name]
        assert info["nature"] in ("吉", "凶", "半吉半凶")
        assert info["element"] in ("木", "火", "土", "金", "水")


def test_palaces_match_independent_derivation() -> None:
    """固定用例：每例的三宫都与独立重算一致。"""
    for case in DATA["cases"]:
        inp = XiaoliurenInput.model_validate(case["input"])
        result = calculate(inp)
        facts = result.chart_facts
        expect = case["expect"]
        assert facts["month_palace"]["name"] == expect["month_palace"], case["case_id"]
        assert facts["day_palace"]["name"] == expect["day_palace"], case["case_id"]
        assert facts["result_palace"]["name"] == expect["result_palace"], case["case_id"]
        # 与独立重算交叉核对
        shichen = facts["shichen"]["index"]
        derived = _derive(expect["lunar_month"], expect["lunar_day"], shichen)
        assert derived == (expect["month_palace"], expect["day_palace"], expect["result_palace"]), (
            case["case_id"]
        )


def test_month_starts_from_daan() -> None:
    """农历正月必落大安：歌诀「月上起大安」的锚点。"""
    inp = XiaoliurenInput.model_validate(
        {"input_mode": "lunar", "lunar_month": 1, "lunar_day": 1, "hour": 1}
    )
    facts = calculate(inp).chart_facts
    assert facts["month_palace"]["name"] == "大安"
    assert facts["day_palace"]["name"] == "大安"
    # hour=1 按 clock 口径换算为丑时（第 2 时辰），故时宫再进一位
    assert facts["result_palace"]["name"] == "留连"


def test_full_cycle_wraps_six() -> None:
    """月数 +6 落回同一宫：六宫循环的基本性质。"""
    base = calculate(
        XiaoliurenInput.model_validate(
            {"input_mode": "lunar", "lunar_month": 1, "lunar_day": 1, "hour": 1}
        )
    ).chart_facts
    shifted = calculate(
        XiaoliurenInput.model_validate(
            {"input_mode": "lunar", "lunar_month": 7, "lunar_day": 1, "hour": 1}
        )
    ).chart_facts
    assert base["month_palace"]["name"] == shifted["month_palace"]["name"]


def test_hour_conversion() -> None:
    """23:00 起子时；每两小时一个时辰（子 23–01，丑 01–03，…）。"""
    assert _clock_to_shichen(0) == 1   # 00:xx 属子时
    assert _clock_to_shichen(1) == 2   # 01:xx 已入丑时
    assert _clock_to_shichen(2) == 2
    assert _clock_to_shichen(3) == 3
    assert _clock_to_shichen(15) == 9  # 申时
    assert _clock_to_shichen(23) == 1  # 子时


def test_shichen_mode_accepts_1_to_12() -> None:
    """shichen 模式下 hour 是时辰序号，与 clock 模式语义不同。"""
    inp = XiaoliurenCalculateIn.model_validate(
        {
            "input_mode": "lunar",
            "lunar_month": 9,
            "lunar_day": 16,
            "hour": 9,
            "convention": {"hour_type": "shichen"},
        }
    )
    facts = calculate(inp, inp.convention).chart_facts
    assert facts["shichen"]["name"] == "申时"
    assert facts["shichen"]["clock_hour"] is None


def test_gregorian_and_lunar_modes_agree() -> None:
    """同一日期的公历输入与农历输入必须得到相同三宫。"""
    gregorian = calculate(
        XiaoliurenInput.model_validate(
            {"input_mode": "gregorian", "date": "2026-10-25T00:00:00", "hour": 15}
        )
    ).chart_facts
    lunar = calculate(
        XiaoliurenInput.model_validate(
            {"input_mode": "lunar", "lunar_month": 9, "lunar_day": 16, "hour": 15}
        )
    ).chart_facts
    assert gregorian["result_palace"]["name"] == lunar["result_palace"]["name"]
    assert gregorian["month_palace"]["name"] == lunar["month_palace"]["name"]


def test_leap_month_strategies_differ() -> None:
    """闰月 advance 比 repeat 多进一月，落点应相差一位。"""
    repeat_in = XiaoliurenCalculateIn.model_validate(
        {
            "input_mode": "lunar",
            "lunar_month": 4,
            "lunar_day": 1,
            "is_leap_month": True,
            "hour": 1,
        }
    )
    advance_in = XiaoliurenCalculateIn.model_validate(
        {
            "input_mode": "lunar",
            "lunar_month": 4,
            "lunar_day": 1,
            "is_leap_month": True,
            "hour": 1,
            "convention": {"leap_month_strategy": "advance"},
        }
    )
    repeat = calculate(repeat_in, repeat_in.convention).chart_facts
    advance = calculate(advance_in, advance_in.convention).chart_facts
    assert repeat["month_palace"]["name"] != advance["month_palace"]["name"]
    idx_repeat = PALACES.index(repeat["month_palace"]["name"])
    idx_advance = PALACES.index(advance["month_palace"]["name"])
    assert idx_advance == (idx_repeat + 1) % 6


def test_question_is_dropped_when_not_stored() -> None:
    """store_question=False 时占问原文不得进入 input_summary。"""
    inp = XiaoliurenInput.model_validate(
        {
            "input_mode": "lunar",
            "lunar_month": 3,
            "lunar_day": 5,
            "hour": 4,
            "question": "这件事能否成",
            "store_question": False,
        }
    )
    result = calculate(inp)
    assert result.input_summary["question"] is None
    assert any("丢弃占问原文" in item for item in result.warnings)


def test_rejects_mixed_input() -> None:
    """公历与农历输入不能同时提供。"""
    with pytest.raises(ValidationError):
        XiaoliurenInput.model_validate(
            {
                "input_mode": "gregorian",
                "date": "2026-10-25T00:00:00",
                "lunar_month": 9,
                "lunar_day": 16,
                "hour": 15,
            }
        )


def test_rejects_unknown_school() -> None:
    """未实现的流派必须校验失败，不能静默套用。"""
    with pytest.raises(ValidationError):
        XiaoliurenConvention.model_validate({"school": "zhangjue_v1"})


def test_algorithm_version_is_recorded() -> None:
    result = calculate(
        XiaoliurenInput.model_validate(
            {"input_mode": "lunar", "lunar_month": 2, "lunar_day": 2, "hour": 2}
        )
    )
    assert result.algorithm_version.startswith("xiaoliuren-engine-")
    assert result.domain == "xiaoliuren"


def test_no_triggered_rules() -> None:
    """小六壬没有关系规则，triggered_rules 必须为空（不留伪规则）。"""
    result = calculate(
        XiaoliurenInput.model_validate(
            {"input_mode": "lunar", "lunar_month": 5, "lunar_day": 5, "hour": 5}
        )
    )
    assert result.triggered_rules == []


def test_gregorian_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        XiaoliurenInput.model_validate(
            {"input_mode": "gregorian", "date": "1799-12-31T00:00:00", "hour": 1}
        )
