"""奇门遁甲（时家转盘拆补法）常量：九宫、九星、八门、八神、三奇六仪与三元局数。

本版本只实现一种口径，所有表都写成显式常量而不是「推导出来的」：
歌诀、局数、旬首、马星这些数据一旦写错，盘面必然整体偏移，
因此宁可逐条抄清楚，便于与古籍歌诀逐行核对，也便于测试侧独立重算比对。
"""

from __future__ import annotations

from app.domains.calendar_core.jiazi import BRANCHES, STEMS, pillar_of_index, pillar_text

#: 单一口径标识，回显到 `ChartResult.convention.school`
SCHOOL = "chaibu_zhuanpan_v1"
SCHOOL_NOTE = (
    "本版本只实现时家转盘拆补法：阴阳遁以二十四节气为界、上中下元以符头（甲日、己日）地支拆补，"
    "中五宫寄坤二宫、天禽随天芮。置闰法、飞盘奇门与法术奇门均不在本版本范围内。"
)

# ---- 九宫 ----
PALACE_NUMBERS: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 8, 9)
PALACE_NUMERAL: dict[int, str] = {
    1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九",
}
PALACE_TRIGRAM: dict[int, str] = {
    1: "坎", 2: "坤", 3: "震", 4: "巽", 5: "中", 6: "乾", 7: "兑", 8: "艮", 9: "离",
}
PALACE_DIRECTION: dict[int, str] = {
    1: "北", 2: "西南", 3: "东", 4: "东南", 5: "中", 6: "西北", 7: "西", 8: "东北", 9: "南",
}
PALACE_ELEMENT: dict[int, str] = {
    1: "水", 2: "土", 3: "木", 4: "木", 5: "土", 6: "金", 7: "金", 8: "土", 9: "火",
}
#: 八宫环：后天八卦方位上的「顺行」次序（坎→艮→震→巽→离→坤→兑→乾），中五不入环
RING: tuple[int, ...] = (1, 8, 3, 4, 9, 2, 7, 6)
CENTER_PALACE = 5
#: 中五宫寄坤二宫：布星、布门、布神时一律按坤二处理
CENTER_REDIRECT = 2


def palace_name(number: int) -> str:
    return f"{PALACE_TRIGRAM[number]}{PALACE_NUMERAL[number]}宫"


def center_redirect(palace: int) -> int:
    """中五宫寄坤二宫。"""
    return CENTER_REDIRECT if palace == CENTER_PALACE else palace


# ---- 九星 / 八门 ----
STARS_BY_PALACE: dict[int, str] = {
    1: "天蓬", 2: "天芮", 3: "天冲", 4: "天辅", 5: "天禽", 6: "天心", 7: "天柱", 8: "天任", 9: "天英",
}
#: 中五宫无门，八门只占其余八宫
DOORS_BY_PALACE: dict[int, str] = {
    1: "休门", 2: "死门", 3: "伤门", 4: "杜门", 6: "开门", 7: "惊门", 8: "生门", 9: "景门",
}

# ---- 八神 ----
#: 阳遁八神顺布；阴遁把白虎、玄武换成勾陈、朱雀
DEITIES_YANG: tuple[str, ...] = ("值符", "螣蛇", "太阴", "六合", "白虎", "玄武", "九地", "九天")
DEITIES_YIN: tuple[str, ...] = ("值符", "螣蛇", "太阴", "六合", "勾陈", "朱雀", "九地", "九天")

# ---- 三奇六仪 ----
#: 地盘布干的固定次序：六仪（戊己庚辛壬癸）在前，三奇（丁丙乙）在后
INSTRUMENTS: tuple[str, ...] = ("戊", "己", "庚", "辛", "壬", "癸", "丁", "丙", "乙")
#: 六甲遁于六仪：旬首 → 所遁之仪
XUN_INSTRUMENT: dict[str, str] = {
    "甲子": "戊", "甲戌": "己", "甲申": "庚", "甲午": "辛", "甲辰": "壬", "甲寅": "癸",
}
#: 三奇
THREE_MARVELS: tuple[str, ...] = ("乙", "丙", "丁")

# ---- 阴阳遁与三元局数 ----
#: 冬至→芒种为阳遁
YANG_TERMS: tuple[str, ...] = (
    "冬至", "小寒", "大寒", "立春", "雨水", "惊蛰",
    "春分", "清明", "谷雨", "立夏", "小满", "芒种",
)
#: 夏至→大雪为阴遁
YIN_TERMS: tuple[str, ...] = (
    "夏至", "小暑", "大暑", "立秋", "处暑", "白露",
    "秋分", "寒露", "霜降", "立冬", "小雪", "大雪",
)
#: 二十四节气上元 / 中元 / 下元局数（歌诀：冬至惊蛰一七四，小寒二八五相随……）
JU_TABLE: dict[str, tuple[int, int, int]] = {
    "冬至": (1, 7, 4),
    "小寒": (2, 8, 5),
    "大寒": (3, 9, 6),
    "立春": (8, 5, 2),
    "雨水": (9, 6, 3),
    "惊蛰": (1, 7, 4),
    "春分": (3, 9, 6),
    "清明": (4, 1, 7),
    "谷雨": (5, 2, 8),
    "立夏": (4, 1, 7),
    "小满": (5, 2, 8),
    "芒种": (6, 3, 9),
    "夏至": (9, 3, 6),
    "小暑": (8, 2, 5),
    "大暑": (7, 1, 4),
    "立秋": (2, 5, 8),
    "处暑": (1, 4, 7),
    "白露": (9, 3, 6),
    "秋分": (7, 1, 4),
    "寒露": (6, 9, 3),
    "霜降": (5, 8, 2),
    "立冬": (6, 9, 3),
    "小雪": (5, 8, 2),
    "大雪": (4, 7, 1),
}
YUAN_NAMES: tuple[str, ...] = ("上元", "中元", "下元")
#: 拆补法定元：符头日的地支——四仲为上元、四生为中元、四墓为下元
YUAN_BY_BRANCH: dict[str, int] = {
    "子": 0, "午": 0, "卯": 0, "酉": 0,
    "寅": 1, "申": 1, "巳": 1, "亥": 1,
    "辰": 2, "戌": 2, "丑": 2, "未": 2,
}
#: 符头只取甲日与己日（每五日一元）
FU_TOU_STEMS: tuple[str, ...] = ("甲", "己")

# ---- 旬空与马星 ----
#: 地支 → 后天八卦宫位（马星与旬空定位用）
BRANCH_PALACE: dict[str, int] = {
    "子": 1, "丑": 8, "寅": 8, "卯": 3, "辰": 4, "巳": 4,
    "午": 9, "未": 2, "申": 2, "酉": 7, "戌": 6, "亥": 6,
}
#: 马星：申子辰马在寅、寅午戌马在申、巳酉丑马在亥、亥卯未马在巳
MA_STAR: dict[str, str] = {
    "申": "寅", "子": "寅", "辰": "寅",
    "寅": "申", "午": "申", "戌": "申",
    "巳": "亥", "酉": "亥", "丑": "亥",
    "亥": "巳", "卯": "巳", "未": "巳",
}


def is_yang_dun(term_name: str) -> bool:
    if term_name in YANG_TERMS:
        return True
    if term_name in YIN_TERMS:
        return False
    raise ValueError(f"未知节气：{term_name}，无法判断阴阳遁")


def ju_number(term_name: str, yuan_index: int) -> int:
    """节气 + 元 → 局数。元为 0/1/2（上/中/下）。"""
    return JU_TABLE[term_name][yuan_index]


def fu_tou(day_index: int) -> tuple[str, str, int]:
    """符头：从当日（含当日）向前最近的甲日或己日。

    返回 (干支文本, 地支, 距当日天数)；天数用于反推符头的公历日期，供人工核对。
    """
    cursor = day_index
    for back in range(6):
        pillar = pillar_of_index(cursor)
        if pillar[0] in FU_TOU_STEMS:
            return pillar_text(pillar), pillar[1], back
        cursor = (cursor - 1) % 60
    raise RuntimeError("符头定位失败：六十甲子中必有甲日或己日")  # pragma: no cover


def xun_head_of(pillar_index: int) -> str:
    """时柱所在旬的旬首（甲子、甲戌……甲寅）。"""
    return pillar_text(pillar_of_index(pillar_index - pillar_index % 10))


def xun_kong(pillar_index: int) -> tuple[str, str]:
    """旬空：本旬未被配到的两个地支。"""
    start = pillar_index - pillar_index % 10
    return (BRANCHES[(start + 10) % 12], BRANCHES[(start + 11) % 12])


def stem_is_fu_tou(stem: str) -> bool:
    return stem in FU_TOU_STEMS


def stem_index(stem: str) -> int:
    return STEMS.index(stem)
