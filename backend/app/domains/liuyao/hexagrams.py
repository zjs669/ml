"""六十四卦数据：卦名、所属宫、世应、纳甲六亲。

数据写成两张表，两者互为交叉校验：

1. `HEXAGRAM_TABLE[上卦][下卦] = 卦名` —— 8×8 共 64 个组合；
2. `PALACE_SEQUENCE[宫] = (本宫, 一世, 二世, 三世, 四世, 五世, 游魂, 归魂)` ——
   京房八宫卦序，决定每卦归哪一宫、世应落在第几爻。

导入时立即校验：两张表必须是同一批 64 个卦名且无重复。
任何一边写错都会在启动时报错，而不是等排盘时算出一张奇怪的盘。
`tests/test_liuyao_engine.py` 另有一组独立推导（按变爻法重建八宫）做第二重校验。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domains.liuyao import constants as C

#: 上卦 → 下卦 → 卦名（八经卦自重者写作「乾为天」这类全称）
HEXAGRAM_TABLE: dict[str, dict[str, str]] = {
    "乾": {
        "乾": "乾为天", "兑": "天泽履", "离": "天火同人", "震": "天雷无妄",
        "巽": "天风姤", "坎": "天水讼", "艮": "天山遁", "坤": "天地否",
    },
    "兑": {
        "乾": "泽天夬", "兑": "兑为泽", "离": "泽火革", "震": "泽雷随",
        "巽": "泽风大过", "坎": "泽水困", "艮": "泽山咸", "坤": "泽地萃",
    },
    "离": {
        "乾": "火天大有", "兑": "火泽睽", "离": "离为火", "震": "火雷噬嗑",
        "巽": "火风鼎", "坎": "火水未济", "艮": "火山旅", "坤": "火地晋",
    },
    "震": {
        "乾": "雷天大壮", "兑": "雷泽归妹", "离": "雷火丰", "震": "震为雷",
        "巽": "雷风恒", "坎": "雷水解", "艮": "雷山小过", "坤": "雷地豫",
    },
    "巽": {
        "乾": "风天小畜", "兑": "风泽中孚", "离": "风火家人", "震": "风雷益",
        "巽": "巽为风", "坎": "风水涣", "艮": "风山渐", "坤": "风地观",
    },
    "坎": {
        "乾": "水天需", "兑": "水泽节", "离": "水火既济", "震": "水雷屯",
        "巽": "水风井", "坎": "坎为水", "艮": "水山蹇", "坤": "水地比",
    },
    "艮": {
        "乾": "山天大畜", "兑": "山泽损", "离": "山火贲", "震": "山雷颐",
        "巽": "山风蛊", "坎": "山水蒙", "艮": "艮为山", "坤": "山地剥",
    },
    "坤": {
        "乾": "地天泰", "兑": "地泽临", "离": "地火明夷", "震": "地雷复",
        "巽": "地风升", "坎": "地水师", "艮": "地山谦", "坤": "坤为地",
    },
}

#: 京房八宫卦序（本宫、一世、二世、三世、四世、五世、游魂、归魂）
PALACE_SEQUENCE: dict[str, tuple[str, ...]] = {
    "乾": ("乾为天", "天风姤", "天山遁", "天地否", "风地观", "山地剥", "火地晋", "火天大有"),
    "兑": ("兑为泽", "泽水困", "泽地萃", "泽山咸", "水山蹇", "地山谦", "雷山小过", "雷泽归妹"),
    "离": ("离为火", "火山旅", "火风鼎", "火水未济", "山水蒙", "风水涣", "天水讼", "天火同人"),
    "震": ("震为雷", "雷地豫", "雷水解", "雷风恒", "地风升", "水风井", "泽风大过", "泽雷随"),
    "巽": ("巽为风", "风天小畜", "风火家人", "风雷益", "天雷无妄", "火雷噬嗑", "山雷颐", "山风蛊"),
    "坎": ("坎为水", "水泽节", "水雷屯", "水火既济", "泽火革", "雷火丰", "地火明夷", "地水师"),
    "艮": ("艮为山", "山火贲", "山天大畜", "山泽损", "火泽睽", "天泽履", "风泽中孚", "风山渐"),
    "坤": ("坤为地", "地雷复", "地泽临", "地天泰", "雷天大壮", "泽天夬", "水天需", "水地比"),
}


@dataclass(frozen=True)
class HexagramInfo:
    name: str
    upper: str
    lower: str
    palace: str
    palace_element: str
    phase: str
    shi: int
    ying: int

    @property
    def bits(self) -> str:
        """自下而上的六爻二进制：下卦三爻 + 上卦三爻。"""
        return C.TRIGRAM_BITS[self.lower] + C.TRIGRAM_BITS[self.upper]


def _build_indexes() -> tuple[dict[str, tuple[str, str]], dict[str, HexagramInfo]]:
    by_name: dict[str, tuple[str, str]] = {}
    for upper, row in HEXAGRAM_TABLE.items():
        if len(row) != 8:
            raise RuntimeError(f"{upper}卦一行的下卦不齐")
        for lower, name in row.items():
            if name in by_name:
                raise RuntimeError(f"卦名重复：{name}")
            by_name[name] = (upper, lower)

    infos: dict[str, HexagramInfo] = {}
    for palace, names in PALACE_SEQUENCE.items():
        if len(names) != 8:
            raise RuntimeError(f"{palace}宫卦序数量不为 8")
        for index, name in enumerate(names):
            if name not in by_name:
                raise RuntimeError(f"{palace}宫的「{name}」不在六十四卦表内")
            upper, lower = by_name[name]
            shi = C.SHI_BY_INDEX[index]
            ying = shi + 3 if shi <= 3 else shi - 3
            infos[name] = HexagramInfo(
                name=name,
                upper=upper,
                lower=lower,
                palace=palace,
                palace_element=C.TRIGRAM_ELEMENT[palace],
                phase=C.PHASE_BY_INDEX[index],
                shi=shi,
                ying=ying,
            )

    if len(by_name) != 64:
        raise RuntimeError(f"六十四卦数量不对：{len(by_name)}")
    if set(by_name) != set(infos):
        raise RuntimeError(
            "卦名表与八宫卦序不一致：" f"仅见于卦名表 {sorted(set(by_name) - set(infos))}，"
            f"仅见于八宫序 {sorted(set(infos) - set(by_name))}"
        )
    return by_name, infos


NAME_TO_TRIGRAMS, NAME_TO_INFO = _build_indexes()


def hexagram_of(upper: str, lower: str) -> HexagramInfo:
    name = HEXAGRAM_TABLE[upper][lower]
    return NAME_TO_INFO[name]


def hexagram_from_bits(bits: str) -> HexagramInfo:
    """六爻二进制（自下而上，1=阳）→ 卦信息。"""
    if len(bits) != 6 or set(bits) - {"0", "1"}:
        raise ValueError(f"需要 6 位 0/1，收到 {bits!r}")
    lower = next(name for name, value in C.TRIGRAM_BITS.items() if value == bits[:3])
    upper = next(name for name, value in C.TRIGRAM_BITS.items() if value == bits[3:])
    return hexagram_of(upper, lower)


def bits_of(name: str) -> str:
    return NAME_TO_INFO[name].bits


def lines_payload(info: HexagramInfo, *, day_stem: str, palace_element: str | None = None) -> list[dict[str, Any]]:
    """把一卦摊成六爻（自下而上），带纳甲、六亲、六神、世应。

    `palace_element` 允许外部指定：变卦的六亲仍以**本卦**卦宫为准，
    因此变卦不能用自己的宫五行去算六亲。
    """
    element = palace_element or info.palace_element
    najia = C.najia_of(info.upper, info.lower)
    shen = C.liu_shen_of(day_stem)
    lines: list[dict[str, Any]] = []
    for index, value in enumerate(info.bits):
        position = index + 1
        text = najia[index]
        branch_element = C.branch_element_of(text)
        lines.append(
            {
                "position": position,
                "polarity": "阳" if value == "1" else "阴",
                "najia": text,
                "stem": text[0],
                "branch": text[1],
                "element": branch_element,
                "six_relation": C.six_relation(element, branch_element),
                "liu_shen": shen[index],
                "shi": position == info.shi,
                "ying": position == info.ying,
            }
        )
    return lines
