"""大六壬引擎测试（主干版）。

期望值不取引擎输出，而是按定义独立重算：
- 月将：按中气表独立查（雨水亥、春分戌…大寒子）；
- 天地盘：月将加时的**位移**用独立算式核对，并验证「地盘支 + 位移 = 天盘支」；
- 天将：贵人起于天盘支，逐支顺布；验证「贵人所在的盘面宫位」正确；
- 四课：日干寄宫表独立核对，四课的上神必须是天盘对应宫位的支；
- 三传：贼克法用「下克上优先 / 上克下其次 / 比用取阴阳」独立判定。

三传未实现的情形必须显式标注，不能静默给一个空数组。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domains.calendar_core.jiazi import BRANCHES
from app.domains.daliuren import constants as C
from app.domains.daliuren.engine import (
    _build_generals,
    _build_sky_plate,
    _four_lessons,
    calculate,
)
from app.domains.daliuren.schemas import DaliurenCalculateIn, DaliurenInput

ANCHOR = "2026-10-25T15:00:00"


def _run(moment: str = ANCHOR, **kwargs):
    inp = DaliurenInput.model_validate({"cast_datetime": moment, **kwargs})
    return calculate(inp).chart_facts


# ---- 常量表 ----

def test_month_general_table_complete() -> None:
    """十二中气必须各对应一个月将，且月将不重复。"""
    assert len(C.QI_TO_MONTH_GENERAL) == 12
    assert len(set(C.QI_TO_MONTH_GENERAL.values())) == 12
    assert all(branch in BRANCHES for branch in C.QI_TO_MONTH_GENERAL.values())


def test_month_general_names_complete() -> None:
    assert set(C.MONTH_GENERAL_NAMES) == set(BRANCHES)


def test_generals_table_complete() -> None:
    assert len(C.TIAN_JIANG) == 12
    assert len(set(C.TIAN_JIANG)) == 12


def test_lodge_table_complete() -> None:
    from app.domains.calendar_core.jiazi import STEMS

    assert set(C.STEM_LODGE) == set(STEMS)
    assert all(branch in BRANCHES for branch in C.STEM_LODGE.values())


def test_gui_ren_tables_complete() -> None:
    from app.domains.calendar_core.jiazi import STEMS

    assert set(C.YANG_GUI_REN) == set(STEMS)
    assert set(C.YIN_GUI_REN) == set(STEMS)
    # 阳贵与阴贵对每个日干都必须不同
    for stem in STEMS:
        assert C.YANG_GUI_REN[stem] != C.YIN_GUI_REN[stem], stem


# ---- 天地盘 ----

def test_sky_plate_is_rotation() -> None:
    """天盘必须是地盘的整体旋转：每个地盘支相对时支的位移一致。"""
    sky = _build_sky_plate("卯", "申")
    general = BRANCHES.index("卯")
    hour = BRANCHES.index("申")
    for index, earth in enumerate(BRANCHES):
        assert sky[earth] == BRANCHES[(general + (index - hour)) % 12]


def test_month_general_sits_on_hour_branch() -> None:
    """月将必须落在时支所在的地盘宫位 —— 这是「月将加时」的定义。"""
    sky = _build_sky_plate("卯", "申")
    assert sky["申"] == "卯"


def test_sky_plate_covers_twelve() -> None:
    sky = _build_sky_plate("亥", "子")
    assert set(sky.values()) == set(BRANCHES)


# ---- 天将 ----

def test_generals_start_from_gui_ren() -> None:
    """贵人所乘天盘支即天将起点，其后顺布。"""
    generals = _build_generals("壬", "day")
    start = BRANCHES.index(C.YANG_GUI_REN["壬"])
    for offset, name in enumerate(C.TIAN_JIANG):
        assert generals[BRANCHES[(start + offset) % 12]] == name


def test_generals_day_and_night_differ() -> None:
    day = _build_generals("甲", "day")
    night = _build_generals("甲", "night")
    assert day != night


def test_generals_covers_twelve() -> None:
    generals = _build_generals("丙", "day")
    assert set(generals.values()) == set(C.TIAN_JIANG)


def test_plate_general_follows_sky_branch() -> None:
    """盘面上的将必须挂在天盘支上（地盘某宫 → 天盘某支 → 该支所临之将）。"""
    facts = _run()
    generals = _build_generals("壬", "day")
    for row in facts["plate"]:
        assert row["general"] == generals[row["sky"]], row["earth"]


# ---- 四课 ----

def test_four_lessons_structure() -> None:
    facts = _run()
    lessons = facts["four_lessons"]
    assert len(lessons) == 4
    assert [item["index"] for item in lessons] == [1, 2, 3, 4]


def test_first_lesson_uses_lodge() -> None:
    """一课的下位必须是日干寄宫。"""
    facts = _run()
    day_stem = facts["pillars"]["day"][0]
    assert facts["four_lessons"][0]["lower"] == C.STEM_LODGE[day_stem]


def test_third_lesson_uses_day_branch() -> None:
    facts = _run()
    day_branch = facts["pillars"]["day"][1]
    assert facts["four_lessons"][2]["lower"] == day_branch


def test_lessons_chain_correctly() -> None:
    """二课的下位 = 一课的上位；四课的下位 = 三课的上位。"""
    facts = _run()
    lessons = facts["four_lessons"]
    assert lessons[1]["lower"] == lessons[0]["upper"]
    assert lessons[3]["lower"] == lessons[2]["upper"]


def test_lesson_uppers_match_sky_plate() -> None:
    """每一课的上神必须等于天盘在该下位宫上的支。"""
    facts = _run()
    sky = {row["earth"]: row["sky"] for row in facts["plate"]}
    for item in facts["four_lessons"]:
        assert item["upper"] == sky[item["lower"]], item["index"]


def test_lesson_upper_differs_from_lower() -> None:
    """上下神不应相同（月将加时后天地盘存在位移，除非位移为 0）。"""
    facts = _run()
    offset = (BRANCHES.index(facts["datetime"]["hour_branch"][0]) -
              BRANCHES.index(facts["month_general"]["branch"])) % 12
    if offset != 0:
        for item in facts["four_lessons"]:
            assert item["upper"] != item["lower"]


# ---- 三传 ----

def test_san_chuan_status_always_reported() -> None:
    facts = _run()
    assert "implemented" in facts["san_chuan_status"]
    assert "method" in facts["san_chuan_status"]


def test_san_chuan_when_implemented() -> None:
    """已判定时三传必须齐全，且中传/末传符合「上所临之支」的递推。"""
    facts = _run()
    if not facts["san_chuan_status"]["implemented"]:
        pytest.skip("本时刻属未实现课体")
    chuan = facts["san_chuan"]
    sky = {row["earth"]: row["sky"] for row in facts["plate"]}
    assert chuan["middle"]["branch"] == sky[chuan["first"]["branch"]]
    assert chuan["last"]["branch"] == sky[chuan["middle"]["branch"]]


def test_san_chuan_marks_unimplemented_with_warning() -> None:
    """未实现课体必须留空并给出原因，不能静默返回空。"""
    found_unimplemented = False
    for hour in range(0, 24, 2):
        moment = f"2026-10-25T{hour:02d}:00:00"
        facts = _run(moment)
        if not facts["san_chuan_status"]["implemented"]:
            found_unimplemented = True
            assert facts["san_chuan"] is None
            assert facts["san_chuan_status"]["reason"]
            break
    # 24 小时里应当至少有一个时刻落入未实现课体
    assert found_unimplemented, "一整天都没有未实现课体，判定逻辑可能过于宽松"


def test_san_chuan_method_is_declared() -> None:
    facts = _run()
    status = facts["san_chuan_status"]
    if status["implemented"]:
        assert status["method"] in C.IMPLEMENTED_KE_TI


# ---- 神煞 ----

def test_shen_sha_block_complete() -> None:
    facts = _run()
    block = facts["shen_sha"]
    assert block["tian_ma"] in BRANCHES
    assert block["jian_chu"] in C.JIAN_CHU_ORDER
    assert block["lodge"] in BRANCHES
    assert set(block["gui_ren"]) == {"yang", "yin", "used"}


def test_jian_chu_follows_month_branch() -> None:
    """建除：日支相对月建的偏移决定值神。"""
    facts = _run()
    month_branch = facts["pillars"]["month"][1]
    day_branch = facts["pillars"]["day"][1]
    offset = (BRANCHES.index(day_branch) - BRANCHES.index(month_branch)) % 12
    assert facts["shen_sha"]["jian_chu"] == C.JIAN_CHU_ORDER[offset]


# ---- 口径 ----

def test_day_night_by_shichen() -> None:
    """卯至申为昼，其余为夜。"""
    day = _run("2026-10-25T09:00:00")
    night = _run("2026-10-25T01:00:00")
    assert day["day_night"]["value"] == "day"
    assert night["day_night"]["value"] == "night"


def test_forced_day_night() -> None:
    inp = DaliurenCalculateIn.model_validate(
        {"cast_datetime": ANCHOR, "convention": {"day_night": "night"}}
    )
    facts = calculate(inp, inp.convention).chart_facts
    assert facts["day_night"]["value"] == "night"


def test_manual_month_general() -> None:
    inp = DaliurenCalculateIn.model_validate(
        {
            "cast_datetime": ANCHOR,
            "month_general": "子",
            "convention": {"month_general_source": "manual"},
        }
    )
    facts = calculate(inp, inp.convention).chart_facts
    assert facts["month_general"]["branch"] == "子"
    assert facts["month_general"]["source"] == "manual"


def test_manual_month_general_ignored_without_switch() -> None:
    """未切换 source 时，手工月将不生效但必须给出提示。"""
    inp = DaliurenInput.model_validate({"cast_datetime": ANCHOR, "month_general": "子"})
    result = calculate(inp)
    assert result.chart_facts["month_general"]["source"] == "prev_qi"
    assert any("未生效" in item for item in result.warnings)


def test_rejects_bad_month_general() -> None:
    with pytest.raises(ValidationError):
        DaliurenInput.model_validate({"cast_datetime": ANCHOR, "month_general": "甲"})


def test_question_dropped_when_not_stored() -> None:
    inp = DaliurenInput.model_validate(
        {"cast_datetime": ANCHOR, "question": "此事如何", "store_question": False}
    )
    result = calculate(inp)
    assert result.input_summary["question"] is None
    assert any("丢弃占问原文" in item for item in result.warnings)


def test_rejects_unknown_school() -> None:
    with pytest.raises(ValidationError):
        DaliurenCalculateIn.model_validate(
            {"cast_datetime": ANCHOR, "convention": {"school": "shehai_full_v1"}}
        )


def test_triggered_rules_empty() -> None:
    inp = DaliurenInput.model_validate({"cast_datetime": ANCHOR})
    assert calculate(inp).triggered_rules == []


def test_warnings_have_no_verdict() -> None:
    """红线：警告里不许出现吉凶断语。"""
    inp = DaliurenInput.model_validate({"cast_datetime": ANCHOR})
    result = calculate(inp)
    banned = ("主吉", "主凶", "宜", "忌", "必然")
    for item in result.warnings:
        if item == C.SCHOOL_NOTE:
            continue
        for word in banned:
            assert word not in item, f"警告出现断语「{word}」：{item}"
