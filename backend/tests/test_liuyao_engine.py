"""六爻引擎测试：卦宫与世应由「变爻法」独立重建，纳甲按纳甲规则独立重算。

这两处是本术数最容易被写错、也最难靠肉眼看出来的数据，
因此期望值不取引擎输出，而是用另一套推导路径重建后再比对。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domains.calendar_core.jiazi import pillar_of_index, pillar_text
from app.domains.liuyao import constants as C
from app.domains.liuyao.engine import _coins, calculate
from app.domains.liuyao.hexagrams import (
    HEXAGRAM_TABLE,
    NAME_TO_INFO,
    PALACE_SEQUENCE,
    hexagram_from_bits,
)
from app.domains.liuyao.schemas import LiuyaoConvention, LiuyaoInput

FIXTURES = Path(__file__).parent / "fixtures" / "liuyao_cases.json"
DATA = json.loads(FIXTURES.read_text(encoding="utf-8"))
CONST = DATA["constants"]

#: 六十甲子六旬的空亡（《增删卜易》旬空表，独立于引擎公式）
XUN_KONG_TABLE = {
    "甲子": ("戌", "亥"),
    "甲戌": ("申", "酉"),
    "甲申": ("午", "未"),
    "甲午": ("辰", "巳"),
    "甲辰": ("寅", "卯"),
    "甲寅": ("子", "丑"),
}

#: 六神起例：甲乙青龙、丙丁朱雀、戊勾陈、己螣蛇、庚辛白虎、壬癸玄武
LIU_SHEN_HEAD = {"甲": "青龙", "乙": "青龙", "丙": "朱雀", "丁": "朱雀", "戊": "勾陈",
                 "己": "螣蛇", "庚": "白虎", "辛": "白虎", "壬": "玄武", "癸": "玄武"}

#: 纳甲起例：内卦天干、外卦天干、初爻地支起点、阳卦顺行（隔一位）
NAJIA_STEM_INNER = {"乾": "甲", "坤": "乙", "震": "庚", "巽": "辛", "坎": "戊", "离": "己", "艮": "丙", "兑": "丁"}
NAJIA_STEM_OUTER = {"乾": "壬", "坤": "癸", "震": "庚", "巽": "辛", "坎": "戊", "离": "己", "艮": "丙", "兑": "丁"}
NAJIA_BRANCH_START = {"乾": "子", "坤": "未", "震": "子", "巽": "丑", "坎": "寅", "离": "卯", "艮": "辰", "兑": "巳"}
YANG_TRIGRAMS = ("乾", "震", "坎", "艮")


def _flip(bits: str, positions: list[int]) -> str:
    chars = list(bits)
    for position in positions:
        index = position - 1
        chars[index] = "0" if chars[index] == "1" else "1"
    return "".join(chars)


def _input(**overrides) -> LiuyaoInput:
    body = {
        "method": "manual",
        "cast_datetime": datetime.fromisoformat(CONST["cast_datetime"]),
        "timezone": CONST["timezone"],
        "lines": [7, 7, 7, 7, 7, 7],
    }
    body.update(overrides)
    return LiuyaoInput(**body)


def test_hexagram_table_is_complete() -> None:
    names = [name for row in HEXAGRAM_TABLE.values() for name in row.values()]
    assert len(names) == 64
    assert len(set(names)) == 64
    assert set(HEXAGRAM_TABLE) == set(C.TRIGRAM_BITS)
    # 每卦的上下卦必须与卦名表本身一致（大写表是唯一真源）
    for upper, row in HEXAGRAM_TABLE.items():
        for lower, name in row.items():
            info = NAME_TO_INFO[name]
            assert (info.upper, info.lower) == (upper, lower)


def test_palace_sequence_matches_flip_rule() -> None:
    """按「逐爻变 → 游魂回四爻 → 归魂复原内卦」独立重建八宫，与数据表比对。"""

    for palace in C.PALACE_ORDER:
        pure = C.TRIGRAM_BITS[palace]
        full = pure + pure  # 八纯卦六爻 = 经卦三爻重叠加倍
        derived: list[str] = [hexagram_from_bits(full).name]
        for step in range(1, 6):  # 一至五世：初爻起逐爻累变
            derived.append(hexagram_from_bits(_flip(full, list(range(1, step + 1)))).name)
        wushi = _flip(full, [1, 2, 3, 4, 5])
        youhun = _flip(wushi, [4])  # 游魂：五世卦再回变四爻
        derived.append(hexagram_from_bits(youhun).name)
        guihun = pure + youhun[3:]  # 归魂：内卦复原为本宫
        derived.append(hexagram_from_bits(guihun).name)

        assert tuple(derived) == PALACE_SEQUENCE[palace], palace
        for name in derived:
            assert NAME_TO_INFO[name].palace == palace


def test_shi_ying_positions_follow_palace_rule() -> None:
    """世爻：本宫在上爻、一世至五世即该世数、游魂在四、归魂在三；应爻与世相隔三位。"""
    for palace, names in PALACE_SEQUENCE.items():
        expected_shi = [6, 1, 2, 3, 4, 5, 4, 3]
        for name, shi in zip(names, expected_shi, strict=False):
            info = NAME_TO_INFO[name]
            assert info.shi == shi, name
            assert info.ying == (shi + 3 if shi <= 3 else shi - 3), name
            assert info.palace == palace


def test_najia_tables_match_rule() -> None:
    """按纳甲起例重算内外卦纳甲：阳卦地支顺行、阴卦逆行，外卦自内卦第三步续推。"""

    for trigram in C.TRIGRAM_BITS:
        step = 2 if trigram in YANG_TRIGRAMS else -2
        start = C.BRANCHES.index(NAJIA_BRANCH_START[trigram])
        branches = [C.BRANCHES[(start + step * offset) % 12] for offset in range(6)]
        inner = tuple(f"{NAJIA_STEM_INNER[trigram]}{branches[i]}" for i in range(3))
        outer = tuple(f"{NAJIA_STEM_OUTER[trigram]}{branches[i]}" for i in range(3, 6))
        assert C.NAJIA_INNER[trigram] == inner, trigram
        assert C.NAJIA_OUTER[trigram] == outer, trigram


def test_six_relation_matches_generating_cycle() -> None:
    """生克按「同我兄弟/生我父母/我生子孙/克我官鬼/我克妻财」逐一核对。"""
    # 以乾宫金为例，逐支核对
    expected = {"子": "子孙", "寅": "妻财", "辰": "父母", "午": "官鬼", "申": "兄弟", "戌": "父母"}
    for branch, relation in expected.items():
        assert C.six_relation("金", C.BRANCH_ELEMENT[branch]) == relation
    # 同一地支换宫五行，六亲必须随之改变（六亲是相对关系，不是爻的固有属性）
    water = C.BRANCH_ELEMENT["子"]
    assert C.six_relation("金", water) == "子孙"
    assert C.six_relation("水", water) == "兄弟"
    assert C.six_relation("土", water) == "妻财"
    assert C.six_relation("火", water) == "官鬼"
    assert C.six_relation("木", water) == "父母"


def test_xun_kong_matches_six_xun_table() -> None:
    """每旬十日（含旬首本身）共用的空亡二支必须与旬空表一致。"""
    for xun_head, kong in XUN_KONG_TABLE.items():
        head_index = next(
            index for index in range(60) if pillar_text(pillar_of_index(index)) == xun_head
        )
        assert xun_head[0] == "甲"
        for offset in range(10):
            assert C.xun_kong(head_index + offset) == kong, (xun_head, offset)


def test_liu_shen_follows_day_stem() -> None:
    for stem, head in LIU_SHEN_HEAD.items():
        order = C.liu_shen_of(stem)
        assert order[0] == head, stem
        # 自初爻至上爻顺排，不得逆排或跳位
        start = C.LIU_SHEN.index(head)
        assert order == tuple(C.LIU_SHEN[(start + i) % 6] for i in range(6))


@pytest.mark.parametrize("case", DATA["cases"], ids=[c["case_id"] for c in DATA["cases"]])
def test_fixture_case(case: dict) -> None:
    inp = _input(lines=case["input"]["lines"])
    chart = calculate(inp)
    facts = chart.chart_facts
    expect = case["expect"]

    assert facts["day_pillar"]["text"] == CONST["day_pillar"]
    assert facts["month_build"]["branch"] == CONST["month_build"]
    assert facts["xun_kong"] == CONST["xun_kong"]
    assert facts["moving_lines"] == expect["moving_lines"]
    assert facts["liu_shen_order"] == CONST["liu_shen"]

    original = facts["original"]
    want = expect["original"]
    for key in ("name", "palace", "palace_element", "phase", "shi", "ying"):
        assert original[key] == want[key], key
    assert [line["najia"] for line in original["lines"]] == want["najia"]
    assert [line["element"] for line in original["lines"]] == want["elements"]
    assert [line["six_relation"] for line in original["lines"]] == want["six_relations"]
    assert [line["liu_shen"] for line in original["lines"]] == CONST["liu_shen"]
    # 世应标记与 shi/ying 必须自洽
    assert [line["position"] for line in original["lines"] if line["shi"]] == [want["shi"]]
    assert [line["position"] for line in original["lines"] if line["ying"]] == [want["ying"]]

    if want["name"] == "乾为天" or want["name"] == "坤为地":
        assert original["is_pure"] is True

    changed = facts["changed"]
    if expect["changed"] is None:
        assert changed is None
    else:
        want_changed = expect["changed"]
        for key in ("name", "palace", "palace_element", "phase", "shi", "ying"):
            assert changed[key] == want_changed[key], key
        assert [line["najia"] for line in changed["lines"]] == want_changed["najia"]
        assert [line["six_relation"] for line in changed["lines"]] == want_changed["six_relations"]
        # 变爻六亲以本卦卦宫为「我」
        moving = [line for line in original["lines"] if line["moving"]]
        assert moving, "该例应含动爻"
        for line in moving:
            assert line["changed"]["six_relation"] == want_changed["changed_line_six_relation"]

    assert facts["mutual"]["name"] == expect["mutual"]["name"]
    assert facts["mutual"]["palace"] == expect["mutual"]["palace"]


def test_time_method_uses_meihua_numbers() -> None:
    """2026-01-01 12:00（乙巳年冬月十三午时）：6/5/1 → 上坎下巽，水风井初爻动。"""
    chart = calculate(_input(method="time", lines=None))
    facts = chart.chart_facts
    assert facts["time_numbers"] == {
        "upper_number": 6,
        "lower_number": 5,
        "moving_position": 1,
        "year_number": 6,
        "month_number": 11,
        "day_number": 13,
        "hour_number": 7,
    }
    assert facts["original"]["name"] == "水风井"
    assert facts["original"]["upper"] == "坎"
    assert facts["original"]["lower"] == "巽"
    assert facts["moving_lines"] == [1]
    assert facts["changed"]["name"] == "水天需"


def test_time_method_always_single_moving_line() -> None:
    for minute in (0, 30):
        chart = calculate(
            _input(method="time", lines=None, cast_datetime=datetime(2026, 5, 20, 15, minute))
        )
        assert len(chart.chart_facts["moving_lines"]) == 1


def test_coins_are_reproducible() -> None:
    assert _coins(42) == [7, 6, 7, 6, 6, 7]
    first = calculate(_input(method="coins", lines=None, seed=42))
    second = calculate(_input(method="coins", lines=None, seed=42))
    assert first.chart_facts["values"] == second.chart_facts["values"]
    assert first.chart_facts["original"]["name"] == "山火贲"
    assert first.chart_facts["moving_lines"] == [2, 4, 5]
    assert first.chart_facts["changed"]["name"] == "乾为天"

    other = calculate(_input(method="coins", lines=None, seed=7))
    assert other.chart_facts["values"] != first.chart_facts["values"]


def test_coins_seed_defaults_to_cast_time() -> None:
    """未给 seed 时由起卦时刻派生，两次调用必须一致（不依赖机器随机源）。"""
    chart = calculate(_input(method="coins", lines=None))
    assert chart.chart_facts["seed"] == 20260101120000 % 2**32
    again = calculate(_input(method="coins", lines=None))
    assert chart.chart_facts["values"] == again.chart_facts["values"]


def test_question_storage_policy() -> None:
    kept = calculate(_input(question="这次合作能否推进"))
    assert kept.chart_facts["question"] == "这次合作能否推进"
    assert kept.chart_facts["question_stored"] is True
    assert kept.input_summary["question"] == "这次合作能否推进"

    dropped = calculate(_input(question="这次合作能否推进", store_question=False))
    assert dropped.chart_facts["question"] is None
    assert dropped.chart_facts["question_stored"] is False
    assert dropped.input_summary["question"] is None
    assert any("丢弃占问原文" in item for item in dropped.warnings)


def test_structural_markers() -> None:
    static = calculate(_input(lines=[7, 7, 7, 7, 7, 7]))
    ids = {item["rule_id"] for item in static.triggered_rules}
    assert "liuyao.moving.none" in ids
    assert "liuyao.palace.pure" in ids

    moving = calculate(_input(lines=[7, 7, 7, 7, 8, 9]))  # 火天大有，仅上爻动（9 为老阳）
    ids = {item["rule_id"] for item in moving.triggered_rules}
    assert "liuyao.moving.none" not in ids
    assert "liuyao.palace.guihun" in ids

    youhun = calculate(_input(lines=[8, 8, 8, 7, 8, 7]))  # 火地晋
    assert "liuyao.palace.youhun" in {item["rule_id"] for item in youhun.triggered_rules}

    multiple = calculate(_input(lines=[9, 7, 7, 7, 7, 9]))
    assert "liuyao.moving.multiple" in {item["rule_id"] for item in multiple.triggered_rules}


def test_shi_kong_marker_when_shi_branch_is_empty() -> None:
    """乙亥日属甲戌旬、空申酉：乾卦世爻壬戌不落空，不该报世爻旬空。"""
    chart = calculate(_input(lines=[7, 7, 7, 7, 7, 7]))
    assert chart.chart_facts["xun_kong"] == ["申", "酉"]
    assert "liuyao.shi.kong" not in {item["rule_id"] for item in chart.triggered_rules}

    # 天山遁世爻在二爻丙午；换成丁亥日（甲申旬、空午未）后世爻地支落空，应报出该标记
    shifted = calculate(_input(lines=[8, 8, 7, 7, 7, 7], cast_datetime=datetime(2026, 1, 13, 12, 0)))
    assert shifted.chart_facts["day_pillar"]["text"] == "丁亥"
    assert shifted.chart_facts["xun_kong"] == ["午", "未"]
    assert "liuyao.shi.kong" in {item["rule_id"] for item in shifted.triggered_rules}


def test_zi_hour_boundary_changes_day_pillar() -> None:
    late = datetime(2026, 1, 1, 23, 30)
    policy_a = calculate(_input(cast_datetime=late), LiuyaoConvention(day_boundary="zi_hour_policy_a"))
    policy_b = calculate(_input(cast_datetime=late), LiuyaoConvention(day_boundary="zi_hour_policy_b"))
    assert policy_a.chart_facts["day_pillar"]["text"] == "丙子"
    assert policy_b.chart_facts["day_pillar"]["text"] == "乙亥"
    assert policy_a.chart_facts["liu_shen_order"][0] == "朱雀"  # 丙日朱雀起
    assert policy_b.chart_facts["liu_shen_order"][0] == "青龙"
    assert any("23:00" in item for item in policy_a.warnings)


def test_month_build_follows_solar_term() -> None:
    before = calculate(_input(cast_datetime=datetime(2026, 1, 4, 12, 0)))
    after = calculate(_input(cast_datetime=datetime(2026, 1, 6, 12, 0)))
    assert before.chart_facts["month_build"]["jie"] == "大雪"
    assert before.chart_facts["month_build"]["branch"] == "子"
    assert after.chart_facts["month_build"]["jie"] == "小寒"
    assert after.chart_facts["month_build"]["branch"] == "丑"


def test_facts_and_convention_shape() -> None:
    chart = calculate(_input())
    assert chart.domain == "liuyao"
    assert chart.algorithm_version.startswith("liuyao-engine-")
    assert chart.convention["school"] == C.SCHOOL
    assert chart.convention["school_note"] == C.SCHOOL_NOTE
    assert chart.convention["month_basis"] == "solar_term"
    assert chart.input_summary["method"] == "manual"
    assert chart.input_summary["lines"] == [7, 7, 7, 7, 7, 7]
    assert len(chart.source_refs) >= 5
    assert C.SCHOOL_NOTE in chart.warnings
    # 盘面事实之外不得出现断语字段
    assert not {"judgement", "verdict", "ying_qi"} & set(chart.chart_facts)


def test_rule_notes_never_name_another_hexagram() -> None:
    """校验链会扫描报告里出现的卦名，规则 note 若提到别的卦会被误判成事实错误。"""
    samples = [
        [7, 7, 7, 7, 7, 7],
        [8, 8, 8, 8, 8, 8],
        [8, 8, 8, 7, 8, 7],
        [7, 7, 7, 7, 8, 7],
        [9, 7, 7, 7, 7, 9],
        [7, 8, 8, 8, 7, 8],
    ]
    for lines in samples:
        chart = calculate(_input(lines=lines))
        facts = chart.chart_facts
        allowed = {facts["original"]["name"], facts["mutual"]["name"]}
        if facts["changed"]:
            allowed.add(facts["changed"]["name"])
        for rule in chart.triggered_rules:
            text = rule["note"] + "、".join(rule["members"]) + rule["label"]
            for name in NAME_TO_INFO:
                if name in text:
                    assert name in allowed, (rule["rule_id"], text)


def test_manual_input_validation() -> None:
    with pytest.raises(ValidationError):
        LiuyaoInput(method="manual", cast_datetime=datetime(2026, 1, 1, 12, 0))  # 缺 lines
    with pytest.raises(ValidationError):
        LiuyaoInput(method="manual", cast_datetime=datetime(2026, 1, 1, 12, 0), lines=[7, 7, 7])
    with pytest.raises(ValidationError):
        LiuyaoInput(method="manual", cast_datetime=datetime(2026, 1, 1, 12, 0), lines=[7, 7, 7, 7, 7, 5])
    with pytest.raises(ValidationError):
        LiuyaoInput(method="coins", cast_datetime=datetime(2026, 1, 1, 12, 0), lines=[7] * 6)
    with pytest.raises(ValidationError):
        LiuyaoInput(method="time", cast_datetime=datetime(2026, 1, 1, 12, 0), seed=2**32)
    with pytest.raises(ValidationError):
        LiuyaoInput(method="manual", cast_datetime=datetime(2026, 1, 1, 12, 0), lines=[7] * 6, question="问" * 201)
    # 带时区的时刻一律拒绝：时区只能通过 timezone 字段声明，避免两种情况混用
    with pytest.raises(ValidationError):
        LiuyaoInput(method="time", cast_datetime=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))


def test_convention_rejects_unknown_school() -> None:
    with pytest.raises(ValidationError):
        LiuyaoConvention(school="meihua_v1")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        LiuyaoConvention(day_boundary="zi_hour_policy_c")  # type: ignore[arg-type]


def test_mutual_hexagram_uses_middle_four_lines() -> None:
    """互卦取下卦二三四、上卦三四五；用任意盘复核一遍。"""
    chart = calculate(_input(lines=[7, 8, 8, 8, 7, 8]))  # 水雷屯
    bits = chart.chart_facts["original"]["bits"]
    expected = hexagram_from_bits(bits[1:4] + bits[2:5])
    assert chart.chart_facts["mutual"]["name"] == expected.name
    assert chart.chart_facts["mutual"]["name"] == "山地剥"
