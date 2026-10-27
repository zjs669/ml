"""梅花易数引擎测试。

期望值不取引擎输出，而是按定义独立重算：
- 起卦数：年支数 + 农历月 + 农历日（+ 时支数），除 8 / 除 6 取余；
- 互卦：本卦二三四爻为下卦、三四五爻为上卦；
- 变卦：只动一爻；
- 错卦：六爻全变；综卦：六爻颠倒；
- 体用：动爻所在卦为用。

六十四卦的卦名映射由 `liuyao.hexagrams` 提供（已有独立推导测试），
这里只核对「六爻二进制 → 卦名」这一步有没有接错。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domains.calendar_core.jiazi import BRANCHES, hour_branch
from app.domains.calendar_core.lunar import solar_to_lunar
from app.domains.liuyao import constants as LC
from app.domains.liuyao.hexagrams import NAME_TO_INFO
from app.domains.meihua.engine import calculate
from app.domains.meihua.schemas import MeihuaCalculateIn, MeihuaInput

BITS = LC.TRIGRAM_BITS
NUMBER_TO_TRIGRAM = dict(LC.XIAN_TIAN_NUMBER)


def _run(**kwargs):
    inp = MeihuaInput.model_validate(kwargs)
    return calculate(inp).chart_facts


def _bits_of(name: str) -> str:
    return NAME_TO_INFO[name].bits


# ---- 起卦数 ----

def test_mod_rules() -> None:
    """除 8 余 0 作 8，除 6 余 0 作 6。"""
    from app.domains.meihua.engine import _mod6, _mod8

    assert _mod8(8) == 8
    assert _mod8(16) == 8
    assert _mod8(9) == 1
    assert _mod6(6) == 6
    assert _mod6(12) == 6
    assert _mod6(7) == 1


def test_time_method_independent_recompute() -> None:
    """时间起卦：按农历年月日时独立重算上下卦与动爻。"""
    facts = _run(method="time", cast_datetime="2026-10-25T15:00:00")
    lunar = solar_to_lunar(__import__("datetime").datetime(2026, 10, 25))
    year_number = BRANCHES.index(lunar.year_ganzhi[1]) + 1
    month_number = abs(lunar.month)
    day_number = lunar.day
    hour_number = BRANCHES.index(hour_branch(15)) + 1
    sum_upper = year_number + month_number + day_number
    sum_lower = sum_upper + hour_number
    assert facts["casting"]["upper_number"] == (sum_upper % 8 or 8)
    assert facts["casting"]["lower_number"] == (sum_lower % 8 or 8)
    assert facts["casting"]["moving_line"] == (sum_lower % 6 or 6)


def test_numbers_two_values() -> None:
    facts = _run(method="numbers", numbers=[7, 13])
    assert facts["casting"]["upper_number"] == 7 % 8 or 8
    assert facts["casting"]["lower_number"] == 13 % 8
    assert facts["casting"]["moving_line"] == (7 + 13) % 6


def test_numbers_three_values() -> None:
    facts = _run(method="numbers", numbers=[7, 13, 5])
    assert facts["casting"]["upper_number"] == 7
    assert facts["casting"]["lower_number"] == 5
    assert facts["casting"]["moving_line"] == 5


def test_measure_method() -> None:
    facts = _run(method="measure", length_value=9, width_value=5)
    assert facts["casting"]["upper_number"] == 9 % 8
    assert facts["casting"]["lower_number"] == 5
    assert facts["casting"]["moving_line"] == 14 % 6


def test_direction_method() -> None:
    facts = _run(method="direction", direction="南")
    assert facts["casting"]["upper_number"] == 3  # 离
    assert facts["casting"]["lower_number"] == 3
    assert facts["casting"]["moving_line"] == 6  # 3*2 = 6


def test_hexagram_method() -> None:
    facts = _run(method="hexagram", upper="乾", lower="坤", moving_line=3)
    assert facts["original"]["name"] == "天地否"
    assert facts["original"]["upper"] == "乾"
    assert facts["original"]["lower"] == "坤"


# ---- 卦象结构 ----

def test_original_bits_match_trigrams() -> None:
    """本卦六爻 = 下卦三爻 + 上卦三爻。"""
    for upper, lower in [("乾", "坤"), ("坎", "离"), ("震", "巽"), ("艮", "兑")]:
        facts = _run(method="hexagram", upper=upper, lower=lower, moving_line=1)
        assert facts["original"]["bits"] == BITS[lower] + BITS[upper]


def test_changed_flips_exactly_one_line() -> None:
    """变卦只动一爻，其余五位不变。"""
    for moving in range(1, 7):
        facts = _run(method="hexagram", upper="坎", lower="离", moving_line=moving)
        before = facts["original"]["bits"]
        after = facts["changed"]["bits"]
        diff = [i for i, (a, b) in enumerate(zip(before, after, strict=False)) if a != b]
        assert diff == [moving - 1], f"动爻 {moving} 的变卦差异位不对：{diff}"


def test_mutual_is_middle_lines() -> None:
    """互卦：二三四爻为下卦、三四五爻为上卦。"""
    facts = _run(method="hexagram", upper="乾", lower="坤", moving_line=1)
    bits = facts["original"]["bits"]
    assert facts["mutual"]["bits"] == bits[1:4] + bits[2:5]


def test_opposite_is_all_flipped() -> None:
    facts = _run(method="hexagram", upper="震", lower="艮", moving_line=2)
    bits = facts["original"]["bits"]
    expected = "".join("0" if b == "1" else "1" for b in bits)
    assert facts["opposite"]["bits"] == expected


def test_reversed_is_upside_down() -> None:
    facts = _run(method="hexagram", upper="巽", lower="兑", moving_line=4)
    bits = facts["original"]["bits"]
    assert facts["reversed"]["bits"] == "".join(reversed(bits))


def test_all_five_hexagrams_have_names() -> None:
    """五个卦名都必须能在六十四卦表里查到，不能出现空名。"""
    facts = _run(method="numbers", numbers=[3, 5])
    for key in ("original", "mutual", "changed", "opposite", "reversed"):
        assert facts[key]["name"] in NAME_TO_INFO, f"{key} 的卦名不在六十四卦表内"


# ---- 体用 ----

def test_body_use_follows_moving_line() -> None:
    """动爻在下卦（1–3）则下卦为用、上卦为体；动爻在上卦则相反。"""
    for moving in (1, 3, 4, 6):
        facts = _run(method="hexagram", upper="乾", lower="离", moving_line=moving)
        body = facts["body_use"]["body"]["trigram"]
        use = facts["body_use"]["use"]["trigram"]
        if moving <= 3:
            assert use == "离" and body == "乾", moving
        else:
            assert use == "乾" and body == "离", moving


def test_body_use_elements_match_trigrams() -> None:
    facts = _run(method="hexagram", upper="坎", lower="艮", moving_line=2)
    bu = facts["body_use"]
    assert bu["body"]["element"] == LC.TRIGRAM_ELEMENT[bu["body"]["trigram"]]
    assert bu["use"]["element"] == LC.TRIGRAM_ELEMENT[bu["use"]["trigram"]]


def test_relation_covers_five_cases() -> None:
    """五行生克五种关系都要能出现，且方向正确。"""
    from app.domains.meihua.engine import _relation

    assert _relation("金", "金") == "同我"
    assert _relation("金", "土") == "生我"   # 土生金
    assert _relation("金", "水") == "我生"   # 金生水
    assert _relation("金", "火") == "克我"   # 火克金
    assert _relation("金", "木") == "我克"   # 金克木


# ---- 契约 ----

def test_question_dropped_when_not_stored() -> None:
    inp = MeihuaInput.model_validate(
        {
            "method": "numbers",
            "numbers": [3, 4],
            "question": "此事可成否",
            "store_question": False,
        }
    )
    result = calculate(inp)
    assert result.input_summary["question"] is None
    assert any("丢弃占问原文" in item for item in result.warnings)


def test_rejects_missing_payload() -> None:
    with pytest.raises(ValidationError):
        MeihuaInput.model_validate({"method": "time"})
    with pytest.raises(ValidationError):
        MeihuaInput.model_validate({"method": "numbers"})
    with pytest.raises(ValidationError):
        MeihuaInput.model_validate({"method": "text"})
    with pytest.raises(ValidationError):
        MeihuaInput.model_validate({"method": "measure"})
    with pytest.raises(ValidationError):
        MeihuaInput.model_validate({"method": "direction"})
    with pytest.raises(ValidationError):
        MeihuaInput.model_validate({"method": "hexagram"})


def test_rejects_bad_numbers_count() -> None:
    with pytest.raises(ValidationError):
        MeihuaInput.model_validate({"method": "numbers", "numbers": [1]})
    with pytest.raises(ValidationError):
        MeihuaInput.model_validate({"method": "numbers", "numbers": [1, 2, 3, 4]})


def test_rejects_unknown_trigram() -> None:
    with pytest.raises(ValidationError):
        MeihuaInput.model_validate(
            {"method": "hexagram", "upper": "甲", "lower": "坤", "moving_line": 1}
        )


def test_rejects_unknown_direction() -> None:
    inp = MeihuaInput.model_validate({"method": "direction", "direction": "上"})
    with pytest.raises(ValueError):
        calculate(inp)


def test_rejects_unknown_school() -> None:
    with pytest.raises(ValidationError):
        MeihuaCalculateIn.model_validate(
            {"method": "numbers", "numbers": [1, 2], "convention": {"school": "zhang_v1"}}
        )


def test_text_method_warns_about_approximation() -> None:
    inp = MeihuaInput.model_validate({"method": "text", "text": "占一卦"})
    result = calculate(inp)
    assert any("近似" in item for item in result.warnings)


def test_triggered_rules_empty() -> None:
    inp = MeihuaInput.model_validate({"method": "numbers", "numbers": [2, 3]})
    assert calculate(inp).triggered_rules == []
