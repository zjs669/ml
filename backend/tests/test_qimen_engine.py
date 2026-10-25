"""奇门引擎测试（时家转盘拆补法）。

奇门三层盘（天盘九星 / 人盘八门 / 神盘八神）在八宫环上都是「刚性旋转」：
环的方向写反、或基准宫错一格，盘面看上去依然完整，只是处处偏移，肉眼极难发现。
因此这里的期望值一律不取引擎输出，而是按歌诀与环定义重新推一遍：

- 局数：按「上元 +6 得中元、再 +6 得下元（阴遁反向）」的歌诀递推关系核对，
  并锚定数条原句；
- 地盘：按「自局数宫起阳顺阴逆布戊己庚辛壬癸丁丙乙」重排；
- 天盘/人盘：把盘面按环序读出来，与「本位序列的整体旋转」逐位比对；
- 神盘：按「自值符落宫起阳顺阴逆」重排；
- 旬空 / 马星：照表核对，不用引擎公式。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.domains.qimen import constants as C
from app.domains.qimen.engine import _earth_plate, calculate
from app.domains.qimen.schemas import QimenConvention, QimenInput

FIXTURES = Path(__file__).parent / "fixtures" / "qimen_cases.json"
DATA = json.loads(FIXTURES.read_text(encoding="utf-8"))

# ---- 独立数据：六十甲子与八宫环 ----
STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
JIAZI = [STEMS[i % 10] + BRANCHES[i % 12] for i in range(60)]

#: 后天八卦八宫环（坎→艮→震→巽→离→坤→兑→乾），「阳遁顺行」即沿此序前进
RING = (1, 8, 3, 4, 9, 2, 7, 6)
CENTER = 5
KUN2 = 2

YANG_TERMS = (
    "冬至", "小寒", "大寒", "立春", "雨水", "惊蛰",
    "春分", "清明", "谷雨", "立夏", "小满", "芒种",
)
YIN_TERMS = (
    "夏至", "小暑", "大暑", "立秋", "处暑", "白露",
    "秋分", "寒露", "霜降", "立冬", "小雪", "大雪",
)

STARS_AT = {
    1: "天蓬", 2: "天芮", 3: "天冲", 4: "天辅", 5: "天禽",
    6: "天心", 7: "天柱", 8: "天任", 9: "天英",
}
DOORS_AT = {1: "休门", 2: "死门", 3: "伤门", 4: "杜门", 6: "开门", 7: "惊门", 8: "生门", 9: "景门"}
DEITIES_YANG = ("值符", "螣蛇", "太阴", "六合", "白虎", "玄武", "九地", "九天")
DEITIES_YIN = ("值符", "螣蛇", "太阴", "六合", "勾陈", "朱雀", "九地", "九天")
INSTRUMENTS = ("戊", "己", "庚", "辛", "壬", "癸", "丁", "丙", "乙")

#: 六旬空亡（甲子旬空戌亥……），与引擎的取模公式相互独立
XUN_KONG = {
    "甲子": ("戌", "亥"),
    "甲戌": ("申", "酉"),
    "甲申": ("午", "未"),
    "甲午": ("辰", "巳"),
    "甲辰": ("寅", "卯"),
    "甲寅": ("子", "丑"),
}
#: 马星：申子辰马在寅、寅午戌马在申、巳酉丑马在亥、亥卯未马在巳
MA_OF = {
    "申": "寅", "子": "寅", "辰": "寅",
    "寅": "申", "午": "申", "戌": "申",
    "巳": "亥", "酉": "亥", "丑": "亥",
    "亥": "巳", "卯": "巳", "未": "巳",
}
BRANCH_PALACE = {
    "子": 1, "丑": 8, "寅": 8, "卯": 3, "辰": 4, "巳": 4,
    "午": 9, "未": 2, "申": 2, "酉": 7, "戌": 6, "亥": 6,
}
#: 符头地支定元：四仲上元、四生中元、四墓下元
YUAN_BY_BRANCH = {
    "子": 0, "午": 0, "卯": 0, "酉": 0,
    "寅": 1, "申": 1, "巳": 1, "亥": 1,
    "辰": 2, "戌": 2, "丑": 2, "未": 2,
}

#: 横跨四个世纪、覆盖十二个月的探针时刻（避免只测到某几个节气）
PROBE_TIMES = [datetime(year, month, 15, 9, 30) for year in (1900, 1955, 2026, 2100) for month in range(1, 13)]


def _idx(pillar: str) -> int:
    return JIAZI.index(pillar)


def _xun_head_of(pillar: str) -> str:
    index = _idx(pillar)
    return JIAZI[index - index % 10]


def _facts(dt: datetime, convention: QimenConvention | None = None) -> dict[str, Any]:
    chart = calculate(QimenInput(cast_datetime=dt, timezone="Asia/Shanghai"), convention)
    return chart.chart_facts


def _palaces(facts: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {item["number"]: item for item in facts["palaces"]}


def _effective_day(dt: datetime, convention: QimenConvention) -> datetime:
    """23:00 换日口径下，日柱归入次日——符头日期要以生效日为准。"""
    if convention.day_boundary == "zi_hour_policy_a" and dt.hour >= 23:
        return dt + timedelta(days=1)
    return dt


def _earth(ju: int, yang: bool) -> dict[int, str]:
    """自局数宫起，阳遁沿宫数递增、阴遁沿宫数递减，布戊己庚辛壬癸丁丙乙。"""
    plate: dict[int, str] = {}
    for offset, stem in enumerate(INSTRUMENTS):
        palace = ((ju - 1 + (offset if yang else -offset)) % 9) + 1
        plate[palace] = stem
    return plate


# ---------------------------------------------------------------- 局数 / 三元


def test_ju_table_covers_twenty_four_terms() -> None:
    assert set(C.JU_TABLE) == set(YANG_TERMS) | set(YIN_TERMS)
    assert len(C.JU_TABLE) == 24
    for term, triple in C.JU_TABLE.items():
        assert len(set(triple)) == 3, term
        assert all(1 <= number <= 9 for number in triple), term


def test_ju_numbers_follow_song_cycle() -> None:
    """歌诀中同一节气的三元是「+6、+6」的循环：阳遁顺推、阴遁逆推。"""
    for term, (upper, middle, lower) in C.JU_TABLE.items():
        step = 6 if term in YANG_TERMS else 3
        assert middle == ((upper - 1 + step) % 9) + 1, term
        assert lower == ((middle - 1 + step) % 9) + 1, term


@pytest.mark.parametrize(
    ("term", "triple"),
    [
        ("冬至", (1, 7, 4)),
        ("立春", (8, 5, 2)),
        ("芒种", (6, 3, 9)),
        ("夏至", (9, 3, 6)),
        ("立秋", (2, 5, 8)),
        ("大雪", (4, 7, 1)),
    ],
)
def test_ju_table_anchors_song_lines(term: str, triple: tuple[int, int, int]) -> None:
    """锚定《烟波钓叟歌》原句，防止整张表被"规律化"改写。"""
    assert C.JU_TABLE[term] == triple


def test_yuan_follows_fu_tou_branch() -> None:
    assert C.YUAN_BY_BRANCH == YUAN_BY_BRANCH
    assert set(C.YUAN_BY_BRANCH) == set(BRANCHES)


def test_fu_tou_is_nearest_jia_or_ji_day() -> None:
    """符头必须落在甲日或己日，且距离当日不超过五日（每五日一元）。"""
    for day_index in range(60):
        text, branch, back = C.fu_tou(day_index)
        assert text[0] in ("甲", "己"), text
        assert 0 <= back <= 5
        assert text == JIAZI[(day_index - back) % 60]
        assert branch == text[1]
        assert C.YUAN_BY_BRANCH[branch] == YUAN_BY_BRANCH[text[1]]


# ---------------------------------------------------------------- 地盘


def test_earth_plate_is_permutation_of_nine_stems() -> None:
    for ju in range(1, 10):
        for yang in (True, False):
            plate = _earth_plate(ju, yang)
            assert plate == _earth(ju, yang)
            assert sorted(plate.values()) == sorted(INSTRUMENTS)
            assert plate[ju] == "戊", (ju, yang)


def test_earth_plate_runs_along_palace_numbers() -> None:
    """阳遁顺布等价于按宫数递增，阴遁逆布等价于按宫数递减。"""
    for ju in range(1, 10):
        yang_plate = _earth_plate(ju, True)
        for offset, stem in enumerate(INSTRUMENTS):
            assert yang_plate[((ju - 1 + offset) % 9) + 1] == stem
        yin_plate = _earth_plate(ju, False)
        for offset, stem in enumerate(INSTRUMENTS):
            assert yin_plate[((ju - 1 - offset) % 9) + 1] == stem


def test_three_marvels_sit_on_last_three_steps() -> None:
    """三奇乙丙丁固定排在地盘最后三位，与六仪分开——这是地盘排法最容易错的一处。"""
    for ju in range(1, 10):
        for yang in (True, False):
            plate = _earth_plate(ju, yang)
            positions = [next(p for p, s in plate.items() if s == stem) for stem in ("乙", "丙", "丁")]
            assert len(set(positions)) == 3
            assert all(plate[p] in ("乙", "丙", "丁") for p in positions)


# ---------------------------------------------------------------- 值符 / 值使


@pytest.mark.parametrize("dt", PROBE_TIMES, ids=[d.isoformat() for d in PROBE_TIMES])
def test_zhifu_and_zhishi_come_from_xun_head_palace(dt: datetime) -> None:
    facts = _facts(dt)
    hour_pillar = facts["pillars"]["hour"]["text"]
    xun_head = _xun_head_of(hour_pillar)
    instrument = C.XUN_INSTRUMENT[xun_head]
    earth = _earth(facts["dun"]["ju"], facts["dun"]["is_yang"])

    assert facts["xun_kong"]["xun_head"] == xun_head
    assert facts["xun_kong"]["instrument"] == instrument
    xun_palace = next(p for p, s in earth.items() if s == instrument)
    assert facts["zhifu"]["palace"] == xun_palace
    assert facts["zhifu"]["star"] == STARS_AT[xun_palace]
    # 中五宫无门，值使取寄宫坤二的死门
    assert facts["zhishi"]["door"] == DOORS_AT[xun_palace if xun_palace != CENTER else KUN2]
    assert facts["zhishi"]["steps"] == _idx(hour_pillar) % 10


@pytest.mark.parametrize("dt", PROBE_TIMES, ids=[d.isoformat() for d in PROBE_TIMES])
def test_zhifu_lands_on_hour_stem_palace(dt: datetime) -> None:
    """值符随时干：时干落哪一宫，值符星就转到哪一宫（甲时则用旬首宫）。"""
    facts = _facts(dt)
    earth = _earth(facts["dun"]["ju"], facts["dun"]["is_yang"])
    stem = facts["pillars"]["hour"]["stem"]
    raw = facts["zhifu"]["palace"] if stem == "甲" else next(p for p, s in earth.items() if s == stem)
    # 中五宫寄坤二：时干（或旬首）落中五时，实际按坤二处理
    expected = KUN2 if raw == CENTER else raw
    assert facts["hour_stem_palace"]["palace"] == expected
    assert facts["zhifu"]["landing_palace"] == expected
    palaces = _palaces(facts)
    landing = palaces[facts["zhifu"]["landing_palace"]]
    # 旬首落中五时值符为天禽，而天禽寄坤二随天芮同行，因此可能出现在 extra_star 上
    assert facts["zhifu"]["star"] in (landing["star"], landing["extra_star"])
    assert landing["is_zhifu"] is True


# ---------------------------------------------------------------- 天盘 / 人盘 / 神盘


@pytest.mark.parametrize("dt", PROBE_TIMES, ids=[d.isoformat() for d in PROBE_TIMES])
def test_sky_stars_are_a_rigid_rotation_of_ring(dt: datetime) -> None:
    facts = _facts(dt)
    palaces = _palaces(facts)
    base = [STARS_AT[palace] for palace in RING]
    observed = [palaces[palace]["star"] for palace in RING]

    xun_ring = RING.index(facts["zhifu"]["palace"] if facts["zhifu"]["palace"] != CENTER else KUN2)
    target_ring = RING.index(facts["zhifu"]["landing_palace"])
    offset = (target_ring - xun_ring) % 8
    assert observed == [base[(i - offset) % 8] for i in range(8)]


@pytest.mark.parametrize("dt", PROBE_TIMES, ids=[d.isoformat() for d in PROBE_TIMES])
def test_sky_stems_rotate_together_with_stars(dt: datetime) -> None:
    """天盘干与天盘星同步旋转：星转几格，干就转几格，否则「星干同行」就断了。"""
    facts = _facts(dt)
    palaces = _palaces(facts)
    earth = _earth(facts["dun"]["ju"], facts["dun"]["is_yang"])
    base_stems = [earth[palace] for palace in RING]
    observed = [palaces[palace]["sky_stem"] for palace in RING]

    xun_ring = RING.index(facts["zhifu"]["palace"] if facts["zhifu"]["palace"] != CENTER else KUN2)
    offset = (RING.index(facts["zhifu"]["landing_palace"]) - xun_ring) % 8
    assert observed == [base_stems[(i - offset) % 8] for i in range(8)]


@pytest.mark.parametrize("dt", PROBE_TIMES, ids=[d.isoformat() for d in PROBE_TIMES])
def test_doors_are_a_rigid_rotation_by_xun_step(dt: datetime) -> None:
    facts = _facts(dt)
    palaces = _palaces(facts)
    base = [DOORS_AT[palace] for palace in RING]
    observed = [palaces[palace]["door"] for palace in RING]

    step = facts["zhishi"]["steps"]
    direction = 1 if facts["dun"]["is_yang"] else -1
    offset = (step * direction) % 8
    assert observed == [base[(i - offset) % 8] for i in range(8)]
    # 八门是满排：八个宫恰好各得一扇门，不重不漏
    assert sorted(observed) == sorted(DOORS_AT.values())


@pytest.mark.parametrize("dt", PROBE_TIMES, ids=[d.isoformat() for d in PROBE_TIMES])
def test_zhishi_door_lands_on_expected_palace(dt: datetime) -> None:
    facts = _facts(dt)
    xun_ring = RING.index(facts["zhifu"]["palace"] if facts["zhifu"]["palace"] != CENTER else KUN2)
    direction = 1 if facts["dun"]["is_yang"] else -1
    expected = RING[(xun_ring + facts["zhishi"]["steps"] * direction) % 8]
    assert facts["zhishi"]["palace"] == expected
    palace = _palaces(facts)[expected]
    assert palace["door"] == facts["zhishi"]["door"]
    assert palace["is_zhishi"] is True


@pytest.mark.parametrize("dt", PROBE_TIMES, ids=[d.isoformat() for d in PROBE_TIMES])
def test_deities_are_laid_out_from_zhifu_palace(dt: datetime) -> None:
    facts = _facts(dt)
    palaces = _palaces(facts)
    yang = facts["dun"]["is_yang"]
    order = DEITIES_YANG if yang else DEITIES_YIN
    landing_ring = RING.index(facts["zhifu"]["landing_palace"])

    assert palaces[facts["zhifu"]["landing_palace"]]["deity"] == "值符"
    for palace in RING:
        index = RING.index(palace)
        distance = (index - landing_ring) % 8 if yang else (landing_ring - index) % 8
        assert palaces[palace]["deity"] == order[distance], palace

    deities = {palaces[palace]["deity"] for palace in RING}
    # 阴遁换将：白虎玄武换成勾陈朱雀，这是阴阳遁唯一的用神差异
    assert ("白虎" in deities) is yang
    assert ("玄武" in deities) is yang
    assert ("勾陈" in deities) is (not yang)
    assert ("朱雀" in deities) is (not yang)


# ---------------------------------------------------------------- 中宫寄坤二


@pytest.mark.parametrize("dt", PROBE_TIMES, ids=[d.isoformat() for d in PROBE_TIMES])
def test_center_palace_has_no_door_or_deity(dt: datetime) -> None:
    facts = _facts(dt)
    center = _palaces(facts)[CENTER]
    assert center["star"] == "天禽"
    assert center["door"] is None
    assert center["deity"] is None
    assert center["sky_stem"] is None
    assert center["is_center"] is True
    assert center["earth_stem"] == _earth(facts["dun"]["ju"], facts["dun"]["is_yang"])[CENTER]


@pytest.mark.parametrize("dt", PROBE_TIMES, ids=[d.isoformat() for d in PROBE_TIMES])
def test_tianqin_rides_with_tianrui(dt: datetime) -> None:
    """天禽寄坤二：天芮转到哪一宫，天禽就跟到哪一宫，并带上中五地盘干。"""
    facts = _facts(dt)
    riders = [item for item in facts["palaces"] if item.get("extra_star")]
    assert len(riders) == 1
    rider = riders[0]
    assert rider["extra_star"] == "天禽"
    assert rider["star"] == "天芮"
    assert rider["extra_sky_stem"] == _earth(facts["dun"]["ju"], facts["dun"]["is_yang"])[CENTER]


# ---------------------------------------------------------------- 旬空 / 马星 / 伏吟


@pytest.mark.parametrize("dt", PROBE_TIMES, ids=[d.isoformat() for d in PROBE_TIMES])
def test_xun_kong_matches_six_xun_table(dt: datetime) -> None:
    facts = _facts(dt)
    hour_pillar = facts["pillars"]["hour"]["text"]
    assert tuple(facts["xun_kong"]["branches"]) == XUN_KONG[_xun_head_of(hour_pillar)]


@pytest.mark.parametrize("dt", PROBE_TIMES, ids=[d.isoformat() for d in PROBE_TIMES])
def test_ma_star_follows_hour_branch(dt: datetime) -> None:
    facts = _facts(dt)
    branch = facts["pillars"]["hour"]["branch"]
    assert facts["ma_star"]["branch"] == MA_OF[branch]
    assert facts["ma_star"]["palace"] == BRANCH_PALACE[MA_OF[branch]]


@pytest.mark.parametrize("dt", PROBE_TIMES, ids=[d.isoformat() for d in PROBE_TIMES])
def test_fuyin_flags(dt: datetime) -> None:
    """星伏吟 = 值符星未离旬首宫；门伏吟 = 时柱即旬首（旬内第 0 步）。"""
    facts = _facts(dt)
    xun_palace = facts["zhifu"]["palace"] if facts["zhifu"]["palace"] != CENTER else KUN2
    assert facts["fuyin"]["star"] is (facts["zhifu"]["landing_palace"] == xun_palace)
    assert facts["fuyin"]["door"] is (facts["zhishi"]["steps"] == 0)

    rule_ids = {item["rule_id"] for item in calculate(
        QimenInput(cast_datetime=dt, timezone="Asia/Shanghai")
    ).triggered_rules}
    assert ("qimen.fuyin.star" in rule_ids) is facts["fuyin"]["star"]
    assert ("qimen.fuyin.door" in rule_ids) is facts["fuyin"]["door"]


# ---------------------------------------------------------------- 口径与提示


def test_convention_echo_and_warnings() -> None:
    chart = calculate(
        QimenInput(cast_datetime=datetime(2026, 1, 4, 23, 0), timezone="Asia/Shanghai")
    )
    assert chart.domain == "qimen"
    assert chart.convention["school"] == "chaibu_zhuanpan_v1"
    assert chart.convention["school_note"]
    text = "\n".join(chart.warnings)
    assert "中五宫寄坤二宫" in text
    assert "拆补" in text and "置闰" in text
    # 甲子时即旬首，必须显式提示伏吟
    assert "伏吟" in text


def test_zi_hour_policy_changes_day_pillar_and_ju() -> None:
    """23:00 起的两套换日口径会改日柱→符头→局数，必须一起变，不能只改一处。"""
    moment = datetime(2026, 1, 4, 23, 0)
    a = _facts(moment, QimenConvention(day_boundary="zi_hour_policy_a"))
    b = _facts(moment, QimenConvention(day_boundary="zi_hour_policy_b"))
    assert a["pillars"]["day"]["text"] != b["pillars"]["day"]["text"]
    assert a["dun"]["ju"] != b["dun"]["ju"] or a["fu_tou"]["pillar"] != b["fu_tou"]["pillar"]
    # 两套口径下时柱同为甲子（五鼠遁都取次日日干），这是已声明口径的必然结果
    assert a["pillars"]["hour"]["text"] == b["pillars"]["hour"]["text"] == "甲子"


def test_fu_tou_date_matches_effective_day() -> None:
    convention = QimenConvention()
    for dt in PROBE_TIMES + [datetime(2026, 1, 4, 23, 0)]:
        facts = _facts(dt, convention)
        effective = _effective_day(dt, convention).date()
        back = (_idx(facts["pillars"]["day"]["text"]) - _idx(facts["fu_tou"]["pillar"])) % 60
        assert back <= 5
        assert facts["fu_tou"]["date"] == (effective - timedelta(days=back)).isoformat()


# ---------------------------------------------------------------- 入参校验


def test_rejects_tz_aware_datetime() -> None:
    with pytest.raises(ValidationError):
        QimenInput(cast_datetime=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))


def test_rejects_out_of_range_year() -> None:
    with pytest.raises(ValidationError):
        QimenInput(cast_datetime=datetime(1799, 12, 31, 23, 0))
    with pytest.raises(ValidationError):
        QimenInput(cast_datetime=datetime(2201, 1, 1, 0, 0))


def test_rejects_unknown_school() -> None:
    with pytest.raises(ValidationError):
        QimenConvention(school="feipan_v1")


def test_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        QimenInput(cast_datetime=datetime(2026, 1, 1, 12, 0), ju=4)


# ---------------------------------------------------------------- 手推基准


@pytest.mark.parametrize("case", DATA["cases"], ids=[c["case_id"] for c in DATA["cases"]])
def test_fixture_case(case: dict) -> None:
    facts = _facts(datetime.fromisoformat(case["input"]["cast_datetime"]))
    expect = case["expect"]

    assert [facts["pillars"][key]["text"] for key in ("year", "month", "day", "hour")] == expect["pillars"]
    assert facts["term"]["name"] == expect["term"]
    assert facts["dun"]["text"] == expect["dun"]
    assert facts["dun"]["ju"] == expect["ju"]
    assert facts["dun"]["yuan"] == expect["yuan"]
    assert [facts["fu_tou"]["pillar"], facts["fu_tou"]["branch"], facts["fu_tou"]["date"]] == expect["fu_tou"]
    assert [facts["xun_kong"]["xun_head"], facts["xun_kong"]["instrument"]] == expect["xun"]
    assert [
        facts["zhifu"]["star"],
        facts["zhifu"]["palace"],
        facts["zhifu"]["landing_palace"],
    ] == expect["zhifu"]
    assert [
        facts["zhishi"]["door"],
        facts["zhishi"]["palace"],
        facts["zhishi"]["steps"],
    ] == expect["zhishi"]
    assert facts["xun_kong"]["branches"] == expect["kong"]
    assert [facts["ma_star"]["branch"], facts["ma_star"]["palace"]] == expect["ma"]
    assert [facts["fuyin"]["star"], facts["fuyin"]["door"]] == expect["fuyin"]

    if "palaces" in expect:
        observed = [
            [
                item["number"],
                item["earth_stem"],
                item["sky_stem"],
                item["extra_sky_stem"],
                item["star"],
                item["extra_star"],
                item["door"],
                item["deity"],
            ]
            for item in facts["palaces"]
        ]
        assert observed == expect["palaces"]
