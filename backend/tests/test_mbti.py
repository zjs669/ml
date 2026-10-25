"""MBTI 式问卷引擎测试。

期望值不取引擎输出：
- 题库结构用独立统计核对（每维题数、id 唯一、两极成对）；
- 计分用「构造全 A / 全 B / 指定平票」三种输入独立核对；
- 平票必须记 X，不能被强行归极。

不测「结果像不像某个人」—— 那是量表效度问题，不是代码正确性问题。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domains.mbti import items as K
from app.domains.mbti.engine import TIE_MARK, calculate
from app.domains.mbti.schemas import MbtiCalculateIn, MbtiInput


def _all(choice: str) -> dict[str, str]:
    return {item.id: choice for item in K.QUESTIONS}


def _run(answers: dict[str, str], **kwargs):
    inp = MbtiInput.model_validate({"answers": answers, **kwargs})
    return calculate(inp).chart_facts


# ---- 题库结构 ----

def test_bank_size_and_balance() -> None:
    assert len(K.QUESTIONS) == 40
    per_dim: dict[str, int] = {}
    for item in K.QUESTIONS:
        per_dim[item.dimension] = per_dim.get(item.dimension, 0) + 1
    assert set(per_dim) == {"EI", "SN", "TF", "JP"}
    assert all(count == 10 for count in per_dim.values())


def test_question_ids_unique() -> None:
    ids = [item.id for item in K.QUESTIONS]
    assert len(ids) == len(set(ids))


def test_each_question_has_opposite_poles() -> None:
    """每题的两极必须是该维度的两端，不能同极或跨维度。"""
    for item in K.QUESTIONS:
        pair = dict((dim, (a, b)) for dim, a, b in K.DIMENSIONS)[item.dimension]
        assert {item.pole_a, item.pole_b} == set(pair), item.id
        assert item.pole_a != item.pole_b, item.id


def test_every_question_has_text_and_options() -> None:
    for item in K.QUESTIONS:
        assert item.text.strip()
        assert item.option_a.strip() and item.option_b.strip()


def test_bank_version_declared() -> None:
    assert K.BANK_VERSION
    assert "self" in K.BANK_VERSION.lower()


def test_school_note_disclaims_official() -> None:
    assert "不是官方" in K.SCHOOL_NOTE or "不声称" in K.SCHOOL_NOTE


# ---- 计分 ----

def test_all_a_gives_first_poles() -> None:
    facts = _run(_all("A"))
    assert facts["code"] == "ESTJ"
    for dim in facts["dimensions"]:
        assert dim["tendency"] != TIE_MARK
        assert dim["strength"] == 10


def test_all_b_gives_second_poles() -> None:
    facts = _run(_all("B"))
    assert facts["code"] == "INFP"
    for dim in facts["dimensions"]:
        assert dim["strength"] == 10


def test_tie_recorded_as_x() -> None:
    """每维 5:5 平票必须记为 X，不能强行归极。"""
    answers: dict[str, str] = {}
    counters: dict[str, int] = {}
    for item in K.QUESTIONS:
        index = counters.get(item.dimension, 0)
        answers[item.id] = "A" if index % 2 == 0 else "B"
        counters[item.dimension] = index + 1
    facts = _run(answers)
    assert facts["code"] == "XXXX"
    assert set(facts["undifferentiated"]) == {"EI", "SN", "TF", "JP"}
    for dim in facts["dimensions"]:
        assert dim["strength"] == 0
        assert dim["tendency"] == TIE_MARK


def test_partial_tie() -> None:
    """只让 EI 平票，其余全 A → 代码应为 XSTJ。"""
    answers = _all("A")
    ei_ids = [item.id for item in K.QUESTIONS if item.dimension == "EI"]
    for index, qid in enumerate(ei_ids):
        answers[qid] = "A" if index % 2 == 0 else "B"
    facts = _run(answers)
    assert facts["code"] == "XSTJ"
    assert facts["undifferentiated"] == ["EI"]


def test_counts_sum_to_question_count() -> None:
    facts = _run(_all("A"))
    for dim in facts["dimensions"]:
        assert dim["total"] == 10
        assert sum(pole["count"] for pole in dim["poles"].values()) == 10


def test_strength_is_absolute_difference() -> None:
    answers = _all("A")
    sn_ids = [item.id for item in K.QUESTIONS if item.dimension == "SN"]
    answers[sn_ids[0]] = "B"
    answers[sn_ids[1]] = "B"
    facts = _run(answers)
    sn = next(dim for dim in facts["dimensions"] if dim["dimension"] == "SN")
    assert sn["strength"] == 6  # 8 : 2
    assert sn["tendency"] == "S"


# ---- 作答明细 ----

def test_answers_recorded_by_default() -> None:
    facts = _run(_all("A"))
    assert "answers" in facts
    assert len(facts["answers"]) == 40
    assert facts["answers_recorded"] is True


def test_answers_dropped_when_disabled() -> None:
    facts = _run(_all("A"), store_answers=False)
    assert "answers" not in facts
    assert facts["answers_recorded"] is False


def test_answer_detail_matches_input() -> None:
    answers = _all("A")
    answers[K.QUESTIONS[0].id] = "B"
    facts = _run(answers)
    detail = next(item for item in facts["answers"] if item["id"] == K.QUESTIONS[0].id)
    assert detail["choice"] == "B"
    assert detail["pole"] == K.QUESTIONS[0].pole_b


# ---- 契约 ----

def test_rejects_missing_answers() -> None:
    answers = _all("A")
    answers.pop(K.QUESTIONS[0].id)
    with pytest.raises(ValidationError):
        MbtiInput.model_validate({"answers": answers})


def test_rejects_unknown_question() -> None:
    answers = _all("A")
    answers["no-such-id"] = "A"
    with pytest.raises(ValidationError):
        MbtiInput.model_validate({"answers": answers})


def test_rejects_invalid_choice() -> None:
    answers = _all("A")
    answers[K.QUESTIONS[0].id] = "C"
    with pytest.raises(ValidationError):
        MbtiInput.model_validate({"answers": answers})


def test_accepts_lowercase_choice() -> None:
    answers = {qid: choice.lower() for qid, choice in _all("A").items()}
    facts = _run(answers)
    assert facts["code"] == "ESTJ"


def test_rejects_unknown_school() -> None:
    with pytest.raises(ValidationError):
        MbtiCalculateIn.model_validate(
            {"answers": _all("A"), "convention": {"school": "official_mbti_v1"}}
        )


def test_warns_on_tie() -> None:
    answers: dict[str, str] = {}
    counters: dict[str, int] = {}
    for item in K.QUESTIONS:
        index = counters.get(item.dimension, 0)
        answers[item.id] = "A" if index % 2 == 0 else "B"
        counters[item.dimension] = index + 1
    inp = MbtiInput.model_validate({"answers": answers})
    result = calculate(inp)
    assert any("平票" in item for item in result.warnings)


def test_no_personality_claim_in_warnings() -> None:
    """红线：警告里不许出现人格断言。"""
    inp = MbtiInput.model_validate({"answers": _all("A")})
    result = calculate(inp)
    banned = ("你是", "你的性格", "适合从事", "建议选择")
    for item in result.warnings:
        for word in banned:
            assert word not in item, f"警告出现人格断言「{word}」：{item}"


def test_triggered_rules_empty() -> None:
    inp = MbtiInput.model_validate({"answers": _all("A")})
    assert calculate(inp).triggered_rules == []
