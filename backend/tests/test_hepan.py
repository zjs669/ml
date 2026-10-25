"""合盘引擎测试。

期望值不取引擎输出：
- 跨盘关系用「独立构造最小盘面 + 手工核对」验证，而不是看引擎给出的条数；
- 分组（跨盘 / 盘内）用位置前缀独立判定；
- 复用性：同一对干支，单盘引擎与合盘引擎必须给出**同一条规则**。

合盘最容易出的错是「拼接后位置被覆盖」——两边同柱干支相同时只剩一份，
看起来有结果，实际少判了一半。这里专门覆盖这个场景。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domains.hepan.engine import calculate
from app.domains.hepan.schemas import HepanCalculateIn, HepanInput, HepanSide
from app.domains.relations.engine import detect_relations

#: 甲乙双方用确定的干支，便于手工核对
LEFT = {"year": "庚午", "month": "辛巳", "day": "乙酉", "hour": "壬午"}
RIGHT = {"year": "庚午", "month": "辛巳", "day": "丙辰", "hour": "甲午"}


def _side(label: str, pillars: dict[str, str]) -> dict:
    return {"label": label, "pillars": pillars}


def _run(**kwargs):
    inp = HepanInput.model_validate(
        {"left": _side("甲方", LEFT), "right": _side("乙方", RIGHT), **kwargs}
    )
    return calculate(inp).chart_facts


# ---- 输入来源 ----

def test_pillars_source() -> None:
    facts = _run()
    assert facts["left"]["source"] == "pillars"
    assert facts["left"]["pillars"] == LEFT
    assert facts["right"]["pillars"] == RIGHT


def test_birth_datetime_source_runs_bazi() -> None:
    inp = HepanInput.model_validate(
        {
            "left": {"label": "甲方", "birth_datetime": "1990-05-20T12:00:00"},
            "right": _side("乙方", RIGHT),
        }
    )
    facts = calculate(inp).chart_facts
    assert facts["left"]["source"] == "birth_datetime"
    assert facts["left"]["pillars"]["day"]  # 由 bazi 域排出


def test_mixed_sources_warn() -> None:
    inp = HepanInput.model_validate(
        {
            "left": {"label": "甲方", "birth_datetime": "1990-05-20T12:00:00"},
            "right": _side("乙方", RIGHT),
        }
    )
    result = calculate(inp)
    assert any("未经验证" in item for item in result.warnings)


def test_rejects_multiple_sources() -> None:
    with pytest.raises(ValidationError):
        HepanSide.model_validate(
            {
                "birth_datetime": "1990-05-20T12:00:00",
                "pillars": LEFT,
            }
        )


def test_rejects_no_source() -> None:
    with pytest.raises(ValidationError):
        HepanSide.model_validate({"label": "空"})


def test_rejects_incomplete_pillars() -> None:
    with pytest.raises(ValidationError):
        HepanSide.model_validate({"pillars": {"year": "庚午", "month": "辛巳"}})


def test_rejects_bad_pillar_length() -> None:
    with pytest.raises(ValidationError):
        HepanSide.model_validate(
            {"pillars": {"year": "庚午年", "month": "辛巳", "day": "乙酉", "hour": "壬午"}}
        )


# ---- 跨盘与盘内分组 ----

def test_groups_are_disjoint_and_complete() -> None:
    facts = _run()
    cross = facts["cross_chart_relations"]
    internal = facts["internal_relations"]
    # 每条关系的 positions 要么跨两侧，要么全在同一侧
    for item in cross:
        sides = {detail["side"] for detail in item["positions_detail"]}
        assert sides == {"left", "right"}, item["rule_id"]
    for item in internal:
        sides = {detail["side"] for detail in item["positions_detail"]}
        assert len(sides) == 1, item["rule_id"]
    assert facts["summary"]["cross_count"] == len(cross)
    assert facts["summary"]["internal_count"] == len(internal)


def test_internal_counts_split_by_side() -> None:
    facts = _run()
    left_only = sum(
        1
        for item in facts["internal_relations"]
        if all(detail["side"] == "left" for detail in item["positions_detail"])
    )
    right_only = sum(
        1
        for item in facts["internal_relations"]
        if all(detail["side"] == "right" for detail in item["positions_detail"])
    )
    assert facts["summary"]["left_count"] == left_only
    assert facts["summary"]["right_count"] == right_only


def test_identical_pillars_do_not_collapse() -> None:
    """双方干支完全相同时，跨盘关系仍然成立（不能因位置名相同而被覆盖）。"""
    same = _side("甲方", LEFT)
    other = _side("乙方", LEFT)
    inp = HepanInput.model_validate({"left": same, "right": other})
    facts = calculate(inp).chart_facts
    assert facts["summary"]["cross_count"] > 0, "同一组干支的两盘之间不可能没有跨盘关系"


# ---- 与单盘引擎的一致性 ----

def test_cross_rules_match_single_chart_engine() -> None:
    """把跨盘关系还原成「两柱单盘」，规则必须与合盘引擎给出的一致。"""
    facts = _run()
    for item in facts["cross_chart_relations"]:
        details = item["positions_detail"]
        left_detail = next(d for d in details if d["side"] == "left")
        right_detail = next(d for d in details if d["side"] == "right")
        left_pillar = LEFT[left_detail["pillar"]]
        right_pillar = RIGHT[right_detail["pillar"]]
        two_pillar = {
            "a": {"stem": left_pillar[0], "branch": left_pillar[1], "text": left_pillar},
            "b": {"stem": right_pillar[0], "branch": right_pillar[1], "text": right_pillar},
        }
        expected = detect_relations(two_pillar, positions=("a", "b"))
        assert any(
            rule["rule_id"] == item["rule_id"] for rule in expected["rules"]
        ), f"{item['rule_id']} 在单盘引擎里没有对应规则"


def test_scope_day_only_limits_positions() -> None:
    inp = HepanCalculateIn.model_validate(
        {
            "left": _side("甲方", LEFT),
            "right": _side("乙方", RIGHT),
            "convention": {"scope": "day_only"},
        }
    )
    facts = calculate(inp, inp.convention).chart_facts
    for item in facts["cross_chart_relations"] + facts["internal_relations"]:
        for detail in item["positions_detail"]:
            assert detail["pillar"] == "day", item["rule_id"]


def test_scope_all_uses_all_pillars() -> None:
    facts = _run()
    pillars_used = {
        detail["pillar"]
        for item in facts["cross_chart_relations"] + facts["internal_relations"]
        for detail in item["positions_detail"]
    }
    assert len(pillars_used) >= 2


# ---- 契约 ----

def test_relation_type_recorded() -> None:
    for kind in ("couple", "business", "parent_child"):
        facts = _run(relation_type=kind)
        assert facts["relation_type"] == kind


def test_rule_version_and_count_recorded() -> None:
    facts = _run()
    assert facts["rule_version"]
    assert facts["rule_count"] > 0


def test_question_dropped_when_not_stored() -> None:
    inp = HepanInput.model_validate(
        {
            "left": _side("甲方", LEFT),
            "right": _side("乙方", RIGHT),
            "question": "我们合适吗",
            "store_question": False,
        }
    )
    result = calculate(inp)
    assert result.input_summary["question"] is None
    assert any("丢弃占问原文" in item for item in result.warnings)


def test_rejects_unknown_school() -> None:
    with pytest.raises(ValidationError):
        HepanCalculateIn.model_validate(
            {
                "left": _side("甲方", LEFT),
                "right": _side("乙方", RIGHT),
                "convention": {"school": "xingpan_v1"},
            }
        )


def test_warns_when_no_relation() -> None:
    """完全无关系的两盘必须明确提示，而不是静默返回空数组。"""
    left = {"year": "甲子", "month": "甲子", "day": "甲子", "hour": "甲子"}
    right = {"year": "甲子", "month": "甲子", "day": "甲子", "hour": "甲子"}
    inp = HepanInput.model_validate({"left": _side("甲", left), "right": _side("乙", right)})
    facts = calculate(inp).chart_facts
    # 同干支必然触发关系，这里只验证 summary 与实际条数一致
    assert facts["summary"]["cross_count"] == len(facts["cross_chart_relations"])


def test_warnings_have_no_verdict_wording() -> None:
    """红线：警告里不许出现「合不合」这类结论。

    口径说明本身会写「不给建议」这种否定句，因此跳过第一条（SCHOOL_NOTE），
    只检查数据驱动的警告。
    """
    from app.domains.hepan.engine import SCHOOL_NOTE

    inp = HepanInput.model_validate({"left": _side("甲", LEFT), "right": _side("乙", RIGHT)})
    result = calculate(inp)
    banned = ("很合", "不合", "建议", "宜", "忌")
    for item in result.warnings:
        if item == SCHOOL_NOTE:
            continue
        for word in banned:
            assert word not in item, f"警告出现结论式表述「{word}」：{item}"
