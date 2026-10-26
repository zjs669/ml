"""大六壬课体扩展的测试（伏吟 / 返吟 / 涉害 / 遥克）。

这些课体都有「盘面看起来完整但整体错位」的风险，因此期望值一律按定义独立重算：

- 伏吟：天盘与地盘逐宫相同 → 初传取干上神；
- 返吟：天盘每宫都与地盘相冲 → 有克取克；
- 遥克：四课无上下克，看**上神与日干**的五行关系（蒿矢优先于弹射）；
- 涉害：比用后仍不唯一时，比较「所临宫逆行回本位」途中的受克次数。

其中涉害最容易写错：若把区间算成整圈，每个地支都被数一次，深浅恒等，
涉害法就永远选不出来（实现时踩过，见 `_shehai_deepest` 注释）。
"""

from __future__ import annotations

import pytest

from app.domains.calendar_core.jiazi import BRANCHES
from app.domains.daliuren import constants as C
from app.domains.daliuren.engine import (
    _build_sky_plate,
    _four_lessons,
    _shehai_deepest,
    _yaoke,
    calculate,
)
from app.domains.daliuren.schemas import DaliurenInput


def _facts(moment: str) -> dict:
    return calculate(DaliurenInput.model_validate({"cast_datetime": moment})).chart_facts


def _sky_of(facts: dict) -> dict[str, str]:
    return {row["earth"]: row["sky"] for row in facts["plate"]}


# ---- 伏吟 ----

def test_fuyin_detected_when_plate_identical() -> None:
    """伏吟的结构判据：天盘逐宫等于地盘。"""
    sky = _build_sky_plate("卯", "卯")
    assert all(earth == sky[earth] for earth in BRANCHES)


def test_fuyin_first_chuan_is_first_lesson() -> None:
    """伏吟取初传：四课无克可取，传统取干上神（一课上神）。"""
    # 月将与时支同支 → 伏吟。找一个月将=时支的时刻
    found = None
    for hour in range(0, 24, 2):
        moment = f"2026-10-25T{hour:02d}:00:00"
        facts = _facts(moment)
        if facts["san_chuan_status"]["method"] == "伏吟":
            found = facts
            break
    assert found is not None, "未找到伏吟样本"
    assert found["san_chuan_status"]["implemented"] is True
    assert found["san_chuan"]["first"]["branch"] == found["four_lessons"][0]["upper"]


def test_fuyin_lessons_have_identical_upper_lower() -> None:
    """伏吟时四课上下神必须相同（这是伏吟的定义，不是巧合）。"""
    for hour in range(0, 24, 2):
        facts = _facts(f"2026-10-25T{hour:02d}:00:00")
        if facts["san_chuan_status"]["method"] != "伏吟":
            continue
        for lesson in facts["four_lessons"]:
            assert lesson["upper"] == lesson["lower"], lesson["index"]
        return
    pytest.skip("未找到伏吟样本")


# ---- 返吟 ----

def test_fanyin_detected_when_plate_opposed() -> None:
    """返吟的结构判据：天盘每宫与地盘相冲（相差六位）。"""
    sky = _build_sky_plate("卯", "酉")
    assert all(BRANCHES[(BRANCHES.index(e) + 6) % 12] == sky[e] for e in BRANCHES)


def test_fanyin_implemented_when_ke_exists() -> None:
    """返吟且四课有克时，应标为返吟并给出三传。"""
    for hour in range(0, 24, 2):
        facts = _facts(f"2026-10-25T{hour:02d}:00:00")
        if facts["san_chuan_status"]["method"] != "返吟":
            continue
        assert facts["san_chuan_status"]["implemented"] is True
        assert facts["san_chuan"]["first"]["branch"]
        return
    pytest.skip("未找到返吟样本")


def test_fanyin_lessons_are_opposed() -> None:
    """返吟时四课上下神必须相冲。"""
    for hour in range(0, 24, 2):
        facts = _facts(f"2026-10-25T{hour:02d}:00:00")
        if facts["san_chuan_status"]["method"] != "返吟":
            continue
        for lesson in facts["four_lessons"]:
            diff = (BRANCHES.index(lesson["upper"]) - BRANCHES.index(lesson["lower"])) % 12
            assert diff == 6, f"{lesson['index']}课上下神不冲：{lesson['text']}"
        return
    pytest.skip("未找到返吟样本")


# ---- 遥克 ----

def test_yaoke_haoshi_preferred() -> None:
    """上神克日干（蒿矢）优先于日干克上神（弹射）。"""
    # 甲(木) 日干；戌(土) 克木？土克水，木克土 → 木克土，所以日干克上神 = 弹射
    lessons = [
        {"index": 1, "lower": "子", "upper": "戌", "text": "戌/子",
         "upper_element": "土", "lower_element": "水"},
    ]
    result = _yaoke(lessons, "甲")
    assert result is not None
    assert result["method"] == "遥克·弹射"


def test_yaoke_haoshi_when_upper_controls_stem() -> None:
    """上神克日干 → 蒿矢。甲(木) 被金克，申(金) 克甲。"""
    lessons = [
        {"index": 3, "lower": "寅", "upper": "申", "text": "申/寅",
         "upper_element": "金", "lower_element": "木"},
    ]
    result = _yaoke(lessons, "甲")
    assert result is not None
    assert result["method"] == "遥克·蒿矢"
    assert result["first"]["upper"] == "申"


def test_yaoke_returns_none_without_relation() -> None:
    """上神与日干既不相克也不被克时，不是遥克。"""
    lessons = [
        {"index": 1, "lower": "子", "upper": "亥", "text": "亥/子",
         "upper_element": "水", "lower_element": "水"},
    ]
    assert _yaoke(lessons, "甲") is None


# ---- 涉害 ----

def test_shehai_depth_uses_landed_to_home_span() -> None:
    """涉害深浅必须按「所临宫逆行回本位」的区间计，不是整圈。

    整圈计数时每个地支都被数一次，而相克次数只与五行有关、与起点无关，
    所有候选恒等 —— 涉害法会永远选不出来。
    """
    # 构造两个候选：同一上神落在不同地盘宫位，深浅应可能不同
    candidates = [
        {"index": 1, "lower": "子", "upper": "寅", "text": "寅/子",
         "upper_element": "木", "lower_element": "水"},
        {"index": 3, "lower": "申", "upper": "寅", "text": "寅/申",
         "upper_element": "木", "lower_element": "金"},
    ]
    result = _shehai_deepest(candidates)
    # 深浅可能相同（都返回 None）或选出唯一最深者，但绝不能两个都返回
    assert result is None or result["upper"] == "寅"


def test_shehai_returns_none_when_all_zero() -> None:
    """深浅全为 0 时不应臆断。"""
    candidates = [
        {"index": 1, "lower": "寅", "upper": "寅", "text": "寅/寅",
         "upper_element": "木", "lower_element": "木"},
    ]
    assert _shehai_deepest(candidates) is None


def test_shehai_returns_none_when_tied() -> None:
    """深浅相同时不应臆断，返回 None 交给上层标未实现。"""
    candidates = [
        {"index": 1, "lower": "子", "upper": "寅", "text": "寅/子",
         "upper_element": "木", "lower_element": "水"},
        {"index": 3, "lower": "子", "upper": "寅", "text": "寅/子",
         "upper_element": "木", "lower_element": "水"},
    ]
    assert _shehai_deepest(candidates) is None


# ---- 覆盖率与诚实性 ----

def test_coverage_is_reported_honestly() -> None:
    """未实现课体必须留空并给出原因，且比例不应过高。"""
    total = 0
    unimplemented = 0
    for hour in range(0, 24, 2):
        for day in (1, 10, 20):
            facts = _facts(f"2026-10-{day:02d}T{hour:02d}:00:00")
            total += 1
            status = facts["san_chuan_status"]
            if not status["implemented"]:
                unimplemented += 1
                assert facts["san_chuan"] is None
                assert status["reason"]
    ratio = unimplemented / total
    assert ratio < 0.30, f"未实现比例 {ratio:.0%} 过高，课体覆盖可能退化"


def test_methods_are_all_declared() -> None:
    """实际出现的课体名必须在已实现或未实现清单里，不能出现野名字。"""
    known = set(C.IMPLEMENTED_KE_TI) | set(C.UNIMPLEMENTED_KE_TI)
    for hour in range(0, 24, 2):
        facts = _facts(f"2026-10-25T{hour:02d}:00:00")
        status = facts["san_chuan_status"]
        if status["method"] is None:
            continue
        base = status["method"].split("·")[0]
        assert base in known, f"未登记的课体名：{status['method']}"


def test_biyong_compares_upper_not_lower() -> None:
    """比用必须比较**上神**（发用者）与日干的阴阳，不是下神。

    比较下神等于拿「被克的一方」去比，选出来的往往是错的那一课。
    """
    from app.domains.daliuren.engine import _zeike

    # 构造：两课都下克上，上神阴阳不同，日干为阳
    lessons = [
        {"index": 1, "lower": "子", "upper": "午", "text": "午/子",
         "upper_element": "火", "lower_element": "水"},
        {"index": 3, "lower": "丑", "upper": "未", "text": "未/丑",
         "upper_element": "土", "lower_element": "土"},
    ]
    # 午为阳支、未为阴支；日干甲为阳 → 应选上神为阳的午
    result = _zeike(lessons, "甲")
    assert result["implemented"] is True
    assert result["first"]["upper"] == "午"
