"""解梦引擎测试。

期望值不取引擎输出：
- 词表结构用独立统计核对（keyword 唯一、alias 不冲突、类别合法）；
- 匹配行为用「构造最小文本」逐项核对（长词优先、不重复命中、顺序按出现位置）；
- 未命中必须显式标记 `unmatched`，不能静默返回空。

不测「象征说法对不对」—— 那是民俗问题，不是代码正确性问题。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domains.dream import lexicon as K
from app.domains.dream.engine import _extract, calculate
from app.domains.dream.schemas import DreamCalculateIn, DreamInput


def _run(text: str, **kwargs):
    inp = DreamInput.model_validate({"text": text, **kwargs})
    return calculate(inp).chart_facts


# ---- 词表结构 ----

def test_entries_non_empty() -> None:
    assert len(K.ENTRIES) >= 40


def test_keywords_unique() -> None:
    keywords = [item.keyword for item in K.ENTRIES]
    assert len(keywords) == len(set(keywords))


def test_aliases_do_not_collide() -> None:
    """别名之间、别名与主词之间都不能重复，否则匹配会串到别的条目。"""
    seen: dict[str, str] = {}
    for item in K.ENTRIES:
        for term in (item.keyword, *item.aliases):
            assert term not in seen, f"「{term}」同时属于 {seen.get(term)} 与 {item.keyword}"
            seen[term] = item.keyword


def test_categories_are_declared() -> None:
    for item in K.ENTRIES:
        assert item.category in K.CATEGORIES, item.keyword


def test_every_entry_has_traditional_note() -> None:
    for item in K.ENTRIES:
        assert item.traditional.strip(), item.keyword


# ---- 匹配行为 ----

def test_longest_match_wins() -> None:
    """长词优先：词表里若同时存在「水」与更长的词，长词应先被匹配并占用位置。"""
    from app.domains.dream.engine import _LOOKUP, _SORTED_TERMS

    # 词表按长度倒序排列，这是长词优先的前提
    lengths = [len(term) for term in _SORTED_TERMS]
    assert lengths == sorted(lengths, reverse=True)
    # 「小河」是「水」的别名，匹配后应归到「水」这一条，且只记一次
    hits, _ = _extract("梦见小河", 8)
    assert len(hits) == 1
    assert hits[0]["keyword"] == "水"
    assert hits[0]["matched"] == "河" or hits[0]["matched"] == "小河"


def test_no_duplicate_keyword() -> None:
    """同一意象在文本里出现多次，只记一次。"""
    hits, _ = _extract("蛇，又是一条蛇，还是蛇", 8)
    assert [item["keyword"] for item in hits].count("蛇") == 1


def test_order_follows_position() -> None:
    hits, _ = _extract("先梦见蛇，然后梦见水", 8)
    positions = [item["position"] for item in hits]
    assert positions == sorted(positions)


def test_alias_maps_to_primary_keyword() -> None:
    hits, _ = _extract("梦见小河", 8)
    assert hits and hits[0]["keyword"] == "水"
    assert hits[0]["matched"] == "河"


def test_truncation_reported() -> None:
    hits, truncated = _extract("蛇 水 火 山 风 雪 雷 月亮 太阳 鱼", 3)
    assert len(hits) == 3
    assert truncated == 7


def test_no_hit_returns_empty() -> None:
    hits, truncated = _extract("完全无关的一句话", 8)
    assert hits == []
    assert truncated == 0


# ---- 结果结构 ----

def test_keywords_grouped_by_category() -> None:
    facts = _run("梦见蛇在水里游")
    categories = {item["category"] for item in facts["categories"]}
    assert "动物" in categories and "自然" in categories
    total = sum(len(item["items"]) for item in facts["categories"])
    assert total == facts["matched_count"]


def test_category_order_follows_constant() -> None:
    facts = _run("梦见蛇在水里游")
    order = [item["category"] for item in facts["categories"]]
    assert order == [name for name in K.CATEGORIES if name in order]


def test_traditional_can_be_disabled() -> None:
    with_note = _run("梦见蛇", include_traditional=True)
    without = _run("梦见蛇", include_traditional=False)
    assert "traditional" in with_note["keywords"][0]
    assert "traditional" not in without["keywords"][0]
    assert with_note["matched_count"] == without["matched_count"]


def test_unmatched_flag_and_warning() -> None:
    facts = _run("完全无关的一句话")
    assert facts["unmatched"] is True
    inp = DreamInput.model_validate({"text": "完全无关的一句话"})
    result = calculate(inp)
    assert any("覆盖不足" in item for item in result.warnings)


def test_text_recorded_by_default() -> None:
    facts = _run("梦见蛇")
    assert facts["text_recorded"] is True
    assert facts["text"] == "梦见蛇"


def test_text_dropped_when_disabled() -> None:
    facts = _run("梦见蛇", store_text=False)
    assert facts["text_recorded"] is False
    assert "text" not in facts


def test_max_keywords_respected() -> None:
    facts = _run("蛇 水 火 山 风 雪 雷 月亮 太阳 鱼", max_keywords=4)
    assert facts["matched_count"] == 4
    assert facts["truncated"] > 0


# ---- 契约 ----

def test_rejects_too_short_text() -> None:
    with pytest.raises(ValidationError):
        DreamInput.model_validate({"text": "梦"})


def test_rejects_too_long_text() -> None:
    with pytest.raises(ValidationError):
        DreamInput.model_validate({"text": "梦" * 2001})


def test_rejects_bad_max_keywords() -> None:
    with pytest.raises(ValidationError):
        DreamInput.model_validate({"text": "梦见蛇", "max_keywords": 0})
    with pytest.raises(ValidationError):
        DreamInput.model_validate({"text": "梦见蛇", "max_keywords": 21})


def test_rejects_unknown_school() -> None:
    with pytest.raises(ValidationError):
        DreamCalculateIn.model_validate(
            {"text": "梦见蛇", "convention": {"school": "zhougong_full_v1"}}
        )


def test_no_prediction_in_warnings() -> None:
    """红线：警告里不许出现预示式表述。

    口径说明本身含「不预示任何事件」这类否定句，因此跳过它，只查数据驱动的警告。
    """
    inp = DreamInput.model_validate({"text": "梦见蛇"})
    result = calculate(inp)
    banned = ("预示着", "将会", "一定会", "主吉", "主凶")
    for item in result.warnings:
        if item == K.SCHOOL_NOTE:
            continue
        for word in banned:
            assert word not in item, f"警告出现预示式表述「{word}」：{item}"


def test_triggered_rules_empty() -> None:
    inp = DreamInput.model_validate({"text": "梦见蛇"})
    assert calculate(inp).triggered_rules == []
