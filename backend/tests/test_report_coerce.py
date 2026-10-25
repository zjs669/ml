"""模型输出整形层的行为约定。

整形只允许修「信封结构」，不允许修事实、不允许补引用：
- 自造顶层键要丢掉（否则 extra=forbid 直接判死）；
- observations 用 `facts: [str]` 要折成 `fact`；
- `uncertainties` 写成对象数组要摊平成字符串；
- 空壳输出必须仍然判死（不能因为补了默认 summary 就变成「合格的空报告」）；
- 引用了未提供的 chunk_id 时，只删掉该引用/该条解释，不伪造出处。
"""

from __future__ import annotations

from app.domains.reporting.coerce import dropped_keys, normalize_payload


def test_drops_self_invented_top_level_keys() -> None:
    payload = {
        "skill": "bazi.relations.v1",
        "scope": "只谈刑冲合害",
        "chart_basis": {"four_pillars": "庚午/壬午/辛亥/癸巳"},
        "summary": "总览",
        "observations": [{"fact": "年柱庚午", "rule_ids": [], "citation_ids": []}],
        "traditional_interpretations": [],
        "practical_reflections": [],
        "uncertainties": [],
        "citations": [],
        "safety_note": "仅供研习。",
    }
    normalized = normalize_payload(payload)
    assert set(normalized) == {
        "summary",
        "observations",
        "traditional_interpretations",
        "practical_reflections",
        "uncertainties",
        "citations",
        "safety_note",
    }
    assert dropped_keys(payload) == ["chart_basis", "scope", "skill"]


def test_observation_folds_facts_array_and_strips_unknown_fields() -> None:
    payload = {
        "summary": "总览",
        "observations": [
            {
                "group": "年支-月支",
                "relation": "自刑",
                "facts": ["年支与月支同为一地支", "两支所藏人元一致"],
                "rule_ids": ["rel.branch.zixing.wu"],
                "citation_ids": [],
                "statement_type": "结构事实陈述",
            }
        ],
    }
    normalized = normalize_payload(payload)
    observation = normalized["observations"][0]
    assert set(observation) == {"fact", "rule_ids", "citation_ids"}
    assert observation["fact"].startswith("年支与月支同为一地支")
    assert observation["rule_ids"] == ["rel.branch.zixing.wu"]


def test_object_arrays_are_flattened_to_strings() -> None:
    payload = {
        "summary": "总览",
        "observations": [{"fact": "年柱庚午"}],
        "practical_reflections": [{"text": "记录一周内的实际变化"}],
        "uncertainties": [{"note": "换日口径会影响结果"}, "第二项"],
        "citations": ["12", 13, True, "abc"],
        "safety_note": "仅供研习。",
    }
    normalized = normalize_payload(payload)
    assert normalized["practical_reflections"] == ["记录一周内的实际变化"]
    assert normalized["uncertainties"] == ["换日口径会影响结果", "第二项"]
    # 字符串数字可接受，布尔与非数字被丢弃
    assert normalized["citations"] == [12, 13]


def test_empty_shell_still_rejected() -> None:
    # 补默认 summary 会让「什么都没写」变成表面合格，这里必须返回空字典让校验层拒绝
    assert normalize_payload({}) == {}
    assert normalize_payload({"skill": "x", "version": "1"}) == {}
    assert normalize_payload("not a dict") == {}


def test_unknown_chunk_ids_are_removed() -> None:
    payload = {
        "summary": "总览",
        "observations": [{"fact": "年柱庚午", "citation_ids": [999, 12]}],
        "traditional_interpretations": [
            {"claim": "有真实引用", "citation_ids": [12]},
            {"claim": "引用不存在", "citation_ids": [999]},
        ],
        "citations": [999, 12],
        "safety_note": "仅供研习。",
    }
    normalized = normalize_payload(payload, allowed_chunk_ids={12})
    assert normalized["observations"][0]["citation_ids"] == [12]
    assert [item["claim"] for item in normalized["traditional_interpretations"]] == ["有真实引用"]
    assert normalized["citations"] == [12]


def test_untriggered_rule_observations_are_dropped() -> None:
    payload = {
        "summary": "总览",
        "observations": [
            {"fact": "年柱庚午", "rule_ids": ["rel.branch.zixing.wu"]},
            # 盘面只触发了自刑，这条却宣称三会 → 文字不可信，整条丢掉
            {"fact": "年支与月支构成三会", "rule_ids": ["rel.branch.sanhui.hai_zi_chou"]},
            {"fact": "日主为辛金"},
        ],
        "safety_note": "仅供研习。",
    }
    normalized = normalize_payload(payload, allowed_rule_ids={"rel.branch.zixing.wu"})
    facts = [item["fact"] for item in normalized["observations"]]
    assert facts == ["年柱庚午", "日主为辛金"]
    assert normalized["observations"][0]["rule_ids"] == ["rel.branch.zixing.wu"]


def test_all_observations_dropped_returns_empty() -> None:
    payload = {
        "summary": "总览",
        "observations": [{"fact": "岁运并临", "rule_ids": ["rel.branch.fake"]}],
    }
    assert normalize_payload(payload, allowed_rule_ids=set()) == {}


def test_all_interpretations_dropped_when_no_valid_citation() -> None:
    payload = {
        "summary": "总览",
        "observations": [{"fact": "年柱庚午"}],
        "traditional_interpretations": [{"claim": "无依据的解释", "citation_ids": [999]}],
        "safety_note": "仅供研习。",
    }
    normalized = normalize_payload(payload, allowed_chunk_ids={12})
    assert normalized["traditional_interpretations"] == []
    assert normalized["citations"] == []
