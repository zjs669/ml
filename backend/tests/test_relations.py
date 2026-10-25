"""关系引擎规则表驱动测试。

每条规则（当前 48 条）至少覆盖：正例、反例、边界（三合/三会/三刑缺一、自刑单支不成立）。
另有整体性断言：排序、冲突提示、纯函数性、不输出吉凶。
"""

from __future__ import annotations

from typing import Any, Iterator

import pytest

from app.domains.calendar_core.jiazi import BRANCHES, STEMS
from app.domains.relations.engine import (
    RelationRule,
    attach_to_chart,
    detect_relations,
    load_rules,
)

RULE_VERSION, RULES = load_rules()
POSITIONS = ("year", "month", "day", "hour")
DEFAULT_STEMS = ("甲", "丙", "戊", "庚")
DEFAULT_BRANCHES = ("子", "丑", "寅", "卯")


def _pillars(stems: tuple[str, ...], branches: tuple[str, ...]) -> dict[str, dict[str, str]]:
    return {
        position: {"stem": stems[i], "branch": branches[i]} for i, position in enumerate(POSITIONS)
    }


def _branch_chart(*branches: str) -> dict[str, dict[str, str]]:
    """直接指定地支（不足四位时用固定地支补齐）。"""
    filled = list(branches) + [b for b in DEFAULT_BRANCHES if b not in branches]
    return _pillars(DEFAULT_STEMS, tuple(filled[:4]))


def _stem_chart(*stems: str) -> dict[str, dict[str, str]]:
    filled = list(stems) + [s for s in DEFAULT_STEMS if s not in stems]
    return _pillars(tuple(filled[:4]), DEFAULT_BRANCHES)


def _chart_for(rule: RelationRule, members: tuple[str, ...]) -> dict[str, dict[str, str]]:
    """把规则成员放入靠前的柱位，其余柱位用「不属于本规则」的字填充。

    填充池必须排除规则成员，否则补齐时会把成员又塞回盘面，造成假阳性。
    """
    pool = STEMS if rule.scope == "stem" else BRANCHES
    filler = [item for item in pool if item not in rule.members]
    slots = list(members) + filler[: max(0, 4 - len(members))]
    if rule.scope == "stem":
        return _pillars(tuple(slots[:4]), DEFAULT_BRANCHES)
    return _pillars(DEFAULT_STEMS, tuple(slots[:4]))


def _triggered_ids(pillars: dict[str, dict[str, str]]) -> set[str]:
    return {item["rule_id"] for item in detect_relations(pillars)["rules"]}


def _incomplete_ids(pillars: dict[str, dict[str, str]]) -> set[str]:
    return {item["rule_id"] for item in detect_relations(pillars)["incomplete"]}


def _complements(rule: RelationRule) -> list[str]:
    pool = STEMS if rule.scope == "stem" else BRANCHES
    return [item for item in pool if item not in rule.members]


RULE_IDS = [rule.rule_id for rule in RULES]
BY_ID = {rule.rule_id: rule for rule in RULES}


def test_rule_table_integrity() -> None:
    assert len(RULES) >= 40
    assert RULE_VERSION
    assert len(RULE_IDS) == len(set(RULE_IDS))  # 引擎加载时已强制，这里再锁一次
    for rule in RULES:
        assert rule.rule_id.startswith("rel.")
        assert rule.source_ref.startswith("kb://"), rule.rule_id
        assert rule.version == RULE_VERSION
        assert rule.kind in {"pair", "triple", "self"}
        assert rule.scope in {"stem", "branch"}
        # 硬要求：规则文本不得包含任何吉凶判断
        assert not set(rule.relation + rule.topic + rule.note) & set("吉凶灾祸福")


@pytest.mark.parametrize("rule_id", RULE_IDS)
def test_rule_positive(rule_id: str) -> None:
    rule = BY_ID[rule_id]
    if rule.kind == "self":
        pillars = _chart_for(rule, (rule.members[0], rule.members[0]))
    else:
        pillars = _chart_for(rule, rule.members)

    result = detect_relations(pillars)
    hit = [item for item in result["rules"] if item["rule_id"] == rule_id]
    assert hit, f"{rule_id} 正例未触发"
    payload = hit[0]
    assert payload["relation"] == rule.relation
    assert payload["positions"]
    assert set(payload["positions"]) <= set(POSITIONS)
    assert payload["label"]


@pytest.mark.parametrize("rule_id", RULE_IDS)
def test_rule_negative(rule_id: str) -> None:
    rule = BY_ID[rule_id]
    other = _complements(rule)[0]
    # 规则成员一个都不出现（自刑则只出现一次且是别的支）
    pillars = _chart_for(rule, (other,)) if rule.kind != "self" else _chart_for(rule, (other, other))
    assert rule_id not in _triggered_ids(pillars)
    assert rule_id not in _incomplete_ids(pillars)


@pytest.mark.parametrize("rule_id", RULE_IDS)
def test_rule_never_triggers_on_duplicate_of_other_member(rule_id: str) -> None:
    """同一地支出现两次不应凑出「跨位组合」，除自刑规则外。"""
    rule = BY_ID[rule_id]
    if rule.kind == "self":
        pytest.skip("自刑本身依赖同支两现")
    pillars = _chart_for(rule, (rule.members[0], rule.members[0]))
    assert rule_id not in _triggered_ids(pillars)


TRIPLE_IDS = [rule.rule_id for rule in RULES if rule.kind == "triple"]


@pytest.mark.parametrize("rule_id", TRIPLE_IDS)
def test_triple_incomplete_is_reported(rule_id: str) -> None:
    """三合/三会/三刑缺一：只进 incomplete，不进 triggered。"""
    rule = BY_ID[rule_id]
    pillars = _chart_for(rule, (rule.members[0], rule.members[1]))
    result = detect_relations(pillars)

    assert rule_id not in {item["rule_id"] for item in result["rules"]}
    incomplete = [item for item in result["incomplete"] if item["rule_id"] == rule_id]
    assert incomplete, f"{rule_id} 缺一未提示"
    assert set(incomplete[0]["members_present"]) == set(rule.members[:2])
    assert "缺一" in incomplete[0]["note"]


@pytest.mark.parametrize("rule_id", TRIPLE_IDS)
def test_triple_full_matches_once(rule_id: str) -> None:
    rule = BY_ID[rule_id]
    pillars = _chart_for(rule, rule.members)
    hits = [item for item in detect_relations(pillars)["rules"] if item["rule_id"] == rule_id]
    assert len(hits) == 1
    assert set(hits[0]["positions"]) == {"year", "month", "day"}


def test_pair_is_order_independent() -> None:
    rule = BY_ID["rel.branch.liuhe.zi_chou"]
    forward = _triggered_ids(_chart_for(rule, ("子", "丑")))
    backward = _triggered_ids(_chart_for(rule, ("丑", "子")))
    assert rule.rule_id in forward and rule.rule_id in backward


def test_triggered_rules_are_sorted_by_priority() -> None:
    pillars = _branch_chart("申", "子", "辰", "午")
    rules = detect_relations(pillars)["rules"]
    assert len(rules) > 1
    keys = [(-item["priority"], item["rule_id"]) for item in rules]
    assert keys == sorted(keys)


def test_conflict_detected_between_he_and_chong() -> None:
    # 年日两柱：天干甲庚相冲（同属年日两柱），地支子丑六合 → 合克并见
    pillars = _pillars(("甲", "丙", "庚", "戊"), ("子", "寅", "丑", "卯"))
    result = detect_relations(pillars)
    rule_ids = {item["rule_id"] for item in result["rules"]}
    assert {"rel.branch.liuhe.zi_chou", "rel.stem.xiangchong.jia_geng"} <= rule_ids

    conflicts = result["conflicts"]
    assert conflicts, "合克并见未被识别"
    pair = next(item for item in conflicts if set(item["positions"]) == {"year", "day"})
    assert pair["type"] == "合克并见"
    assert "rel.branch.liuhe.zi_chou" in pair["rule_ids"]
    assert "rel.stem.xiangchong.jia_geng" in pair["rule_ids"]


def test_duplicated_branch_is_reported() -> None:
    pillars = _pillars(DEFAULT_STEMS, ("辰", "午", "辰", "酉"))
    result = detect_relations(pillars)
    zixing = [item for item in result["rules"] if item["rule_id"] == "rel.branch.zixing.chen"]
    assert zixing, "辰见辰应触发自刑"
    assert zixing[0]["duplicated_branches"]["辰"] == ["year", "day"]


def test_summary_matches_rules() -> None:
    result = detect_relations(_branch_chart("申", "子", "辰", "午"))
    counted: dict[str, int] = {}
    for item in result["rules"]:
        counted[item["relation"]] = counted.get(item["relation"], 0) + 1
    assert result["summary"] == counted
    assert result["count"] == len(result["rules"])


def test_empty_pillars_are_safe() -> None:
    result = detect_relations({})
    assert result["rules"] == []
    assert result["count"] == 0


def test_detect_relations_is_pure() -> None:
    pillars = _branch_chart("申", "子", "辰", "午")
    snapshot = {position: dict(values) for position, values in pillars.items()}
    first = detect_relations(pillars)
    second = detect_relations(pillars)
    assert first == second
    assert pillars == snapshot  # 输入未被修改


def test_attach_to_chart_mutates_chart_facts() -> None:
    pillars = _branch_chart("申", "子", "辰", "午")
    facts: dict[str, Any] = {"pillars": pillars}
    analysis = attach_to_chart(facts)
    assert facts["relations"] is analysis
    assert analysis["count"] == len(analysis["rules"])


def test_relation_payload_has_no_verdict() -> None:
    for rule in RULES:
        for item in detect_relations(_chart_for(rule, rule.members))["rules"]:
            text = "".join(str(item[field]) for field in ("relation", "topic", "note", "label"))
            assert not set(text) & set("吉凶灾祸福")


def _iter_all_rule_charts() -> Iterator[dict[str, dict[str, str]]]:  # pragma: no cover - 便于手工排查
    for rule in RULES:
        yield _chart_for(rule, rule.members)
