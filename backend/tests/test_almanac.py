"""黄历引擎测试。

期望值一律不取引擎输出：农历日期、干支、值星、星宿用**独立常量表**核对，
宜忌条目只断言「非空且结构完整」，不断言具体词条 —— 那是数据源的编纂结果，
不是可推导的事实，锁死具体词条会让升级历法库时无谓地红一片。
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.domains.almanac.engine import calculate
from app.domains.almanac.schemas import AlmanacCalculateIn, AlmanacInput

#: 独立锚点：2026-10-25 = 农历丙午年九月十六（香港天文台 2026 年公历农历对照表）
ANCHOR = date(2026, 10, 25)

#: 十二值星（建除十二神）固定顺序
ZHIXING_ORDER = ("建", "除", "满", "平", "定", "执", "破", "危", "成", "收", "开", "闭")

#: 二十八宿固定顺序
XIU_ORDER = (
    "角", "亢", "氐", "房", "心", "尾", "箕",
    "斗", "牛", "女", "虚", "危", "室", "壁",
    "奎", "娄", "胃", "昴", "毕", "觜", "参",
    "井", "鬼", "柳", "星", "张", "翼", "轸",
)


def _facts(day: date, **kwargs):
    payload = {"date": day.isoformat(), **kwargs}
    inp = AlmanacInput.model_validate(payload)
    return calculate(inp).chart_facts


def test_anchor_lunar_date() -> None:
    """锚点日期：农历年月日与干支必须与独立来源一致。"""
    facts = _facts(ANCHOR)
    lunar = facts["lunar_date"]
    assert lunar["year"] == 2026
    assert lunar["month"] == 9
    assert lunar["day"] == 16
    assert lunar["is_leap_month"] is False
    assert lunar["year_ganzhi"] == "丙午"
    assert lunar["day_ganzhi"] == "壬申"


def test_zhi_xing_matches_branch_offset() -> None:
    """值星必须等于「日支相对月建的偏移」——按定义独立重算，不用引擎公式。

    建除十二神：月建之支当日为「建」，其后逐日顺推。
    因此 索引 = (日支序号 - 月建支序号) mod 12。
    交节换月建时偏移会跳变，这是历法行为；用公式核对就不会误判为缺陷。
    """
    branch_index = {name: i for i, name in enumerate("子丑寅卯辰巳午未申酉戌亥")}
    checked = 0
    for offset in range(40):
        day = date(2026, 10, 1) + timedelta(days=offset)
        facts = _facts(day)
        month_branch = facts["lunar_date"]["month_ganzhi"][1]
        day_branch = facts["lunar_date"]["day_ganzhi"][1]
        expected = ZHIXING_ORDER[(branch_index[day_branch] - branch_index[month_branch]) % 12]
        assert facts["day_pillar"]["zhi_xing"] == expected, (
            f"{day} 值星应为 {expected}，实际 {facts['day_pillar']['zhi_xing']}"
        )
        checked += 1
    assert checked == 40


def test_xiu_in_fixed_order() -> None:
    """星宿必须是二十八宿之一，且连续日期按固定顺序推进。"""
    prev_index = None
    for offset in range(10):
        day = date(2026, 10, 1 + offset)
        xiu = _facts(day)["xiu"]
        assert xiu["name"] in XIU_ORDER, xiu["name"]
        assert xiu["luck"] in ("吉", "凶", "中")
        index = XIU_ORDER.index(xiu["name"])
        if prev_index is not None:
            assert index == (prev_index + 1) % 28, f"{day} 星宿未按二十八宿顺序推进"
        prev_index = index


def test_yi_ji_are_lists_of_strings() -> None:
    """宜忌必须是字符串列表；结构完整比具体词条更重要。"""
    facts = _facts(ANCHOR)
    assert isinstance(facts["yi"], list)
    assert isinstance(facts["ji"], list)
    assert all(isinstance(item, str) and item for item in facts["yi"])
    assert all(isinstance(item, str) and item for item in facts["ji"])
    # 同一日不可能既列宜又列忌同一个词
    assert not (set(facts["yi"]) & set(facts["ji"]))


def test_hour_slots_cover_twelve_shichen() -> None:
    """时辰吉凶必须覆盖 12 个时辰，且干支两两不同。"""
    facts = _facts(ANCHOR)
    slots = facts["hour_slots"]
    assert len(slots) == 12 or len(slots) == 13, f"时辰数异常：{len(slots)}"
    ganzhi = [slot["ganzhi"] for slot in slots[:12]]
    assert len(set(ganzhi)) == 12
    for slot in slots:
        assert isinstance(slot["yi"], list)
        assert isinstance(slot["ji"], list)


def test_positions_have_six_entries() -> None:
    """方位条目必须齐全：喜神、阳贵、阴贵、福神、财神、太岁。"""
    facts = _facts(ANCHOR)
    assert set(facts["positions"]) == {"xi", "yang_gui", "yin_gui", "fu", "cai", "tai_sui"}
    for key, item in facts["positions"].items():
        assert item["branch"], f"{key} 缺地支"
        assert item["desc"], f"{key} 缺方位描述"


def test_nine_star_block_complete() -> None:
    """九星块必须含数字、五行与三套命名，缺一即视为结构退化。"""
    facts = _facts(ANCHOR)
    star = facts["nine_star"]
    assert star["number"] in ("一", "二", "三", "四", "五", "六", "七", "八", "九")
    assert star["element"] in ("水", "土", "木", "金", "火")
    assert star["xuan_kong"]["name"]
    assert star["qi_men"]["name"]
    assert star["tai_yi"]["name"]


def test_birth_date_is_annotation_only() -> None:
    """出生日期只作对照标注，不改变任何宜忌条目。"""
    plain = _facts(ANCHOR)
    personalized = _facts(ANCHOR, birth_date="1990-05-15")
    assert personalized["yi"] == plain["yi"]
    assert personalized["ji"] == plain["ji"]
    assert personalized["hour_slots"] == plain["hour_slots"]
    assert personalized["personal"]["birth_date"] == "1990-05-15"
    assert "不参与宜忌判定" in personalized["personal"]["note"]


def test_birth_date_after_target_rejected() -> None:
    with pytest.raises(ValidationError):
        AlmanacInput.model_validate({"date": "2020-01-01", "birth_date": "2021-01-01"})


def test_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        AlmanacInput.model_validate({"date": "1799-12-31"})
    with pytest.raises(ValidationError):
        AlmanacInput.model_validate({"date": "2201-01-01"})


def test_convention_is_echoed() -> None:
    inp = AlmanacCalculateIn.model_validate({"date": ANCHOR.isoformat()})
    result = calculate(inp, inp.convention)
    assert result.convention["school"] == "tongshu_daily_v1"
    assert result.convention["day_boundary"] == "midnight"
    assert "school_note" in result.convention


def test_no_good_bad_conclusion_in_warnings() -> None:
    """红线：警告里不许出现吉凶结论式表述。"""
    inp = AlmanacInput.model_validate({"date": ANCHOR.isoformat()})
    result = calculate(inp)
    banned = ("适合", "不宜", "大吉", "必凶", "建议")
    for item in result.warnings:
        for word in banned:
            assert word not in item, f"警告出现结论式表述「{word}」：{item}"


def test_triggered_rules_empty() -> None:
    """黄历没有关系规则，triggered_rules 必须为空。"""
    inp = AlmanacInput.model_validate({"date": ANCHOR.isoformat()})
    assert calculate(inp).triggered_rules == []
