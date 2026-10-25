"""紫微斗数常量表（三合派单一口径）。

所有表都写成显式常量并附出处说明，便于会审与单测锁定；不在运行期读取外部典籍。
本模块只放「不会变的东西」，任何推导（安星、四化落宫、大限）都在 `engine.py`。
"""

from __future__ import annotations

from app.domains.calendar_core.jiazi import BRANCHES, STEMS
from app.domains.calendar_core.tables import (
    CHANG_SHENG_ORDER,
    CHANG_SHENG_START_BY_BUREAU,
    NA_YIN_30,
)

# ---- 十二宫 ----
#: 从命宫起，按地支逆序（盘面顺时针方向）依次布列
PALACES: tuple[str, ...] = (
    "命宫", "兄弟", "夫妻", "子女", "财帛", "疾厄",
    "迁移", "交友", "官禄", "田宅", "福德", "父母",
)

#: 寅宫在地支表里的下标；「寅起正月」等口诀都以它为基准
YIN_INDEX = BRANCHES.index("寅")

# ---- 五行局 ----
#: 纳音五行 → 局数（水二 / 木三 / 金四 / 土五 / 火六）
BUREAU_BY_ELEMENT: dict[str, int] = {"水": 2, "木": 3, "金": 4, "土": 5, "火": 6}
BUREAU_NAME: dict[int, str] = {2: "水二局", 3: "木三局", 4: "金四局", 5: "土五局", 6: "火六局"}

#: 六十甲子纳音由 calendar_core/tables.py 统一维护（`NA_YIN_30` 已在上方导入）

# ---- 十四主星 ----
#: 紫微星系：紫微定位后逆布。元组第二项是相对紫微宫的位移（负数 = 逆时针）。
ZIWEI_SERIES: tuple[tuple[str, int], ...] = (
    ("紫微", 0),
    ("天机", -1),
    ("太阳", -3),
    ("武曲", -4),
    ("天同", -5),
    ("廉贞", -8),
)
#: 天府星系：天府定位后顺布。
TIANFU_SERIES: tuple[tuple[str, int], ...] = (
    ("天府", 0),
    ("太阴", 1),
    ("贪狼", 2),
    ("巨门", 3),
    ("天相", 4),
    ("天梁", 5),
    ("七杀", 6),
    ("破军", 10),
)
#: 紫微与天府的对称关系常数：`天府 = (TIANFU_MIRROR - 紫微) % 12`
TIANFU_MIRROR = 4

MAIN_STARS: tuple[str, ...] = tuple(name for name, _ in ZIWEI_SERIES) + tuple(
    name for name, _ in TIANFU_SERIES
)

# ---- 辅星 ----
#: 左辅：辰宫起正月顺数至生月
ZUOFU_START = BRANCHES.index("辰")
#: 右弼：戌宫起正月逆数至生月
YOUBI_START = BRANCHES.index("戌")
#: 文昌：戌宫起子时逆数至生时
WENCHANG_START = BRANCHES.index("戌")
#: 文曲：辰宫起子时顺数至生时
WENQU_START = BRANCHES.index("辰")
#: 地劫：亥宫起子时顺行；地空：亥宫起子时逆行
DIJIE_START = BRANCHES.index("亥")

AUX_STARS: tuple[str, ...] = (
    "左辅", "右弼", "文昌", "文曲", "天魁", "天钺", "禄存",
    "擎羊", "陀罗", "火星", "铃星", "地空", "地劫", "天马",
)

# ---- 杂曜（第二轮扩充）----
# 全部只用「年支 / 生月 / 生时」定宫，规则单一、无流派争议；
# 不同流派对部分杂曜的起法有差异的（如解神、天巫）本版本一律不收录，宁缺勿错。
TIAN_XING_START = BRANCHES.index("酉")   # 天刑：酉宫起正月顺数至生月
TIAN_YAO_START = BRANCHES.index("酉")    # 天姚：酉宫起正月逆数至生月
HONG_LUAN_START = BRANCHES.index("卯")   # 红鸾：卯宫起子年逆数至生年支
LONG_CHI_START = BRANCHES.index("辰")    # 龙池：辰宫起子年顺数
FENG_GE_START = BRANCHES.index("戌")     # 凤阁：戌宫起子年逆数
TIAN_KU_START = BRANCHES.index("午")     # 天哭：午宫起子年逆数
TIAN_XU_START = BRANCHES.index("午")     # 天虚：午宫起子年顺数
FEI_LIAN_START = BRANCHES.index("申")    # 蜚廉：申宫起子年顺数
TIAN_DE_START = BRANCHES.index("酉")     # 天德：酉宫起子年顺数
YUE_DE_START = BRANCHES.index("巳")      # 月德：巳宫起子年顺数

#: 华盖：寅午戌见戌、申子辰见辰、巳酉丑见丑、亥卯未见未
HUAGAI_BY_GROUP: dict[str, int] = {"寅午戌": 10, "申子辰": 4, "巳酉丑": 1, "亥卯未": 7}
#: 咸池：寅午戌见卯、申子辰见酉、巳酉丑见午、亥卯未见子
XIANCHI_BY_GROUP: dict[str, int] = {"寅午戌": 3, "申子辰": 9, "巳酉丑": 6, "亥卯未": 0}
#: 孤辰：亥子丑年寅、寅卯辰年巳、巳午未年申、申酉戌年亥
GUCHEN_BY_GROUP: dict[str, int] = {"亥子丑": 2, "寅卯辰": 5, "巳午未": 8, "申酉戌": 11}
#: 寡宿：亥子丑年戌、寅卯辰年丑、巳午未年辰、申酉戌年未
GUASU_BY_GROUP: dict[str, int] = {"亥子丑": 10, "寅卯辰": 1, "巳午未": 4, "申酉戌": 7}
#: 破碎：子午卯酉年巳、寅申巳亥年酉、辰戌丑未年丑
POSUI_BY_TRIO: dict[str, int] = {"子午卯酉": 5, "寅申巳亥": 9, "辰戌丑未": 1}

MINOR_STARS: tuple[str, ...] = (
    "天刑", "天姚", "红鸾", "天喜", "龙池", "凤阁", "天哭", "天虚",
    "蜚廉", "天德", "月德", "华盖", "咸池", "孤辰", "寡宿", "破碎",
)

# ---- 长生十二神 / 博士十二神 ----
#: 顺序与起宫由 calendar_core/tables.py 统一维护
#: 水二局起申、木三局起亥、金四局起巳、土五局起申、火六局起寅
CHANG_SHENG_START: dict[int, int] = CHANG_SHENG_START_BY_BUREAU

#: 博士十二神：禄存宫起博士，方向与大限一致
BO_SHI_ORDER: tuple[str, ...] = (
    "博士", "力士", "青龙", "小耗", "将军", "奏书",
    "飞廉", "喜神", "病符", "大耗", "伏兵", "官府",
)

#: 将前十二神：年支三合定将星，顺行
JIANG_QIAN_ORDER: tuple[str, ...] = (
    "将星", "攀鞍", "岁驿", "息神", "华盖", "劫煞",
    "灾煞", "天煞", "指背", "咸池", "月煞", "亡神",
)
#: 将星起宫：申子辰在子、寅午戌在午、巳酉丑在酉、亥卯未在卯
JIANG_XING_START: dict[str, int] = {"申子辰": 0, "寅午戌": 6, "巳酉丑": 9, "亥卯未": 3}

#: 岁前十二神：年支起岁建，顺行
SUI_QIAN_ORDER: tuple[str, ...] = (
    "岁建", "晦气", "丧门", "贯索", "官符", "小耗",
    "大耗", "龙德", "白虎", "天德", "吊客", "病符",
)

#: 小限最大岁数（展示窗口）
XIAOXIAN_MAX_AGE = 120

#: 天魁天钺：按年干（甲戊庚牛羊，乙己鼠猴乡，丙丁猪鸡位，壬癸兔蛇藏，六辛逢马虎）
KUI_YUE: dict[str, tuple[int, int]] = {
    "甲": (1, 7),   # 丑、未
    "戊": (1, 7),
    "庚": (1, 7),
    "乙": (0, 8),   # 子、申
    "己": (0, 8),
    "丙": (11, 9),  # 亥、酉
    "丁": (11, 9),
    "壬": (3, 5),   # 卯、巳
    "癸": (3, 5),
    "辛": (6, 2),   # 午、寅
}

#: 禄存：按年干
LU_CUN: dict[str, int] = {
    "甲": 2,   # 寅
    "乙": 3,   # 卯
    "丙": 5,   # 巳
    "丁": 6,   # 午
    "戊": 5,   # 巳
    "己": 6,   # 午
    "庚": 8,   # 申
    "辛": 9,   # 酉
    "壬": 11,  # 亥
    "癸": 0,   # 子
}

#: 年支三合组 → 起火/起铃/天马的宫位
#: 火铃起例「寅午戌人丑卯方，申子辰人寅戌扬，巳酉丑人卯戌位，亥卯未人酉戌房」
HUO_XING_START: dict[str, int] = {"寅午戌": 1, "申子辰": 2, "巳酉丑": 3, "亥卯未": 9}
LING_XING_START: dict[str, int] = {"寅午戌": 3, "申子辰": 10, "巳酉丑": 10, "亥卯未": 10}
#: 天马「寅午戌马在申，申子辰马在寅，巳酉丑马在亥，亥卯未马在巳」
TIAN_MA: dict[str, int] = {"寅午戌": 8, "申子辰": 2, "巳酉丑": 11, "亥卯未": 5}

#: 六十甲子四化（三合派通行表）。
#: 庚干四化各派不一（中州派作「太阳、武曲、天府、天同」），本版本采通行说
#: 「太阳、武曲、太阴、天同」，并写入 `docs/口径说明.md`，不做成开关。
SI_HUA: dict[str, dict[str, str]] = {
    "甲": {"禄": "廉贞", "权": "破军", "科": "武曲", "忌": "太阳"},
    "乙": {"禄": "天机", "权": "天梁", "科": "紫微", "忌": "太阴"},
    "丙": {"禄": "天同", "权": "天机", "科": "文昌", "忌": "廉贞"},
    "丁": {"禄": "太阴", "权": "天同", "科": "天机", "忌": "巨门"},
    "戊": {"禄": "贪狼", "权": "太阴", "科": "右弼", "忌": "天机"},
    "己": {"禄": "武曲", "权": "贪狼", "科": "天梁", "忌": "文曲"},
    "庚": {"禄": "太阳", "权": "武曲", "科": "太阴", "忌": "天同"},
    "辛": {"禄": "巨门", "权": "太阳", "科": "文曲", "忌": "文昌"},
    "壬": {"禄": "天梁", "权": "紫微", "科": "左辅", "忌": "武曲"},
    "癸": {"禄": "破军", "权": "巨门", "科": "太阴", "忌": "贪狼"},
}

SCHOOL = "sanhe_default_v1"
SCHOOL_NOTE = (
    "本版本只实现三合派单一口径（安星按《紫微斗数全书》通行法）："
    "庚干四化采「太阳、武曲、太阴、天同」，闰月按本月计，23:00–24:00 按当日之子时计。"
    "其他流派（中州派、飞星派等）一律不支持，也不静默套用。"
)


def branch_index(branch: str) -> int:
    return BRANCHES.index(branch)


def sanhe_group(branch: str) -> str:
    """年支 → 三合组名（用于火星/铃星/天马/华盖/咸池起宫）。"""
    index = branch_index(branch)
    if index in (2, 6, 10):
        return "寅午戌"
    if index in (8, 0, 4):
        return "申子辰"
    if index in (5, 9, 1):
        return "巳酉丑"
    return "亥卯未"


def sanhui_group(branch: str) -> str:
    """年支 → 三会组名（用于孤辰/寡宿起宫）。

    亥子丑（11/0/1）、寅卯辰（2/3/4）、巳午未（5/6/7）、申酉戌（8/9/10）：
    按 `(index + 1) % 12 // 3` 归组，比写 12 条映射更难写错。
    """
    group = ((branch_index(branch) + 1) % 12) // 3
    return ("亥子丑", "寅卯辰", "巳午未", "申酉戌")[group]


def trio_group(branch: str) -> str:
    """年支 → 四正/四生/四墓（破碎起宫用）。

    子午卯酉下标 %3==0，辰戌丑未 %3==1，寅申巳亥 %3==2。
    """
    return ("子午卯酉", "辰戌丑未", "寅申巳亥")[branch_index(branch) % 3]


def nayin_element(stem: str, branch: str) -> str:
    """干支 → 纳音五行。调用方需保证干支是合法组合。"""
    from app.domains.calendar_core.jiazi import jiazi_index

    name = NA_YIN_30[jiazi_index(stem, branch) // 2]
    return name[-1]


def year_stem_is_yang(stem: str) -> bool:
    return STEMS.index(stem) % 2 == 0
