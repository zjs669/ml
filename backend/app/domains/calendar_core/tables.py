"""干支公共表：纳音、旬空、十二长生。

原先这些表只存在于紫微常量里，四柱要用就得复制一份。集中到这里后：
- 紫微、六爻、四柱共用同一份数据，避免「同一张表两处不一致」；
- 任何一张表写错，单测会同时打到三个术数，而不是只坏一处。

口径声明：
- 纳音按《三命通会》三十纳音，每两个干支共用一组；
- 旬空按六旬（甲子、甲戌、甲申、甲午、甲辰、甲寅）取所在旬的后两支；
- 十二长生：木亥、火寅、金巳、水申、土申（土寄水），阳干顺行、阴干逆行。
  「土同火（寅）」是另一派做法，本版本不采用，差异写进 docs/口径说明.md。
"""

from __future__ import annotations

from app.domains.calendar_core.jiazi import BRANCHES, STEMS, STEM_ELEMENT, STEM_YANG

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
