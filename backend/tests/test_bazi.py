"""四柱引擎测试：fixture 驱动（24 例）+ 口径行为断言。

fixture 见 `tests/fixtures/bazi_cases.json`，每例记录输入、期望四柱与期望来源：
- `source=lunar-python`：已与独立实现（lunar-python 1.4.8, MIT）交叉核验；
- `source=self_baseline`：非 Asia/Shanghai 时区，lunar-python 无法作为第二来源，
  暂作回归基线，见 `docs/测试基准说明.md`。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from app.core.config import settings
from app.domains.bazi.constants import HIDDEN_STEMS
from app.domains.bazi.engine import calculate
from app.domains.bazi.schemas import BaziInput, ChartResult, Convention

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "bazi_cases.json"
PAYLOAD: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
CASES: list[dict[str, Any]] = PAYLOAD["cases"]
POSITIONS = ("year", "month", "day", "hour")


def _run(case: dict[str, Any]) -> ChartResult:
    raw = case["input"]
    inp = BaziInput(
        birth_datetime=datetime.fromisoformat(raw["birth_datetime"]),
        timezone=raw["timezone"],
        gender=raw["gender"],
        time_known=raw["time_known"],
        longitude=raw["longitude"],
    )
    return calculate(inp, Convention(**raw["convention"]))


def test_fixture_has_enough_cases() -> None:
    # 计划门槛：基准与边界用例合计 ≥ 20 例
    assert len(CASES) >= 20
    ids = [case["id"] for case in CASES]
    assert len(ids) == len(set(ids))
    for case in CASES:
        assert case["source"] in {"lunar-python", "self_baseline"}


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_pillars_match_fixture(case: dict[str, Any]) -> None:
    result = _run(case)
    actual = [result.chart_facts["pillars"][key]["text"] for key in POSITIONS]
    assert actual == case["expected_pillars"], f"{case['id']}：{case['note']}"


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_chart_result_shape(case: dict[str, Any]) -> None:
    result = _run(case)
    facts = result.chart_facts

    assert result.domain == "bazi"
    assert result.algorithm_version == settings.bazi_algorithm_version
    assert list(facts["pillars"]) == list(POSITIONS)

    for position in POSITIONS:
        pillar = facts["pillars"][position]
        assert len(pillar["stem"]) == 1 and len(pillar["branch"]) == 1
        assert pillar["text"] == pillar["stem"] + pillar["branch"]
        # 藏干必须与藏干表一致，且权重按 weight-v1 口径
        expected_hidden = [stem for stem, _level in HIDDEN_STEMS[pillar["branch"]]]
        assert [item["stem"] for item in pillar["hidden_stems"]] == expected_hidden
        for item in pillar["hidden_stems"]:
            assert item["weight"] == {"本气": 1.0, "中气": 0.5, "余气": 0.3}[item["level"]]

    # 日主即日干，十神四位齐全且日位标为「日主」
    assert facts["day_master"]["stem"] == facts["pillars"]["day"]["stem"]
    assert facts["ten_gods"]["day"] == "日主"
    assert set(facts["ten_gods"]) == set(POSITIONS)
    assert all(value for value in facts["ten_gods"].values())

    # 五行统计：天干 4 + 地支 4 = 8 个计数，加权总和应大于原始计数
    raw = facts["five_elements_count"]["raw"]
    weighted = facts["five_elements_count"]["weighted"]
    assert sum(raw.values()) == 8
    assert sum(weighted.values()) > 8
    assert facts["five_elements_count"]["weight_rule"] == "weight-v1"

    # 节气上下文必须完整回显，且时间顺序正确
    assert facts["jieqi"]["prev"]["name"] and facts["jieqi"]["next"]["name"]
    assert facts["jieqi"]["minutes_to_prev"] >= 0
    assert facts["jieqi"]["minutes_to_next"] >= 0

    # 关系结果与 triggered_rules 是同一份数据
    assert facts["relations"]["count"] == len(result.triggered_rules)


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_rules_are_cited_and_neutral(case: dict[str, Any]) -> None:
    result = _run(case)
    for rule in result.triggered_rules:
        assert rule["rule_id"].startswith("rel.")
        assert rule["source_ref"]
        assert rule["version"]
        assert set(rule["positions"]) <= set(POSITIONS)
        # 硬要求：关系引擎不得输出吉凶结论
        for field in ("relation", "note", "topic"):
            assert not set(rule[field]) & set("吉凶灾祸福")


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_convention_is_echoed(case: dict[str, Any]) -> None:
    result = _run(case)
    expected = Convention(**case["input"]["convention"])
    for key, value in expected.model_dump().items():
        assert result.convention[key] == value
    assert result.convention["day_boundary_note"]


def test_unknown_time_marks_hour_uncertain() -> None:
    case = next(item for item in CASES if not item["input"]["time_known"])
    result = _run(case)
    facts = result.chart_facts
    # 时辰不详按 12:00 占位，但必须标记不确定并给出警告
    assert facts["hour_confidence"] == "unknown"
    assert facts["pillars"]["hour"]["uncertain"] is True
    assert facts["pillars"]["day"]["uncertain"] is False
    assert any("时辰未知" in warning for warning in result.warnings)


def test_day_boundary_policies_differ() -> None:
    base = BaziInput(birth_datetime=datetime(2016, 11, 30, 23, 30), gender="male")
    policy_a = calculate(base, Convention(day_boundary="zi_hour_policy_a"))
    policy_b = calculate(base, Convention(day_boundary="zi_hour_policy_b"))

    # 23:30 属于子时：policy_a 换日 ⇒ 日柱不同；policy_b 夜子时 ⇒ 日柱仍为当日
    assert policy_a.chart_facts["pillars"]["day"]["text"] != policy_b.chart_facts["pillars"]["day"]["text"]
    assert policy_a.chart_facts["pillars"]["day"]["text"] == "丁巳"
    assert policy_b.chart_facts["pillars"]["day"]["text"] == "丙辰"
    # 两种口径下时柱取的都是次日子干，结果相同
    assert policy_a.chart_facts["pillars"]["hour"]["text"] == policy_b.chart_facts["pillars"]["hour"]["text"]


def test_year_boundary_modes_differ() -> None:
    # 2024 立春交节 16:26:53；凌晨出生时 lichun 与 lichun_day 的年柱必然不同
    moment = datetime(2024, 2, 4, 0, 30)
    precise = calculate(BaziInput(birth_datetime=moment, gender="male"), Convention(year_boundary="lichun"))
    by_day = calculate(BaziInput(birth_datetime=moment, gender="male"), Convention(year_boundary="lichun_day"))

    assert precise.chart_facts["pillars"]["year"]["text"] == "癸卯"
    assert by_day.chart_facts["pillars"]["year"]["text"] == "甲辰"
    assert any("立春所在公历日" in warning for warning in by_day.warnings)


def test_true_solar_time_shifts_pillars() -> None:
    moment = datetime(1992, 5, 20, 8, 0)
    plain = calculate(BaziInput(birth_datetime=moment, gender="male", longitude=87.6))
    adjusted = calculate(
        BaziInput(birth_datetime=moment, gender="male", longitude=87.6),
        Convention(solar_time="true_solar_time"),
    )

    facts = adjusted.chart_facts["solar_time_adjust"]
    assert facts["applied"] is True
    assert facts["delta_minutes"] < -100  # 乌鲁木齐经度校正约 −2 小时
    assert any("真太阳时" in warning for warning in adjusted.warnings)
    assert plain.chart_facts["solar_time_adjust"]["applied"] is False
    # 校正后本地时刻约 6:00 出头，时支从辰变卯
    assert plain.chart_facts["pillars"]["hour"]["branch"] == "辰"
    assert adjusted.chart_facts["pillars"]["hour"]["branch"] == "卯"


def test_true_solar_time_without_longitude_is_flagged() -> None:
    result = calculate(
        BaziInput(birth_datetime=datetime(1992, 5, 20, 8, 0), gender="male"),
        Convention(solar_time="true_solar_time"),
    )
    assert result.chart_facts["solar_time_adjust"]["applied"] is False
    assert any("未提供出生地经度" in warning for warning in result.warnings)


def test_dayun_requires_gender() -> None:
    unknown = calculate(BaziInput(birth_datetime=datetime(1990, 6, 15, 9, 10), gender="unknown"))
    assert unknown.chart_facts["dayun"]["computed"] is False
    assert unknown.chart_facts["dayun"]["reason"]

    male = calculate(BaziInput(birth_datetime=datetime(1990, 6, 15, 9, 10), gender="male"))
    dayun = male.chart_facts["dayun"]
    assert dayun["computed"] is True
    assert dayun["error_bound"]
    assert len(dayun["list"]) >= 8
    ages = [item["start_age_years"] for item in dayun["list"]]
    assert ages == sorted(ages)
    for item in dayun["list"]:
        assert item["end_age_years"] > item["start_age_years"]


def test_dayun_direction_by_polarity() -> None:
    # 1984 甲子年（阳年）：男顺排、女逆排
    male = calculate(BaziInput(birth_datetime=datetime(1984, 6, 1, 10, 0), gender="male"))
    female = calculate(BaziInput(birth_datetime=datetime(1984, 6, 1, 10, 0), gender="female"))
    assert male.chart_facts["dayun"]["forward"] is True
    assert female.chart_facts["dayun"]["forward"] is False
    # 顺排第一步即月柱的下一柱，逆排为上一柱
    month = male.chart_facts["pillars"]["month"]["text"]
    assert male.chart_facts["dayun"]["list"][0]["pillar"] != month
    assert female.chart_facts["dayun"]["list"][0]["pillar"] != month


def test_boundary_warning_near_jieqi() -> None:
    # 2023 惊蛰交节 04:36，04:30 出生应触发临界告警
    result = calculate(BaziInput(birth_datetime=datetime(2023, 3, 6, 4, 30), gender="female"))
    assert any("紧邻节气" in warning for warning in result.warnings)


def test_source_refs_include_term_source() -> None:
    result = calculate(BaziInput(birth_datetime=datetime(2020, 1, 1, 12, 0), gender="male"))
    term_refs = [item for item in result.source_refs if item["type"] == "term_source"]
    assert len(term_refs) == 1
    assert term_refs[0]["id"] == "lunar_python"


def test_input_summary_keeps_original_moment() -> None:
    # 真太阳时只影响「生效时刻」，原始输入必须原样回显，便于追溯
    result = calculate(
        BaziInput(birth_datetime=datetime(1992, 5, 20, 8, 0), gender="male", longitude=87.6),
        Convention(solar_time="true_solar_time"),
    )
    summary = result.input_summary
    assert summary["birth_datetime"].startswith("1992-05-20T08:00")
    assert summary["effective_datetime"].startswith("1992-05-20T05:")
    assert summary["longitude"] == 87.6


def test_timezone_must_be_valid() -> None:
    with pytest.raises(ValueError):
        calculate(BaziInput(birth_datetime=datetime(2020, 1, 1, 12, 0), timezone="Mars/Olympus"))
