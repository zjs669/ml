"""紫微斗数引擎（三合派单一口径）。

对外唯一入口 `calculate(inp, conv)`，返回与四柱同构的 `ChartResult`。
只输出盘面事实（宫位、星曜、四化、大限）与结构性标记，不做吉凶判断。

安星顺序固定，任何一步都不能交换——后面的步骤依赖前面的结果：

1. 定农历（公历先转农历）→ 取农历月、日、时支
2. 寅起正月顺数至生月，再逆数至生时安命宫；顺数至生时安身宫
3. 年干五虎遁得十二宫天干，命宫纳音五行定五行局
4. 五行局 + 生日定紫微宫
5. 紫微星系逆布、天府星系顺布，共十四主星
6. 按年干/年支/生月/生时安十四辅星
7. 年干四化落宫
8. 命宫起逆布十二宫名，按阴阳男女排大限
"""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings
from app.domains.bazi.schemas import ChartResult
from app.domains.calendar_core.jiazi import (
    BRANCHES,
    MONTH_STEM_START,
    STEMS,
    hour_branch,
)
from app.domains.calendar_core.lunar import LunarDate, lunar_to_solar, solar_to_lunar
from app.domains.ziwei import constants as C
from app.domains.ziwei.schemas import ZiweiConvention, ZiweiInput

PLACEHOLDER_HOUR = 12
DAYUN_SPAN = 10


def _resolve_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"未知时区: {name}（需要安装 tzdata）") from exc


def _ziwei_index(bureau: int, day: int) -> int:
    """紫微星定位：把日数补到能被局数整除，商数自寅顺数，补数按奇偶进退。

    例：水二局初一 → 补 1、商 1，寅位退一宫 → 丑；土五局初一 → 补 4、商 1，寅位进四宫 → 午。
    """
    extra = (bureau - day % bureau) % bureau
    quotient = (day + extra) // bureau
    base = C.YIN_INDEX + quotient - 1
    step = extra if extra % 2 == 0 else -extra
    return (base + step) % 12


def _palace_stem(year_stem: str, index: int) -> str:
    """五虎遁：年干定寅宫天干，其余宫按十二宫顺序顺推。

    注意必须先把位移落回 0–11（十二宫一圈），再压缩到十干：
    子宫与丑宫在寅之前，直接对负数取模会错开两位（会把子错成壬）。
    """
    start = STEMS.index(MONTH_STEM_START[year_stem])
    offset = (index - C.YIN_INDEX) % 12
    return STEMS[(start + offset) % 10]


def _dayun_forward(year_stem: str, gender: str) -> tuple[bool, str | None]:
    """阳男阴女顺行，阴男阳女逆行。性别未知时退回「阳年顺、阴年逆」并给出提示。"""
    yang = C.year_stem_is_yang(year_stem)
    if gender == "unknown":
        return yang, "性别未知：大限方向按「阳年顺行、阴年逆行」占位，请补充性别以获得确定排布。"
    return (yang and gender == "male") or (not yang and gender == "female"), None


def _stars(
    year_stem: str,
    year_branch: str,
    month: int,
    hour_index: int,
    ziwei: int,
) -> dict[int, list[str]]:
    """按固定顺序安十四主星与十四辅星，返回 宫位下标 → 星曜名列表。"""
    placed: dict[int, list[str]] = {index: [] for index in range(12)}

    for name, offset in C.ZIWEI_SERIES:
        placed[(ziwei + offset) % 12].append(name)
    tianfu = (C.TIANFU_MIRROR - ziwei) % 12
    for name, offset in C.TIANFU_SERIES:
        placed[(tianfu + offset) % 12].append(name)

    # 生月系：左辅顺、右弼逆
    placed[(C.ZUOFU_START + month - 1) % 12].append("左辅")
    placed[(C.YOUBI_START - (month - 1)) % 12].append("右弼")
    # 生时系：文昌逆、文曲顺
    placed[(C.WENCHANG_START - hour_index) % 12].append("文昌")
    placed[(C.WENQU_START + hour_index) % 12].append("文曲")
    # 年干系：天魁天钺、禄存及其前后一宫为擎羊陀罗
    kui, yue = C.KUI_YUE[year_stem]
    placed[kui].append("天魁")
    placed[yue].append("天钺")
    lucun = C.LU_CUN[year_stem]
    placed[lucun].append("禄存")
    placed[(lucun + 1) % 12].append("擎羊")
    placed[(lucun - 1) % 12].append("陀罗")
    # 年支三合 + 生时系：火星、铃星、天马
    group = C.sanhe_group(year_branch)
    placed[(C.HUO_XING_START[group] + hour_index) % 12].append("火星")
    placed[(C.LING_XING_START[group] + hour_index) % 12].append("铃星")
    placed[C.TIAN_MA[group]].append("天马")
    # 生时系：地劫顺、地空逆
    placed[(C.DIJIE_START + hour_index) % 12].append("地劫")
    placed[(C.DIJIE_START - hour_index) % 12].append("地空")

    return placed


def _minor_stars(year_branch: str, month: int) -> dict[int, list[str]]:
    """杂曜：全部由年支或生月定宫，起法见 `constants.py` 注释。"""
    placed: dict[int, list[str]] = {index: [] for index in range(12)}
    year_index = BRANCHES.index(year_branch)
    month_offset = month - 1

    def put(index: int, name: str) -> None:
        placed[index % 12].append(name)

    # 生月系：酉宫起正月，天刑顺、天姚逆
    put(C.TIAN_XING_START + month_offset, "天刑")
    put(C.TIAN_YAO_START - month_offset, "天姚")
    # 年支系：顺逆各半，天喜恒为红鸾对宫
    hong_luan = (C.HONG_LUAN_START - year_index) % 12
    put(hong_luan, "红鸾")
    put(hong_luan + 6, "天喜")
    put(C.LONG_CHI_START + year_index, "龙池")
    put(C.FENG_GE_START - year_index, "凤阁")
    put(C.TIAN_KU_START - year_index, "天哭")
    put(C.TIAN_XU_START + year_index, "天虚")
    put(C.FEI_LIAN_START + year_index, "蜚廉")
    put(C.TIAN_DE_START + year_index, "天德")
    put(C.YUE_DE_START + year_index, "月德")
    # 年支三合 / 三会 / 四正四生四墓
    sanhe = C.sanhe_group(year_branch)
    put(C.HUAGAI_BY_GROUP[sanhe], "华盖")
    put(C.XIANCHI_BY_GROUP[sanhe], "咸池")
    sanhui = C.sanhui_group(year_branch)
    put(C.GUCHEN_BY_GROUP[sanhui], "孤辰")
    put(C.GUASU_BY_GROUP[sanhui], "寡宿")
    put(C.POSUI_BY_TRIO[C.trio_group(year_branch)], "破碎")
    return placed


def _life_cycle(bureau: int, forward: bool) -> dict[int, str]:
    """长生十二神：局数定起宫，方向同大限。"""
    start = C.CHANG_SHENG_START[bureau]
    placed: dict[int, str] = {}
    for step, name in enumerate(C.CHANG_SHENG_ORDER):
        index = (start + step) % 12 if forward else (start - step) % 12
        placed[index] = name
    return placed


def _bo_shi(lucun: int, forward: bool) -> dict[int, str]:
    """博士十二神：禄存宫起博士，方向同大限。"""
    placed: dict[int, str] = {}
    for step, name in enumerate(C.BO_SHI_ORDER):
        index = (lucun + step) % 12 if forward else (lucun - step) % 12
        placed[index] = name
    return placed


def _transformations_for(
    stem: str, star_palace: dict[str, int], life: int
) -> list[dict[str, Any]]:
    """按某个天干推四化，返回「化什么星、落在哪个宫」的事实。"""
    rows: list[dict[str, Any]] = []
    for kind, star in C.SI_HUA[stem].items():
        target = star_palace.get(star)
        if target is None:  # 该星不在本盘（本版本不会发生，防御式保留）
            continue
        rows.append(
            {
                "type": kind,
                "star": star,
                "palace": C.PALACES[(life - target) % 12],
                "branch": BRANCHES[target],
            }
        )
    return rows


def _palace_transformations(
    palaces: list[dict[str, Any]], star_palace: dict[str, int], life: int
) -> list[dict[str, Any]]:
    """宫干四化：每个宫的天干各推一组，共 12 组。"""
    rows: list[dict[str, Any]] = []
    for palace in palaces:
        stem = palace["heavenly_stem"]
        for item in _transformations_for(stem, star_palace, life):
            rows.append(
                {
                    "from_palace": palace["name"],
                    "stem": stem,
                    "type": item["type"],
                    "star": item["star"],
                    "to_palace": item["palace"],
                    "to_branch": item["branch"],
                }
            )
    return rows


def _dayun_transformation(
    dayun: list[dict[str, Any]],
    review_age: int,
    year_stem: str,
    star_palace: dict[str, int],
    life: int,
) -> dict[str, Any] | None:
    """大限四化：取该年龄所在大限宫的宫干。年龄超出 12 个大限则不猜。"""
    for item in dayun:
        if item["start_age"] <= review_age <= item["end_age"]:
            index = BRANCHES.index(item["branch"])
            stem = _palace_stem(year_stem, index)
            return {
                "age": review_age,
                "palace": item["palace"],
                "branch": item["branch"],
                "stem": stem,
                "items": _transformations_for(stem, star_palace, life),
            }
    return None


def _liunian_transformation(
    review_year: int, star_palace: dict[str, int], life: int
) -> dict[str, Any]:
    """流年四化：review_year 按**农历年**理解，年干支由 (year - 4) % 60 得出。"""
    cycle = (review_year - 4) % 60
    stem = STEMS[cycle % 10]
    branch = BRANCHES[cycle % 12]
    index = BRANCHES.index(branch)
    return {
        "year": review_year,
        "ganzhi": f"{stem}{branch}",
        "palace": C.PALACES[(life - index) % 12],
        "branch": branch,
        "stem": stem,
        "items": _transformations_for(stem, star_palace, life),
    }


def _markers(
    *,
    palaces: list[dict[str, Any]],
    transformations: list[dict[str, Any]],
    life: int,
    body: int,
) -> list[dict[str, Any]]:
    """结构性标记：只描述「什么落在哪里」，不评价好坏。"""
    life_palace = palaces[0]
    life_stars = life_palace["stars"]
    markers: list[dict[str, Any]] = []

    def emit(
        rule_id: str,
        relation: str,
        label: str,
        members: list[str],
        note: str,
        priority: int,
    ) -> None:
        markers.append(
            {
                "rule_id": rule_id,
                "system": "ziwei",
                "kind": "placement",
                "relation": relation,
                "members": members,
                "topic": "structure",
                "priority": priority,
                "note": note,
                "source_ref": "ziwei.quanshu",
                "version": settings.ziwei_algorithm_version,
                "scope": "palace",
                "positions": [label],
                "label": label,
            }
        )

    if "紫微" in life_stars:
        emit("ziwei.star.ziwei_in_life", "紫微坐命", "命宫", ["紫微"], "紫微星落在命宫，属结构性事实。", 60)
    if not life_palace["main_stars"]:
        emit("ziwei.palace.life_empty", "命宫无主星", "命宫", [], "命宫十四主星全无，需借对宫星曜观察，属结构性事实。", 55)
    if life == body:
        emit("ziwei.palace.life_body_same", "命身同宫", "命宫", [], "身宫与命宫同在一宫，属结构性事实。", 50)

    by_type = {item["type"]: item for item in transformations}
    for kind, rule_id, palace_name in (
        ("忌", "ziwei.sihua.ji_in_life", "命宫"),
        ("禄", "ziwei.sihua.lu_in_cai", "财帛"),
        ("权", "ziwei.sihua.quan_in_guan", "官禄"),
    ):
        item = by_type.get(kind)
        if item and item["palace"] == palace_name:
            emit(
                rule_id,
                f"化{kind}入{palace_name}",
                palace_name,
                [item["star"]],
                f"生年化{kind}落在{palace_name}（{item['star']}），属结构性事实，不作吉凶判断。",
                45,
            )
    return markers


# ---------------------------------------------------------------- 飞星串联
#
# 紫微飞星串联：只列「哪一宫干化什么星、又落到哪一宫」的链路。
#
# 边界（与口径说明一致）：
# - 不取用神、不论吉凶、不把「禄转忌」读成事件；
# - 链路只做结构展示，最多 `depth` 跳，超过 `limit` 条即截断；
# - 遇到重复宫位视为环路，当前链停止并标 `cycle=True`。
#
# 为什么默认只从命宫/身宫起：
# 12 宫 × 4 化 × 每层 4 条，两跳就是 192 条，面板会淹没重点。起点可配置，
# 给了大限/流年时再追加对应宫位。


DEFAULT_DEPTH = 2
DEFAULT_LIMIT = 200


def build_chains(
    palace_transformations: list[dict[str, Any]],
    starts: list[str],
    *,
    depth: int = DEFAULT_DEPTH,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    by_from: dict[str, list[dict[str, Any]]] = {}
    for row in palace_transformations:
        by_from.setdefault(row["from_palace"], []).append(row)

    chains: list[dict[str, Any]] = []
    truncated = False

    for start in starts:
        seeds = by_from.get(start, [])
        for seed in seeds:
            if len(chains) >= limit:
                truncated = True
                break
            hops = [
                {
                    "palace": seed["from_palace"],
                    "type": seed["type"],
                    "star": seed["star"],
                    "to_palace": seed["to_palace"],
                }
            ]
            path = [start, seed["to_palace"]]
            current = seed["to_palace"]
            cycle = False
            for _ in range(1, max(depth, 1)):
                if current in path[:-1]:
                    cycle = True
                    break
                nxt = by_from.get(current, [])
                if not nxt:
                    break
                # 每一跳只取第一条，避免 4^depth 爆炸；四化类型在面板里仍完整可见
                step = nxt[0]
                hops.append(
                    {
                        "palace": current,
                        "type": step["type"],
                        "star": step["star"],
                        "to_palace": step["to_palace"],
                    }
                )
                path.append(step["to_palace"])
                if step["to_palace"] in path[:-1]:
                    cycle = True
                    break
                current = step["to_palace"]
            chains.append(
                {
                    "start_palace": start,
                    "start_stem": seed["stem"],
                    "hops": hops,
                    "cycle": cycle,
                }
            )
        if truncated:
            break

    return {
        "depth": depth,
        "starts": starts,
        "chains": chains,
        "truncated": truncated,
        "rule": "只列宫干四化的落宫链路，不推事件、不取用神；每跳取该宫第一条四化以避免组合爆炸",
    }


def calculate(inp: ZiweiInput, conv: ZiweiConvention | None = None) -> ChartResult:
    conv = conv or ZiweiConvention()
    tz = _resolve_zone(inp.timezone)
    warnings: list[str] = []

    # ---- 1. 生效时刻与农历 ----
    local_dt = inp.birth_datetime
    if not inp.time_known:
        local_dt = local_dt.replace(hour=PLACEHOLDER_HOUR, minute=0, second=0, microsecond=0)
        warnings.append(
            "出生时辰未知：按 12:00（午时）占位安星，命宫、身宫与全盘星曜都可能偏移，"
            "本盘只可用于了解排盘结构，不可据此下任何结论。"
        )

    lunar: LunarDate
    if inp.calendar == "lunar":
        month_arg = -abs(local_dt.month) if inp.is_leap_month else abs(local_dt.month)
        solar_dt = lunar_to_solar(
            local_dt.year, month_arg, local_dt.day, local_dt.hour, local_dt.minute
        )
        lunar = solar_to_lunar(solar_dt)
        effective_dt = solar_dt
    else:
        effective_dt = local_dt
        lunar = solar_to_lunar(local_dt)

    month = abs(lunar.month)
    if lunar.is_leap_month:
        warnings.append(
            f"出生月为{lunar.month_name}：本版本按本月安星（不并入下月），"
            "部分流派会把闰月按下月计，命宫与紫微落宫会随之变化。"
        )

    branch_text = hour_branch(local_dt.hour, local_dt.minute)
    hour_index = BRANCHES.index(branch_text)
    if local_dt.hour == 23:
        warnings.append(
            "出生时刻在 23:00–24:00：本版本按当日之子时计（不跳次日）。"
            "若采「子时换日」派，农历日数会差一天，全盘星曜随之改变。"
        )

    # ---- 2. 命宫 / 身宫 ----
    month_pos = (C.YIN_INDEX + (month - 1)) % 12
    life = (month_pos - hour_index) % 12
    body = (month_pos + hour_index) % 12
    year_stem = lunar.year_ganzhi[0]
    year_branch = lunar.year_ganzhi[1]

    # ---- 3. 宫干支 + 五行局 ----
    life_stem = _palace_stem(year_stem, life)
    life_branch = BRANCHES[life]
    nayin = C.nayin_element(life_stem, life_branch)
    bureau = C.BUREAU_BY_ELEMENT[nayin]
    bureau_name = C.BUREAU_NAME[bureau]

    # 大限方向在安星之前就要定下来：长生十二神 / 博士十二神的方向与它一致
    forward, gender_warning = _dayun_forward(year_stem, inp.gender)
    if gender_warning:
        warnings.append(gender_warning)

    # ---- 4~6. 安星 ----
    ziwei = _ziwei_index(bureau, lunar.day)
    placed = _stars(year_stem, year_branch, month, hour_index, ziwei)
    minor = _minor_stars(year_branch, month)

    # ---- 7. 四化（生年 / 宫干 / 大限 / 流年）----
    sihua = C.SI_HUA[year_stem]
    star_palace: dict[str, int] = {}
    for bucket in (placed, minor):
        for index, stars in bucket.items():
            for star in stars:
                star_palace.setdefault(star, index)
    transformations = _transformations_for(year_stem, star_palace, life)

    # ---- 8. 大限 ----
    dayun = []
    for step in range(12):
        index = (life + step) % 12 if forward else (life - step) % 12
        start_age = bureau + step * DAYUN_SPAN
        dayun.append(
            {
                "index": step + 1,
                "palace": C.PALACES[(life - index) % 12],
                "branch": BRANCHES[index],
                "start_age": start_age,
                "end_age": start_age + DAYUN_SPAN - 1,
            }
        )
    dayun_by_branch = {item["branch"]: item for item in dayun}

    # ---- 9. 十二宫 ----
    life_cycle = _life_cycle(bureau, forward)
    bo_shi = _bo_shi(C.LU_CUN[year_stem], forward)
    palaces: list[dict[str, Any]] = []
    for order, name in enumerate(C.PALACES):
        index = (life - order) % 12
        stars = placed[index]
        main = [star for star in stars if star in C.MAIN_STARS]
        aux = [star for star in stars if star not in C.MAIN_STARS]
        extra = minor[index]
        span = dayun_by_branch[BRANCHES[index]]
        palace_stem = _palace_stem(year_stem, index)
        # 自化：本宫宫干四化的目标星仍在本宫
        self_hua = [
            kind
            for kind, star in C.SI_HUA[palace_stem].items()
            if star_palace.get(star) == index
        ]
        # 小限：男命命宫起 1 岁顺行，女命逆行
        step = ((index - life) % 12) if forward else ((life - index) % 12)
        xiaoxian_ages = list(range(step + 1, C.XIAOXIAN_MAX_AGE + 1, 12))
        # 流年：流年支落本宫时的虚岁
        birth_branch_index = BRANCHES.index(lunar.year_ganzhi[1])
        liunian_ages = list(
            range(((index - birth_branch_index) % 12) + 1, C.XIAOXIAN_MAX_AGE + 1, 12)
        )
        group = C.sanhe_group(year_branch)
        jiang_start = C.JIANG_XING_START[group]
        year_index = BRANCHES.index(year_branch)
        palaces.append(
            {
                "order": order,
                "name": name,
                "branch": BRANCHES[index],
                "heavenly_stem": palace_stem,
                "is_body": index == body,
                "main_stars": main,
                "aux_stars": aux,
                "minor_stars": extra,
                "stars": main + aux + extra,
                "life_cycle": life_cycle.get(index),
                "bo_shi": bo_shi.get(index),
                "jiang_qian": C.JIANG_QIAN_ORDER[(index - jiang_start) % 12],
                "sui_qian": C.SUI_QIAN_ORDER[(index - year_index) % 12],
                "self_hua": self_hua,
                "xiaoxian_ages": xiaoxian_ages,
                "liunian_ages": liunian_ages,
                # 三方四正：本宫 + 财帛 + 官禄 + 迁移（按 PALACES 顺序 i, i+4, i+8, i+6）
                "sanfang": [C.PALACES[(order + offset) % 12] for offset in (0, 4, 8, 6)],
                "transformations": [
                    {"type": item["type"], "star": item["star"]}
                    for item in transformations
                    if item["branch"] == BRANCHES[index]
                ],
                "dayun": {"start_age": span["start_age"], "end_age": span["end_age"]},
            }
        )

    palace_transformations = _palace_transformations(palaces, star_palace, life)
    dayun_transformation = (
        _dayun_transformation(dayun, inp.review_age, year_stem, star_palace, life)
        if inp.review_age is not None
        else None
    )
    if inp.review_age is not None and dayun_transformation is None:
        warnings.append(
            f"输入的年龄 {inp.review_age} 超出十二个大限的覆盖范围（{dayun[0]['start_age']}–"
            f"{dayun[-1]['end_age']} 岁），本次不输出大限四化。"
        )
    liunian_transformation = (
        _liunian_transformation(inp.review_year, star_palace, life)
        if inp.review_year is not None
        else None
    )

    # ---- 大限/流年表 + 飞星串联 ----
    birth_year = effective_dt.year
    table_start = inp.review_year if inp.review_year is not None else birth_year
    liunian_table = []
    for offset in range(10):
        year = table_start + offset
        cycle = (year - 4) % 60
        branch_index = cycle % 12
        liunian_table.append(
            {
                "year": year,
                "virtual_age": year - birth_year + 1,
                "pillar": f"{STEMS[cycle % 10]}{BRANCHES[branch_index]}",
                "palace": C.PALACES[(life - branch_index) % 12],
            }
        )

    flying_starts: list[str] = []
    for candidate in (
        "命宫",
        C.PALACES[(life - body) % 12],
        dayun_transformation["palace"] if dayun_transformation else None,
        liunian_transformation["palace"] if liunian_transformation else None,
    ):
        if candidate and candidate not in flying_starts:
            flying_starts.append(candidate)
    flying = build_chains(
        palace_transformations, flying_starts, depth=inp.flying_depth
    )

    markers = _markers(
        palaces=palaces, transformations=transformations, life=life, body=body
    )

    chart_facts: dict[str, Any] = {
        "lunar_date": {
            "year": lunar.year,
            "month": lunar.month,
            "day": lunar.day,
            "is_leap_month": lunar.is_leap_month,
            "month_name": lunar.month_name,
            "day_name": lunar.day_name,
            "text": lunar.text,
        },
        "solar_date": effective_dt.strftime("%Y-%m-%d %H:%M"),
        "year_ganzhi": lunar.year_ganzhi,
        "year_zodiac": lunar.year_zodiac,
        "hour_branch": branch_text,
        "hour_known": inp.time_known,
        "five_element_bureau": {
            "element": nayin,
            "number": bureau,
            "name": bureau_name,
            "life_palace_nayin": f"{life_stem}{life_branch}",
        },
        "life_palace": {
            "branch": life_branch,
            "heavenly_stem": life_stem,
            "text": f"{life_stem}{life_branch}",
            "palace": "命宫",
        },
        "body_palace": {
            "branch": BRANCHES[body],
            "palace": C.PALACES[(life - body) % 12],
        },
        "ziwei_star": {
            "branch": BRANCHES[ziwei],
            "palace": C.PALACES[(life - ziwei) % 12],
        },
        "si_hua": dict(sihua),
        "palaces": palaces,
        "transformations": transformations,
        "palace_transformations": palace_transformations,
        "dayun": dayun,
        "dayun_forward": forward,
        "liunian_table": liunian_table,
        "flying": flying,
        "timezone": str(tz),
    }
    # 可选层：不给年龄/年份就不出这两个键，前端也不渲染空栏
    if dayun_transformation is not None:
        chart_facts["dayun_transformation"] = dayun_transformation
    if liunian_transformation is not None:
        chart_facts["liunian_transformation"] = liunian_transformation

    input_summary = {
        "calendar": inp.calendar,
        "birth_datetime": inp.birth_datetime.isoformat(timespec="minutes"),
        "effective_datetime": effective_dt.isoformat(timespec="minutes"),
        "lunar_date": lunar.text,
        "timezone": inp.timezone,
        "time_known": inp.time_known,
        "gender": inp.gender,
        "is_leap_month": inp.is_leap_month,
    }
    if inp.review_age is not None:
        input_summary["review_age"] = inp.review_age
    if inp.review_year is not None:
        input_summary["review_year"] = inp.review_year

    convention_dump = conv.model_dump()
    convention_dump["school_note"] = C.SCHOOL_NOTE

    warnings.append(C.SCHOOL_NOTE)

    source_refs = [
        {"type": "rule", "id": "ziwei.palace.month_hour", "note": "寅起正月顺数至生月，逆数至生时安命宫，顺数至生时安身宫"},
        {"type": "rule", "id": "ziwei.bureau.nayin", "note": "命宫干支纳音定五行局（水二木三金四土五火六）"},
        {"type": "rule", "id": "ziwei.star.ziwei", "note": "局数与生日定紫微宫，补数奇偶决定进退"},
        {"type": "rule", "id": "ziwei.star.series", "note": "紫微星系逆布、天府星系顺布共十四主星"},
        {"type": "rule", "id": "ziwei.aux.year_month_hour", "note": "辅星按年干、年支三合、生月、生时分别安放"},
        {"type": "rule", "id": "ziwei.minor.year_month", "note": "杂曜：天刑天姚按生月，红鸾天喜等按年支顺逆，华盖咸池孤辰寡宿破碎按三合三会"},
        {"type": "rule", "id": "ziwei.changsheng.bureau", "note": "长生十二神：局数起宫，方向同大限"},
        {"type": "rule", "id": "ziwei.boshi.lucun", "note": "博士十二神：禄存宫起博士，方向同大限"},
        {"type": "rule", "id": "ziwei.sihua.year_stem", "note": "生年干四化，庚干采通行说"},
        {"type": "rule", "id": "ziwei.sihua.palace_stem", "note": "飞星四化：宫干、大限宫干、流年干各推一组，只记落宫不记吉凶"},
        {"type": "rule", "id": "ziwei.dayun.yangyang", "note": "阳男阴女顺行，起限岁数等于五行局数"},
        {"type": "rule", "id": "ziwei.xiaoxian.gender", "note": "小限：男命命宫起一岁顺行、女命逆行，每宫隔十二年"},
        {"type": "rule", "id": "ziwei.jiangqian.year", "note": "将前十二神：年支三合定将星，顺行"},
        {"type": "rule", "id": "ziwei.suiqian.year", "note": "岁前十二神：年支起岁建，顺行"},
        {"type": "rule", "id": "ziwei.sanfang.order", "note": "三方四正：按十二宫顺序 i/i+4/i+8/i+6 取本宫、财帛、官禄、迁移"},
        {"type": "rule", "id": "ziwei.flying.chain", "note": "飞星串联：宫干四化逐层落宫，只列链路，最多三层，遇环路即停"},
        {"type": "book", "id": "ziwei.quanshu", "note": "《紫微斗数全书》通行安星法，本仓库仅取事实与结构，不取断语"},
    ]

    return ChartResult(
        domain="ziwei",
        algorithm_version=settings.ziwei_algorithm_version,
        input_summary=input_summary,
        convention=convention_dump,
        chart_facts=chart_facts,
        triggered_rules=markers,
        warnings=warnings,
        source_refs=source_refs,
    )
