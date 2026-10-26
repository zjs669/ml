"""塔罗引擎测试。

期望值不取引擎输出：
- 牌池构成（22 / 56 / 78）用独立计数核对；
- 无放回性质用「同一牌阵内 card_id 不重复」核对；
- 可复现性用「同 seed 两次结果完全一致、异 seed 不同」核对；
- 正逆位分布用大样本统计核对（不是断言某一张的具体正逆）。
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domains.tarot import schemas as K
from app.domains.tarot.engine import calculate
from app.domains.tarot.schemas import TarotCalculateIn, TarotConvention, TarotInput

FIXTURES = Path(__file__).parent / "fixtures" / "tarot_cases.json"
DATA = json.loads(FIXTURES.read_text(encoding="utf-8"))


def _draw(**kwargs):
    inp = TarotInput.model_validate({"seed": "test-seed", **kwargs})
    return calculate(inp).chart_facts


# ---- 牌池结构 ----

def test_deck_composition() -> None:
    """78 = 22 大阿卡纳 + 56 小阿卡纳（4 花色 × 14 张）。"""
    assert len(K.MAJOR) == 22
    assert len(K.MINOR) == 56
    assert len(K.ALL_CARDS) == 78


def test_major_arcana_numbering() -> None:
    """大阿卡纳编号必须是 0–21 连续无重复。"""
    numbers = [card["number"] for card in K.MAJOR]
    assert numbers == list(range(22))


def test_minor_suits_and_ranks() -> None:
    """每个花色 14 张：1–10 加 4 张宫廷牌。"""
    per_suit: Counter[str] = Counter(card["suit"] for card in K.MINOR)
    assert set(per_suit) == {"wands", "cups", "swords", "pentacles"}
    assert all(count == 14 for count in per_suit.values())
    for suit in per_suit:
        court = [c for c in K.MINOR if c["suit"] == suit and c["number"] is None]
        assert len(court) == 4


def test_card_ids_unique() -> None:
    ids = [card["id"] for card in K.ALL_CARDS]
    assert len(ids) == len(set(ids)) == 78


def test_every_card_has_both_orientations() -> None:
    for card in K.ALL_CARDS:
        assert card["upright"], f"{card['id']} 缺正位关键词"
        assert card["reversed"], f"{card['id']} 缺逆位关键词"
        assert card["upright"] != card["reversed"]


def test_spreads_are_well_formed() -> None:
    assert "celtic" in K.SPREADS
    for spread_id, meta in K.SPREADS.items():
        positions = meta["positions"]
        assert positions, f"{spread_id} 缺位置"
        assert len(set(positions)) == len(positions), f"{spread_id} 位置名重复"
        assert len(positions) <= 12


# ---- 抽牌行为 ----

def test_no_replacement_within_spread() -> None:
    """无放回：凯尔特十字 10 张不得出现重复牌。"""
    facts = _draw(spread="celtic")
    ids = [card["card_id"] for card in facts["cards"]]
    assert len(ids) == 10
    assert len(set(ids)) == 10


def test_same_seed_reproducible() -> None:
    """同 seed 两次抽牌必须完全一致（含正逆位）。"""
    first = _draw(spread="three")
    second = _draw(spread="three")
    assert first["cards"] == second["cards"]
    assert first["draw"]["seed"] == second["draw"]["seed"]


def test_different_seed_differs() -> None:
    """异 seed 应产生不同牌序（抽样 20 次，至少有一次不同）。"""
    base = calculate(TarotInput.model_validate({"spread": "three", "seed": "a"})).chart_facts
    differs = False
    for index in range(20):
        other = calculate(
            TarotInput.model_validate({"spread": "three", "seed": f"b{index}"})
        ).chart_facts
        if [c["card_id"] for c in other["cards"]] != [c["card_id"] for c in base["cards"]]:
            differs = True
            break
    assert differs


def test_auto_seed_is_reported() -> None:
    """未给 seed 时必须回显派生值，否则用户无法复现。"""
    inp = TarotInput.model_validate({"spread": "single"})
    result = calculate(inp)
    seed = result.chart_facts["draw"]["seed"]
    assert seed.startswith("auto-")
    assert result.chart_facts["draw"]["auto_seed"] is True
    assert any("未提供 seed" in item for item in result.warnings)


def test_deck_modes_limit_pool() -> None:
    major = _draw(spread="three", deck="major")
    assert all(card["suit"] == "major" for card in major["cards"])
    assert major["deck"]["pool_size"] == 22

    minor = _draw(spread="three", deck="minor")
    assert all(card["suit"] != "major" for card in minor["cards"])
    assert minor["deck"]["pool_size"] == 56


def test_positions_bound_in_order() -> None:
    """抽牌结果按牌阵位置顺序绑定，位置名不得错位。"""
    facts = _draw(spread="three")
    expected = list(K.SPREADS["three"]["positions"])
    assert [card["position"] for card in facts["cards"]] == expected


def test_custom_positions_override_spread() -> None:
    facts = _draw(spread="three", custom_positions=["甲", "乙"])
    assert [card["position"] for card in facts["cards"]] == ["甲", "乙"]
    assert facts["spread"]["card_count"] == 2


def test_no_reversed_when_disabled() -> None:
    facts = _draw(spread="celtic", allow_reversed=False)
    assert all(card["orientation"] == "upright" for card in facts["cards"])


def test_reversed_probability_extremes() -> None:
    """概率 0 全正位、概率 1 全逆位。"""
    zero = _draw(spread="celtic", reversed_probability=0.0)
    assert all(card["orientation"] == "upright" for card in zero["cards"])
    one = _draw(spread="celtic", reversed_probability=1.0)
    assert all(card["orientation"] == "reversed" for card in one["cards"])


def test_reversed_distribution_is_plausible() -> None:
    """大样本下逆位比例应接近设定值（0.35 ± 0.15），确认随机源没有退化。"""
    reversed_count = 0
    total = 0
    for index in range(200):
        facts = calculate(
            TarotInput.model_validate(
                {"spread": "celtic", "seed": f"dist-{index}", "reversed_probability": 0.35}
            )
        ).chart_facts
        for card in facts["cards"]:
            total += 1
            if card["orientation"] == "reversed":
                reversed_count += 1
    ratio = reversed_count / total
    assert 0.20 <= ratio <= 0.50, f"逆位比例 {ratio:.3f} 偏离设定值 0.35 过多"


def test_question_dropped_when_not_stored() -> None:
    inp = TarotInput.model_validate(
        {"spread": "single", "question": "要不要换工作", "store_question": False}
    )
    result = calculate(inp)
    assert result.input_summary["question"] is None
    assert any("丢弃占问原文" in item for item in result.warnings)


# ---- 契约与红线 ----

def test_rejects_unknown_spread() -> None:
    with pytest.raises(ValidationError):
        TarotInput.model_validate({"spread": "no-such-spread"})


def test_rejects_too_many_positions() -> None:
    with pytest.raises(ValidationError):
        TarotInput.model_validate(
            {"spread": "three", "custom_positions": [f"p{i}" for i in range(13)]}
        )


def test_rejects_duplicate_positions() -> None:
    with pytest.raises(ValidationError):
        TarotInput.model_validate({"spread": "three", "custom_positions": ["甲", "甲"]})


def test_rejects_unknown_school() -> None:
    with pytest.raises(ValidationError):
        TarotConvention.model_validate({"school": "thoth_v1"})


def test_max_positions_fits_smallest_deck() -> None:
    """12 位上限必须放得进最小牌池（22 张），否则守卫会误伤合法牌阵。"""
    inp = TarotInput.model_validate(
        {"spread": "three", "deck": "major", "custom_positions": [f"p{i}" for i in range(12)]}
    )
    facts = calculate(inp).chart_facts
    assert facts["spread"]["card_count"] == 12
    assert len({c["card_id"] for c in facts["cards"]}) == 12


def test_triggered_rules_empty() -> None:
    assert calculate(TarotInput.model_validate({"spread": "single"})).triggered_rules == []


def test_warnings_have_no_prediction_wording() -> None:
    """红线：警告里不许出现预测式表述。"""
    inp = TarotInput.model_validate({"spread": "three"})
    result = calculate(inp)
    banned = ("预示", "一定会", "必然", "建议你", "注定")
    for item in result.warnings:
        for word in banned:
            assert word not in item, f"警告出现预测式表述「{word}」：{item}"


def test_fixture_cases() -> None:
    """固定用例：牌池与位置数符合预期。"""
    for case in DATA["cases"]:
        inp = TarotInput.model_validate(case["input"])
        facts = calculate(inp).chart_facts
        expect = case["expect"]
        assert facts["deck"]["pool_size"] == expect["pool_size"], case["case_id"]
        assert facts["spread"]["card_count"] == expect["card_count"], case["case_id"]
        assert len({c["card_id"] for c in facts["cards"]}) == expect["card_count"], case["case_id"]
