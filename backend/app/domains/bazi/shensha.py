"""四柱神煞（默认 10 类 + 2 类扩展）。

原则与关系规则一致：**只报「哪个神煞落在哪一柱」，不做好坏判断**。
神煞不参与 `rule_id` 校验，也不进入 AI 的 `triggered_rules`，只作为盘面事实展示。

口径：
- 起法以「日干」为主（天乙、太极、文昌、福星、金舆），年支三合/三会定华盖、寡宿、六厄；
- 天德、月德按月支（与节气定月一致）；
- 六秀日、金神是固定干支组合，直接比日柱/时柱；
- 童子、勾绞流派分歧大，默认不启用（`variant="extended"` 才计算），并在 warnings 声明。
"""

from __future__ import annotations

from typing import Any

# 天乙贵人：甲戊庚牛羊，乙己鼠猴乡，丙丁猪鸡位，壬癸兔蛇藏，六辛逢马虎
TIAN_YI: dict[str, tuple[str, ...]] = {
    "甲": ("丑", "未"), "戊": ("丑", "未"), "庚": ("丑", "未"),
    "乙": ("子", "申"), "己": ("子", "申"),
    "丙": ("亥", "酉"), "丁": ("亥", "酉"),
    "壬": ("卯", "巳"), "癸": ("卯", "巳"),
    "辛": ("午", "寅"),
}

# 太极贵人：甲乙子午，丙丁卯酉，戊己辰戌丑未，庚辛寅亥，壬癸巳申
TAI_JI: dict[str, tuple[str, ...]] = {
    "甲": ("子", "午"), "乙": ("子", "午"),
    "丙": ("卯", "酉"), "丁": ("卯", "酉"),
    "戊": ("辰", "戌", "丑", "未"), "己": ("辰", "戌", "丑", "未"),
    "庚": ("寅", "亥"), "辛": ("寅", "亥"),
    "壬": ("巳", "申"), "癸": ("巳", "申"),
}

# 文昌贵人
WEN_CHANG: dict[str, str] = {
    "甲": "巳", "乙": "午", "丙": "申", "丁": "酉", "戊": "申",
    "己": "酉", "庚": "亥", "辛": "子", "壬": "寅", "癸": "卯",
}

# 福星贵人：甲丙寅子，乙癸丑卯，戊申己未，丁亥，庚午，辛巳，壬辰
FU_XING: dict[str, tuple[str, ...]] = {
    "甲": ("寅", "子"), "丙": ("寅", "子"),
    "乙": ("丑", "卯"), "癸": ("丑", "卯"),
    "戊": ("申",), "己": ("未",), "丁": ("亥",),
    "庚": ("午",), "辛": ("巳",), "壬": ("辰",),
}

# 金舆：甲龙乙蛇丙戊羊，丁己猴，庚犬辛猪壬牛癸虎
JIN_YU: dict[str, str] = {
    "甲": "辰", "乙": "巳", "丙": "未", "丁": "申", "戊": "未",
    "己": "申", "庚": "戌", "辛": "亥", "壬": "丑", "癸": "寅",
}

# 华盖：寅午戌见戌、申子辰见辰、巳酉丑见丑、亥卯未见未
HUA_GAI: dict[str, str] = {"寅午戌": "戌", "申子辰": "辰", "巳酉丑": "丑", "亥卯未": "未"}
# 寡宿：亥子丑见戌、寅卯辰见丑、巳午未见辰、申酉戌见未
GUA_SU: dict[str, str] = {"亥子丑": "戌", "寅卯辰": "丑", "巳午未": "辰", "申酉戌": "未"}
# 六厄：申子辰见卯、寅午戌见酉、巳酉丑见午、亥卯未见子
LIU_E: dict[str, str] = {"申子辰": "卯", "寅午戌": "酉", "巳酉丑": "午", "亥卯未": "子"}

# 天德（按月支）：寅丁、卯申、辰壬、巳辛、午亥、未甲、申癸、酉寅、戌丙、亥乙、子巳、丑庚
TIAN_DE: dict[str, str] = {
    "寅": "丁", "卯": "申", "辰": "壬", "巳": "辛", "午": "亥", "未": "甲",
    "申": "癸", "酉": "寅", "戌": "丙", "亥": "乙", "子": "巳", "丑": "庚",
}
# 月德（按月支三合）：寅午戌丙、申子辰壬、亥卯未甲、巳酉丑庚
YUE_DE: dict[str, str] = {"寅午戌": "丙", "申子辰": "壬", "亥卯未": "甲", "巳酉丑": "庚"}

STEM_HE = {"甲": "己", "己": "甲", "乙": "庚", "庚": "乙", "丙": "辛", "辛": "丙", "丁": "壬", "壬": "丁", "戊": "癸", "癸": "戊"}
BRANCH_HE = {"子": "丑", "丑": "子", "寅": "亥", "亥": "寅", "卯": "戌", "戌": "卯", "辰": "酉", "酉": "辰", "巳": "申", "申": "巳", "午": "未", "未": "午"}

# 六秀日 / 金神（固定组合）
LIU_XIU_DAYS = {"丙午", "丁未", "戊子", "戊午", "己丑", "己未"}
JIN_SHEN = {"乙丑", "己巳", "癸酉"}

POSITIONS = ("year", "month", "day", "hour")
POSITION_NAMES = {"year": "年柱", "month": "月柱", "day": "日柱", "hour": "时柱"}


def _sanhe(branch: str) -> str:
    index = "子丑寅卯辰巳午未申酉戌亥".index(branch)
    if index in (2, 6, 10):
        return "寅午戌"
    if index in (8, 0, 4):
        return "申子辰"
    if index in (5, 9, 1):
        return "巳酉丑"
    return "亥卯未"


def _sanhui(branch: str) -> str:
    index = "子丑寅卯辰巳午未申酉戌亥".index(branch)
    return ("亥子丑", "寅卯辰", "巳午未", "申酉戌")[((index + 1) % 12) // 3]


def _match(
    pillars: dict[str, dict[str, Any]],
    targets: set[str],
    *,
    field: str,
) -> list[str]:
    return [
        position
        for position in POSITIONS
        if pillars.get(position, {}).get(field) in targets
    ]


def compute(
    pillars: dict[str, dict[str, Any]],
    *,
    variant: str = "common",
) -> dict[str, Any]:
    """返回 `{items, by_pillar, variant}`；items 只含命中的神煞。"""
    day = pillars.get("day", {})
    year = pillars.get("year", {})
    month = pillars.get("month", {})
    day_stem = day.get("stem", "")
    year_branch = year.get("branch", "")
    month_branch = month.get("branch", "")

    items: list[dict[str, Any]] = []

    def emit(name: str, targets: set[str], *, field: str, basis: str, source: str) -> None:
        positions = _match(pillars, targets, field=field)
        if positions:
            items.append(
                {
                    "name": name,
                    "positions": positions,
                    "basis": basis,
                    "source_ref": source,
                }
            )

    if day_stem in TIAN_YI:
        emit("天乙贵人", set(TIAN_YI[day_stem]), field="branch", basis="日干", source="bazi.shensha.tianyi")
    if day_stem in TAI_JI:
        emit("太极贵人", set(TAI_JI[day_stem]), field="branch", basis="日干", source="bazi.shensha.taiji")
    if day_stem in WEN_CHANG:
        emit("文昌贵人", {WEN_CHANG[day_stem]}, field="branch", basis="日干", source="bazi.shensha.wenchang")
    if day_stem in FU_XING:
        emit("福星贵人", set(FU_XING[day_stem]), field="branch", basis="日干", source="bazi.shensha.fuxing")
    if day_stem in JIN_YU:
        emit("金舆", {JIN_YU[day_stem]}, field="branch", basis="日干", source="bazi.shensha.jinyu")

    if year_branch:
        emit("华盖", {HUA_GAI[_sanhe(year_branch)]}, field="branch", basis="年支三合", source="bazi.shensha.huagai")
        emit("寡宿", {GUA_SU[_sanhui(year_branch)]}, field="branch", basis="年支三会", source="bazi.shensha.guasu")
        emit("六厄", {LIU_E[_sanhe(year_branch)]}, field="branch", basis="年支三合", source="bazi.shensha.liue")

    if month_branch:
        tian_de = TIAN_DE.get(month_branch)
        if tian_de:
            if tian_de in STEM_HE:
                emit("天德合", {STEM_HE[tian_de]}, field="stem", basis="月支天德之合", source="bazi.shensha.tiande")
            else:
                emit("天德合", {BRANCH_HE[tian_de]}, field="branch", basis="月支天德之合", source="bazi.shensha.tiande")
        yue_de = YUE_DE.get(_sanhe(month_branch))
        if yue_de:
            emit("月德合", {STEM_HE[yue_de]}, field="stem", basis="月支月德之合", source="bazi.shensha.yuede")

    day_text = f"{day.get('stem', '')}{day.get('branch', '')}"
    if day_text in LIU_XIU_DAYS:
        items.append(
            {
                "name": "六秀日",
                "positions": ["day"],
                "basis": "日柱固定组合",
                "source_ref": "bazi.shensha.liuxiu",
            }
        )
    for position in ("day", "hour"):
        text = f"{pillars.get(position, {}).get('stem', '')}{pillars.get(position, {}).get('branch', '')}"
        if text in JIN_SHEN:
            items.append(
                {
                    "name": "金神",
                    "positions": [position],
                    "basis": "日/时柱固定组合",
                    "source_ref": "bazi.shensha.jinshen",
                }
            )

    if variant == "extended":
        # 起法有分歧，默认不启用；启用时同时在 warnings 里说明
        if year_branch:
            front = "子丑寅卯辰巳午未申酉戌亥"[("子丑寅卯辰巳午未申酉戌亥".index(year_branch) + 3) % 12]
            items.append(
                {
                    "name": "勾绞",
                    "positions": _match(pillars, {front}, field="branch"),
                    "basis": "年支顺数三位（一派做法）",
                    "source_ref": "bazi.shensha.goujiao",
                    "variant": True,
                }
            )
        if day_text in {"甲子", "乙丑", "丙寅", "丁卯", "戊辰", "己巳", "庚午", "辛未", "壬申", "癸酉"}:
            items.append(
                {
                    "name": "童子",
                    "positions": ["day"],
                    "basis": "按日柱纳音一派做法",
                    "source_ref": "bazi.shensha.tongzi",
                    "variant": True,
                }
            )

    by_pillar: dict[str, list[str]] = {position: [] for position in POSITIONS}
    for item in items:
        for position in item["positions"]:
            by_pillar[position].append(item["name"])
    for name in by_pillar:
        by_pillar[name] = sorted(set(by_pillar[name]))

    return {"items": items, "by_pillar": by_pillar, "variant": variant}
