"""大六壬常量：月将、贵人、寄宫、五行生克。

全部写成显式常量并注明出处，运行期不读外部文件。
本模块只放「不会变的东西」，推导逻辑在 `engine.py`。
"""

from __future__ import annotations

from app.domains.calendar_core.jiazi import BRANCHES, BRANCH_ELEMENT, STEM_ELEMENT

#: 中气 → 月将（地支）。大六壬以中气换月将
QI_TO_MONTH_GENERAL: dict[str, str] = {
    "雨水": "亥", "春分": "戌", "谷雨": "酉", "小满": "申",
    "夏至": "未", "大暑": "午", "处暑": "巳", "秋分": "辰",
    "霜降": "卯", "小雪": "寅", "冬至": "丑", "大寒": "子",
}

#: 月将名（登明、河魁等十二将名）
MONTH_GENERAL_NAMES: dict[str, str] = {
    "亥": "登明", "戌": "河魁", "酉": "从魁", "申": "传送",
    "未": "小吉", "午": "胜光", "巳": "太乙", "辰": "天罡",
    "卯": "太冲", "寅": "功曹", "丑": "大吉", "子": "神后",
}

#: 天将十二神（顺序固定）
TIAN_JIANG: tuple[str, ...] = (
    "贵人", "螣蛇", "朱雀", "六合", "勾陈", "青龙",
    "天空", "白虎", "太常", "玄武", "太阴", "天后",
)

#: 天将简称
TIAN_JIANG_SHORT: dict[str, str] = {
    "贵人": "贵", "螣蛇": "蛇", "朱雀": "雀", "六合": "合",
    "勾陈": "勾", "青龙": "龙", "天空": "空", "白虎": "虎",
    "太常": "常", "玄武": "玄", "太阴": "阴", "天后": "后",
}

#: 日干寄宫（天干寄居的地盘宫位）。甲寄寅、乙寄辰、丙戊寄巳、丁己寄未、庚寄申、辛寄戌、壬寄亥、癸寄丑
STEM_LODGE: dict[str, str] = {
    "甲": "寅", "乙": "辰", "丙": "巳", "丁": "未", "戊": "巳",
    "己": "未", "庚": "申", "辛": "戌", "壬": "亥", "癸": "丑",
}

#: 阳贵人：日干 → 地盘宫位（甲戊庚牛羊，乙己鼠猴乡，丙丁猪鸡位，壬癸兔蛇藏，六辛逢马虎）
YANG_GUI_REN: dict[str, str] = {
    "甲": "丑", "戊": "丑", "庚": "丑",
    "乙": "子", "己": "子",
    "丙": "亥", "丁": "亥",
    "壬": "卯", "癸": "卯",
    "辛": "午",
}

#: 阴贵人：日干 → 地盘宫位（与阳贵相对）
YIN_GUI_REN: dict[str, str] = {
    "甲": "未", "戊": "未", "庚": "未",
    "乙": "申", "己": "申",
    "丙": "酉", "丁": "酉",
    "壬": "巳", "癸": "巳",
    "辛": "寅",
}

#: 天马（月支三合 → 驿马地支）
TIAN_MA_BY_GROUP: dict[str, str] = {
    "寅午戌": "申", "申子辰": "寅", "巳酉丑": "亥", "亥卯未": "巳",
}

#: 日干五行 → 十二长生起点（地支）
CHANG_SHENG_START: dict[str, str] = {
    "木": "亥", "火": "寅", "金": "巳", "水": "申", "土": "申",
}

#: 长生十二神顺序
CHANG_SHENG_ORDER: tuple[str, ...] = (
    "长生", "沐浴", "冠带", "临官", "帝旺", "衰",
    "病", "死", "墓", "绝", "胎", "养",
)

#: 建除十二神顺序
JIAN_CHU_ORDER: tuple[str, ...] = (
    "建", "除", "满", "平", "定", "执", "破", "危", "成", "收", "开", "闭",
)

#: 三传课体（九宗门）。
#: 已实现：贼克法、比用法、涉害法、遥克、伏吟、返吟。
#: 未实现：昴星、别责、八专 —— 这三个需要课表或额外的分取规则
#: （昴星要按日干阴阳分取酉上神/天盘酉下神；别责与八专各有专门的取传法），
#: 各版本教材次序有差异，不宜凭结构推演硬补。
IMPLEMENTED_KE_TI: tuple[str, ...] = (
    "贼克法", "比用法", "涉害法", "遥克", "伏吟", "返吟",
)
UNIMPLEMENTED_KE_TI: tuple[str, ...] = ("昴星法", "别责法", "八专法")

#: 伏吟 / 返吟的判据说明（写进结果，便于复核）
FUYIN_NOTE = "月将与占时同支：天盘与地盘完全重合，四课上下神相同，无克可取的课体"
FANYIN_NOTE = "月将与占时相冲：天盘每宫都与地盘相冲，四课上下神两两相冲的课体"

SCHOOL_NOTE = (
    "本版本实现大六壬主干：月将加时定天地盘、四课、贼克法三传（含比用法）。"
    "涉害、遥克、昴星、别责、八专、伏吟、返吟等复杂课体未实现；"
    "遇到这些情形时三传留空并说明原因，不硬凑结果。"
    "只出盘面结构与神煞位置，不判断吉凶、不推应期。"
)


def branch_element(branch: str) -> str:
    return BRANCH_ELEMENT[branch]


def stem_element(stem: str) -> str:
    return STEM_ELEMENT[stem]


def is_ke(attacker_element: str, target_element: str) -> bool:
    """attacker 是否克 target（我克者）。五行相克：木克土、土克水、水克火、火克金、金克木。"""
    from app.domains.calendar_core.jiazi import ELEMENTS

    attacker = ELEMENTS.index(attacker_element)
    target = ELEMENTS.index(target_element)
    return (attacker + 2) % 5 == target


def tian_ma_of(month_branch: str) -> str:
    """月支 → 天马。"""
    index = BRANCHES.index(month_branch)
    if index in (2, 6, 10):
        return TIAN_MA_BY_GROUP["寅午戌"]
    if index in (8, 0, 4):
        return TIAN_MA_BY_GROUP["申子辰"]
    if index in (5, 9, 1):
        return TIAN_MA_BY_GROUP["巳酉丑"]
    return TIAN_MA_BY_GROUP["亥卯未"]


def chang_sheng_of(stem: str, branch: str) -> str:
    """日干在某支上的长生十二神状态。

    阳干顺行、阴干逆行；土从水（寄申）。
    """
    from app.domains.calendar_core.jiazi import STEMS

    element = stem_element(stem)
    start = CHANG_SHENG_START[element]
    start_index = BRANCHES.index(start)
    branch_index = BRANCHES.index(branch)
    yang = STEMS.index(stem) % 2 == 0
    offset = (branch_index - start_index) % 12 if yang else (start_index - branch_index) % 12
    return CHANG_SHENG_ORDER[offset]


def jian_chu_of(month_branch: str, day_branch: str) -> str:
    """建除十二神：月建之支为「建」，逐支顺推。"""
    offset = (BRANCHES.index(day_branch) - BRANCHES.index(month_branch)) % 12
    return JIAN_CHU_ORDER[offset]
