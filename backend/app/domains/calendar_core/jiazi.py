"""干支、五行、五虎遁、五鼠遁。

所有表都是显式常量，便于单测与会审；不依赖任何第三方排盘库。
"""

from __future__ import annotations

from typing import Literal

STEMS: tuple[str, ...] = ("甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸")
BRANCHES: tuple[str, ...] = ("子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥")

STEM_ELEMENT: dict[str, str] = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
    "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水",
}
BRANCH_ELEMENT: dict[str, str] = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火",
    "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水",
}
# 阳干/阳支为 True；阴为 False
STEM_YANG: dict[str, bool] = {stem: index % 2 == 0 for index, stem in enumerate(STEMS)}
BRANCH_YANG: dict[str, bool] = {branch: index % 2 == 0 for index, branch in enumerate(BRANCHES)}

# 日柱锚点：JDN + DAY_PILLAR_OFFSET ≡ 六十甲子序号
# 由 1949-10-01 = 甲子日（JDN 2433191 → 0）反解得到，并在单测中锁定。
DAY_PILLAR_OFFSET = 49

ELEMENTS: tuple[str, ...] = ("木", "火", "土", "金", "水")

# 十二节 → 月支（节气定月，中气不参与定月）
JIE_TO_MONTH_BRANCH: dict[str, str] = {
    "立春": "寅", "惊蛰": "卯", "清明": "辰", "立夏": "巳", "芒种": "午", "小暑": "未",
    "立秋": "申", "白露": "酉", "寒露": "戌", "立冬": "亥", "大雪": "子", "小寒": "丑",
}

# 五虎遁：年干 → 正月（寅月）天干
MONTH_STEM_START: dict[str, str] = {
    "甲": "丙", "己": "丙", "乙": "戊", "庚": "戊", "丙": "庚",
    "辛": "庚", "丁": "壬", "壬": "壬", "戊": "甲", "癸": "甲",
}

# 五鼠遁：日干 → 子时天干
HOUR_STEM_START: dict[str, str] = {
    "甲": "甲", "己": "甲", "乙": "丙", "庚": "丙", "丙": "戊",
    "辛": "戊", "丁": "庚", "壬": "庚", "戊": "壬", "癸": "壬",
}

Pillar = tuple[str, str]


def jiazi_index(stem: str, branch: str) -> int:
    """(天干, 地支) → 六十甲子序号 0..59。"""
    return (STEMS.index(stem) * 6 - BRANCHES.index(branch) * 5) % 60


def pillar_of_index(index: int) -> Pillar:
    index %= 60
    return STEMS[index % 10], BRANCHES[index % 12]


def pillar_text(pillar: Pillar) -> str:
    return f"{pillar[0]}{pillar[1]}"


def day_pillar_index(jdn: int) -> int:
    return (jdn + DAY_PILLAR_OFFSET) % 60


def year_pillar_index(ganzhi_year: int) -> int:
    """干支纪年（以立春为界）→ 序号；1984 甲子 → 0。"""
    return (ganzhi_year - 4) % 60


def month_stem(year_stem: str, month_branch: str) -> str:
    """五虎遁：由年干与月支推月干。月支索引 0=子，2=寅 为正月的位移基准。"""
    start = STEMS.index(MONTH_STEM_START[year_stem])
    offset = (BRANCHES.index(month_branch) - BRANCHES.index("寅")) % 12
    return STEMS[(start + offset) % 10]


def hour_branch(hour: int, minute: int = 0, second: int = 0) -> str:
    """23:00-00:59 为子时，依此类推每两小时一个时辰。"""
    total_minutes = hour * 60 + minute
    index = ((total_minutes + 60) // 120) % 12
    return BRANCHES[index]


def hour_stem(day_stem: str, branch: str) -> str:
    """五鼠遁：由日干与时辰地支推时干。"""
    start = STEMS.index(HOUR_STEM_START[day_stem])
    return STEMS[(start + BRANCHES.index(branch)) % 10]


def ten_god(day_stem: str, target_stem: str) -> str:
    """以日干为「我」，推目标天干的十神。

    同我者比劫（阴阳异为劫财），我生者食伤（异为伤官），
    我克者财（异为正财），克我者官杀（异为正官），生我者印（异为正印）。
    """
    me_element = STEM_ELEMENT[day_stem]
    me_yang = STEM_YANG[day_stem]
    other_element = STEM_ELEMENT[target_stem]
    same_polarity = me_yang == STEM_YANG[target_stem]
    relation = _element_relation(me_element, other_element)
    if relation == "same":
        return "比肩" if same_polarity else "劫财"
    if relation == "output":
        return "食神" if same_polarity else "伤官"
    if relation == "wealth":
        return "偏财" if same_polarity else "正财"
    if relation == "officer":
        return "七杀" if same_polarity else "正官"
    return "偏印" if same_polarity else "正印"


def _element_relation(me: str, other: str) -> Literal["same", "output", "wealth", "officer", "resource"]:
    if me == other:
        return "same"
    me_index = ELEMENTS.index(me)
    other_index = ELEMENTS.index(other)
    # 五行相生：木→火→土→金→水→木
    if (me_index + 1) % 5 == other_index:
        return "output"
    if (me_index + 2) % 5 == other_index:
        return "wealth"
    if (other_index + 2) % 5 == me_index:
        return "officer"
    return "resource"


# ---------------------------------------------------------------- 公共表
#
# 干支公共表：纳音、旬空、十二长生。
# 
# 原先这些表只存在于紫微常量里，四柱要用就得复制一份。集中到这里后：
# - 紫微、六爻、四柱共用同一份数据，避免「同一张表两处不一致」；
# - 任何一张表写错，单测会同时打到三个术数，而不是只坏一处。
# 
# 口径声明：
# - 纳音按《三命通会》三十纳音，每两个干支共用一组；
# - 旬空按六旬（甲子、甲戌、甲申、甲午、甲辰、甲寅）取所在旬的后两支；
# - 十二长生：木亥、火寅、金巳、水申、土申（土寄水），阳干顺行、阴干逆行。
#   「土同火（寅）」是另一派做法，本版本不采用，差异写进 docs/口径说明.md。


# ---- 纳音 ----
NA_YIN_30: tuple[str, ...] = (
    "海中金", "炉中火", "大林木", "路旁土", "剑锋金", "山头火",
    "涧下水", "城头土", "白蜡金", "杨柳木", "泉中水", "屋上土",
    "霹雳火", "松柏木", "长流水", "沙中金", "山下火", "平地木",
    "壁上土", "金箔金", "覆灯火", "天河水", "大驿土", "钗钏金",
    "桑柘木", "大溪水", "沙中土", "天上火", "石榴木", "大海水",
)

# ---- 旬空 ----
#: 六个旬首对应的空亡二支；下标 = 六十甲子序号 // 10
XUN_KONG: tuple[tuple[str, str], ...] = (
    ("戌", "亥"),  # 甲子旬
    ("申", "酉"),  # 甲戌旬
    ("午", "未"),  # 甲申旬
    ("辰", "巳"),  # 甲午旬
    ("寅", "卯"),  # 甲辰旬
    ("子", "丑"),  # 甲寅旬
)

# ---- 十二长生 ----
CHANG_SHENG_ORDER: tuple[str, ...] = (
    "长生", "沐浴", "冠带", "临官", "帝旺", "衰",
    "病", "死", "墓", "绝", "胎", "养",
)

#: 五行 → 长生所在地支（土寄水，起于申）
CHANG_SHENG_START: dict[str, int] = {
    "木": BRANCHES.index("亥"),
    "火": BRANCHES.index("寅"),
    "金": BRANCHES.index("巳"),
    "水": BRANCHES.index("申"),
    "土": BRANCHES.index("申"),
}

#: 紫微用「五行局」而不是五行本身，这里给出局数 → 起宫（水二/土五起申、木三起亥、金四起巳、火六起寅）
CHANG_SHENG_START_BY_BUREAU: dict[int, int] = {2: 8, 3: 11, 4: 5, 5: 8, 6: 2}


def nayin_of_index(index: int) -> str:
    return NA_YIN_30[(index % 60) // 2]


def xun_of_index(index: int) -> tuple[str, str]:
    return XUN_KONG[(index % 60) // 10]


def chang_sheng(branch: str, stem: str) -> str:
    """某天干在某地支上的十二长生位（阳顺阴逆，土寄水）。"""
    element = STEM_ELEMENT[stem]
    start = CHANG_SHENG_START[element]
    step = BRANCHES.index(branch)
    offset = (step - start) % 12 if STEM_YANG[stem] else (start - step) % 12
    return CHANG_SHENG_ORDER[offset]


def chang_sheng_by_bureau(branch: str, bureau: int, forward: bool) -> str:
    """紫微长生十二神：局数起宫、按大限方向排。"""
    start = CHANG_SHENG_START_BY_BUREAU[bureau]
    step = BRANCHES.index(branch)
    offset = (step - start) % 12 if forward else (start - step) % 12
    return CHANG_SHENG_ORDER[offset]


def stem_index(stem: str) -> int:
    return STEMS.index(stem)
