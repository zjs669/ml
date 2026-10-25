"""六爻常量表（京房纳甲单一口径）。

全部写成显式常量并附出处说明，运行期不读任何外部文件、不依赖排盘库。
推导逻辑一律放在 `engine.py`，本模块只放"不会变的东西"。

八卦的二进制表示统一为 **自下而上** 的三位：`1` 为阳爻，`0` 为阴爻。
例：乾 `111`、兑 `110`（初阳、二阳、三阴）、艮 `001`（初阴、二阴、三阳）。
"""

from __future__ import annotations

from app.domains.calendar_core.jiazi import (
    BRANCHES,
    BRANCH_ELEMENT,
    ELEMENTS,
    STEMS,
    STEM_ELEMENT,
)

# ---- 八卦 ----
#: 自下而上的三爻二进制；次序与「先天八卦数」无关，只表示爻象
TRIGRAM_BITS: dict[str, str] = {
    "乾": "111",
    "兑": "110",
    "离": "101",
    "震": "100",
    "巽": "011",
    "坎": "010",
    "艮": "001",
    "坤": "000",
}

#: 先天八卦数（梅花易数时间起卦用）：乾一 兑二 离三 震四 巽五 坎六 艮七 坤八
XIAN_TIAN_NUMBER: dict[int, str] = {
    1: "乾", 2: "兑", 3: "离", 4: "震", 5: "巽", 6: "坎", 7: "艮", 8: "坤",
}

#: 八卦所属五行（八宫五行同此）
TRIGRAM_ELEMENT: dict[str, str] = {
    "乾": "金", "兑": "金", "离": "火", "震": "木",
    "巽": "木", "坎": "水", "艮": "土", "坤": "土",
}

#: 京房八宫次序（决定「宫」的排列顺序，不决定卦的归属，归属见 hexagrams.py）
PALACE_ORDER: tuple[str, ...] = ("乾", "兑", "离", "震", "巽", "坎", "艮", "坤")

#: 八宫卦序中每一卦的世爻位置（1=初爻 … 6=上爻）
#: 次序：本宫(八纯)、一世、二世、三世、四世、五世、游魂、归魂
SHI_BY_INDEX: tuple[int, ...] = (6, 1, 2, 3, 4, 5, 4, 3)
PHASE_BY_INDEX: tuple[str, ...] = ("本宫", "一世", "二世", "三世", "四世", "五世", "游魂", "归魂")

#: 卦位 → 规则 ID 片段（规则 ID 一律 ASCII，便于日志检索与跨语言引用）
PHASE_SLUG: dict[str, str] = {
    "本宫": "pure",
    "一世": "first",
    "二世": "second",
    "三世": "third",
    "四世": "fourth",
    "五世": "fifth",
    "游魂": "youhun",
    "归魂": "guihun",
}

# ---- 纳甲 ----
#: 内卦（下卦，初二三爻）纳甲。出处：《增删卜易》《卜筮正宗》通行纳甲表
NAJIA_INNER: dict[str, tuple[str, str, str]] = {
    "乾": ("甲子", "甲寅", "甲辰"),
    "兑": ("丁巳", "丁卯", "丁丑"),
    "离": ("己卯", "己丑", "己亥"),
    "震": ("庚子", "庚寅", "庚辰"),
    "巽": ("辛丑", "辛亥", "辛酉"),
    "坎": ("戊寅", "戊辰", "戊午"),
    "艮": ("丙辰", "丙午", "丙申"),
    "坤": ("乙未", "乙巳", "乙卯"),
}

#: 外卦（上卦，四五上爻）纳甲
NAJIA_OUTER: dict[str, tuple[str, str, str]] = {
    "乾": ("壬午", "壬申", "壬戌"),
    "兑": ("丁亥", "丁酉", "丁未"),
    "离": ("己酉", "己未", "己巳"),
    "震": ("庚午", "庚申", "庚戌"),
    "巽": ("辛未", "辛巳", "辛卯"),
    "坎": ("戊申", "戊戌", "戊子"),
    "艮": ("丙戌", "丙子", "丙寅"),
    "坤": ("癸丑", "癸亥", "癸酉"),
}

# ---- 六亲 ----
#: 六亲名称（按生克关系推出，见 `six_relation`）
SIX_RELATIONS: tuple[str, ...] = ("父母", "兄弟", "子孙", "妻财", "官鬼")

# ---- 六神（六兽）----
LIU_SHEN: tuple[str, ...] = ("青龙", "朱雀", "勾陈", "螣蛇", "白虎", "玄武")

#: 日干 → 初爻所起六神的下标（甲乙青龙、丙丁朱雀、戊勾陈、己螣蛇、庚辛白虎、壬癸玄武）
LIU_SHEN_START: dict[str, int] = {
    "甲": 0, "乙": 0,
    "丙": 1, "丁": 1,
    "戊": 2,
    "己": 3,
    "庚": 4, "辛": 4,
    "壬": 5, "癸": 5,
}

# ---- 起卦法 ----
METHODS: tuple[str, ...] = ("coins", "time", "manual")
METHOD_LABELS: dict[str, str] = {
    "coins": "三枚铜钱（可复现随机种子）",
    "time": "时间起卦（梅花易数取数法）",
    "manual": "手动输入六爻（6/7/8/9）",
}

SCHOOL = "jingfang_najia_v1"
SCHOOL_NOTE = (
    "本版本只实现京房纳甲单一口径：以时间定月建日辰与旬空，"
    "六亲以本卦卦宫五行为「我」推算（变爻六亲同样对照本卦卦宫），"
    "六神按日干起于初爻顺排。时间起卦沿用梅花易数的「年支+月+日」「再加时支」取数与"
    "单动爻规则，与铜钱起卦的多动爻不同；如需多爻动请用铜钱或手动输入。"
)


def trigram_bits(trigram: str) -> str:
    return TRIGRAM_BITS[trigram]


def six_relation(palace_element: str, branch_element: str) -> str:
    """本卦卦宫五行与爻支五行的生克 → 六亲。

    同我兄弟、生我父母、我生子孙、克我官鬼、我克妻财。
    以乾宫（金）为例：子水子孙、寅木妻财、辰土父母、午火官鬼、申金兄弟，
    与《卜筮正宗》乾卦纳甲六亲一致。
    """
    me = ELEMENTS.index(palace_element)
    other = ELEMENTS.index(branch_element)
    if me == other:
        return "兄弟"
    if (other + 1) % 5 == me:  # 生我
        return "父母"
    if (me + 1) % 5 == other:  # 我生
        return "子孙"
    if (other + 2) % 5 == me:  # 克我
        return "官鬼"
    return "妻财"


def najia_of(upper: str, lower: str) -> tuple[str, ...]:
    """六爻纳甲（自下而上）：下卦三爻取内卦表，上卦三爻取外卦表。"""
    return tuple(NAJIA_INNER[lower]) + tuple(NAJIA_OUTER[upper])


def liu_shen_of(day_stem: str) -> tuple[str, ...]:
    """六神自初爻至上爻的排列（依赖日干，不依赖日支）。"""
    start = LIU_SHEN_START[day_stem]
    return tuple(LIU_SHEN[(start + index) % 6] for index in range(6))


def xun_kong(day_index: int) -> tuple[str, str]:
    """日柱所在旬的空亡二支。六十甲子每旬十日，余下两个地支即旬空。"""
    start = (day_index // 10) * 10
    covered = {BRANCHES[(start + offset) % 12] for offset in range(10)}
    missing = [branch for branch in BRANCHES if branch not in covered]
    return missing[0], missing[1]


def branch_element_of(najia: str) -> str:
    return BRANCH_ELEMENT[najia[1]]


def stem_element_of(najia: str) -> str:
    return STEM_ELEMENT[najia[0]]


__all__ = [
    "BRANCHES",
    "STEMS",
    "TRIGRAM_BITS",
    "XIAN_TIAN_NUMBER",
    "TRIGRAM_ELEMENT",
    "PALACE_ORDER",
    "SHI_BY_INDEX",
    "PHASE_BY_INDEX",
    "PHASE_SLUG",
    "NAJIA_INNER",
    "NAJIA_OUTER",
    "SIX_RELATIONS",
    "LIU_SHEN",
    "LIU_SHEN_START",
    "METHODS",
    "METHOD_LABELS",
    "SCHOOL",
    "SCHOOL_NOTE",
    "trigram_bits",
    "six_relation",
    "najia_of",
    "liu_shen_of",
    "xun_kong",
    "branch_element_of",
    "stem_element_of",
]
