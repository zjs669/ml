"""大六壬引擎（主干版）：月将加时 → 天地盘 → 四课 → 贼克法三传。

固定顺序（任何一步都不能交换）：
1. 定四柱、月将、昼夜；
2. 月将加时：把月将放到时支所在的**地盘**宫位，顺布十二支得天盘；
3. 定天将：按日干取阳贵/阴贵，以贵人所落地盘宫为起点，顺布十二天将；
4. 四课：以日干寄宫、日支、日干阴阳位推四课（一课干上神、二课干上神之支上神…）；
5. 三传：只实现**贼克法**（下贼上优先，其次上克下；同数则比用取阴阳）；
   其余课体（涉害、遥克、昴星、别责、八专、伏吟、返吟）明确标为未实现。

为什么三传只做贼克法：见 `constants.UNIMPLEMENTED_KE_TI` 的注释 ——
课体判定各版本优先级不同，硬凑会给出「看起来完整但可能错」的结果。

红线：只出天地盘、四课、三传与神煞位置，不判吉凶、不推应期。
"""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings
from app.domains.bazi.schemas import ChartResult
from app.domains.calendar_core.jiazi import BRANCHES, day_pillar_index, hour_branch, pillar_of_index
from app.domains.calendar_core.lunar import solar_to_lunar
from app.domains.daliuren import constants as C
from app.domains.daliuren.schemas import DaliurenConvention, DaliurenInput

PLACEHOLDER_HOUR = 12


def _resolve_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"未知时区: {name}（需要安装 tzdata）") from exc


def _lunar(day: Any):
    from lunar_python import Solar

    return Solar.fromYmd(day.year, day.month, day.day).getLunar()


def _build_earth_plate() -> dict[str, str]:
    """地盘：固定不动，支位即本身。"""
    return {branch: branch for branch in BRANCHES}


def _build_sky_plate(month_general: str, hour_branch_text: str) -> dict[str, str]:
    """天盘：月将加临时支宫位，其余顺布。

    返回「地盘宫位 → 天盘支」的映射。定义式是 `天盘[时支] = 月将`，
    其余地盘宫按「地盘支 + 位移」顺推：

        sky[earth] = 月将 + (earth − 时支)

    注意位移方向：写反会得到一张整体偏移的天盘 —— 盘面依然完整（十二支齐全、
    顺序也对），只是每个宫位都错位，肉眼几乎发现不了。
    """
    general_index = BRANCHES.index(month_general)
    hour_index = BRANCHES.index(hour_branch_text)
    sky: dict[str, str] = {}
    for index, earth in enumerate(BRANCHES):
        sky[earth] = BRANCHES[(general_index + (index - hour_index)) % 12]
    return sky


def _build_generals(day_stem: str, day_night: str) -> dict[str, str]:
    """天将：以「天盘支」为键，贵人所在天盘支起，顺布十二神。

    坐标系统必须统一：天将挂在**天盘**上（盘面读法是「地盘某宫，天盘某支，临某将」）。
    日干的阳贵/阴贵表给出的是贵人所乘的**天盘支**，因此这里按天盘支顺布，
    盘面渲染时用 `generals[sky[earth]]` 取该宫所临之将。

    早前版本把天将挂在地盘支上却按天盘支查询，两套坐标系混用会导致
    每个宫位的将都错位 —— 这类错误在盘面上看不出来（十二将齐全、顺序也对）。
    """
    gui_branch = C.YANG_GUI_REN[day_stem] if day_night == "day" else C.YIN_GUI_REN[day_stem]
    start_index = BRANCHES.index(gui_branch)
    generals: dict[str, str] = {}
    for offset, name in enumerate(C.TIAN_JIANG):
        generals[BRANCHES[(start_index + offset) % 12]] = name
    return generals


def _upper_of(sky: dict[str, str], earth: str) -> str:
    """某地盘宫位上的天盘支。"""
    return sky[earth]


def _four_lessons(day_stem: str, day_branch: str, sky: dict[str, str]) -> list[dict[str, Any]]:
    """四课。

    一课：日干寄宫的上神
    二课：一课上神（作为地盘）的上神
    三课：日支的上神
    四课：三课上神（作为地盘）的上神
    """
    lodge = C.STEM_LODGE[day_stem]
    first_upper = _upper_of(sky, lodge)
    second_upper = _upper_of(sky, first_upper)
    third_upper = _upper_of(sky, day_branch)
    fourth_upper = _upper_of(sky, third_upper)

    def lesson(index: int, lower: str, upper: str, note: str) -> dict[str, Any]:
        return {
            "index": index,
            "lower": lower,
            "upper": upper,
            "text": f"{upper}/{lower}",
            "note": note,
            "upper_element": C.branch_element(upper),
            "lower_element": C.branch_element(lower),
        }

    return [
        lesson(1, lodge, first_upper, f"日干{day_stem}寄{lodge}宫，取其上神"),
        lesson(2, first_upper, second_upper, "以一课上神为地盘，再取上神"),
        lesson(3, day_branch, third_upper, f"日支{day_branch}取其上神"),
        lesson(4, third_upper, fourth_upper, "以三课上神为地盘，再取上神"),
    ]


def _zeike(lessons: list[dict[str, Any]], day_stem: str) -> dict[str, Any]:
    """贼克法三传。

    规则：
    - 下贼上（下克上）优先于上克下；
    - 同类相克不止一处时，取与日干阴阳相同者（比用）；
    - 只取到一处时直接为初传。
    中传 = 初传所临地盘宫位上的天盘支；末传 = 中传所临地盘宫位上的天盘支。
    """
    downward: list[dict[str, Any]] = []
    upward: list[dict[str, Any]] = []
    for item in lessons:
        upper_el = item["upper_element"]
        lower_el = item["lower_element"]
        if C.is_ke(lower_el, upper_el):
            downward.append(item)
        elif C.is_ke(upper_el, lower_el):
            upward.append(item)

    candidates = downward or upward
    method = "贼克法"
    if not candidates:
        # 四课无上下克 → 遥克（上神与日干遥相克）或昴星（亦无遥克）。
        remote = _yaoke(lessons, day_stem)
        if remote is not None:
            return remote
        return {
            "implemented": False,
            "method": "昴星法",
            "reason": (
                "四课既无上下克、也无遥克，属昴星课体；"
                "昴星取传需按日干阴阳分取酉上神或天盘酉下神，本版本未实现"
            ),
            "candidates": [],
            "chuan": None,
        }
    if len(candidates) > 1:
        method = "比用法"
        from app.domains.calendar_core.jiazi import STEMS

        day_yang = STEMS.index(day_stem) % 2 == 0
        # 比用比较的是**发用者**（上神）与日干的阴阳，不是下神。
        # 早前实现比较的是 lower，等于拿「被克的一方」去比，选出来的往往是错的那一课。
        same_polarity = [
            item for item in candidates
            if (BRANCHES.index(item["upper"]) % 2 == 0) == day_yang
        ]
        if len(same_polarity) == 1:
            candidates = same_polarity
        else:
            # 比用后仍不唯一 → 进入涉害法：比较各候选的「涉害深浅」。
            # 涉害深浅 = 上神回到本位的路径上经过几重克，取**最深**者发用。
            deepest = _shehai_deepest(same_polarity or candidates)
            if deepest is None:
                return {
                    "implemented": False,
                    "method": "涉害法",
                    "reason": (
                        f"同类相克 {len(candidates)} 处，比用后仍不唯一"
                        f"（{len(same_polarity)} 处），涉害深浅亦相同，本版本不臆断"
                    ),
                    "candidates": [
                        {"index": item["index"], "text": item["text"]} for item in candidates
                    ],
                    "chuan": None,
                }
            method = "涉害法"
            candidates = [deepest]

    first = candidates[0]
    return {
        "implemented": True,
        "method": method,
        "reason": None,
        "candidates": [{"index": item["index"], "text": first["text"]}],
        "first": first,
    }


def _yaoke(lessons: list[dict[str, Any]], day_stem: str) -> dict[str, Any] | None:
    """遥克：四课无上下克时，取四课上神与**日干**遥相克者发用。

    分两种：
    - 上神克日干 → 蒿矢（外来的克）；
    - 日干克上神 → 弹射（由内向外）。

    传统上蒿矢优先于弹射。同类不止一处时按比用（与日干阴阳相同者）取舍，
    仍不唯一则视为无法判定，返回 None 交给调用方 —— 遥克的涉害深浅
    各家计法差异更大，不再往下推。

    为什么可以这样判：遥克只看「上神与日干」的五行关系，不依赖任何课表，
    是纯结构判定，因此不属于「凭记忆补课表」的范畴。
    """
    from app.domains.calendar_core.jiazi import STEMS

    day_element = C.stem_element(day_stem)
    haoshi: list[dict[str, Any]] = []   # 上神克日干
    tanshe: list[dict[str, Any]] = []   # 日干克上神
    for item in lessons:
        upper_element = item["upper_element"]
        if C.is_ke(upper_element, day_element):
            haoshi.append(item)
        elif C.is_ke(day_element, upper_element):
            tanshe.append(item)

    for group, method in ((haoshi, "遥克·蒿矢"), (tanshe, "遥克·弹射")):
        if not group:
            continue
        if len(group) == 1:
            return {
                "implemented": True,
                "method": method,
                "reason": None,
                "candidates": [{"index": group[0]["index"], "text": group[0]["text"]}],
                "first": group[0],
            }
        day_yang = STEMS.index(day_stem) % 2 == 0
        same = [
            item for item in group
            if (BRANCHES.index(item["upper"]) % 2 == 0) == day_yang
        ]
        if len(same) == 1:
            return {
                "implemented": True,
                "method": method,
                "reason": None,
                "candidates": [{"index": same[0]["index"], "text": same[0]["text"]}],
                "first": same[0],
            }
        return None
    return None


def _shehai_deepest(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """涉害法：比较各候选上神「涉害深浅」，取最深者发用。

    涉害深浅的算法：该候选的上神**从所临的地盘宫位出发，逆行回到自己本位**，
    途中每遇一个克它的地支计一重。谁的路径上「受克更多」，谁就是「涉害更深」。

    关键点：区间必须是「所临宫 → 本位」，**不能走满一圈**。
    绕满十二支时每个地支都被数到一次，而五行相克的次数只与五行有关，
    与起点无关 —— 那样算出来所有候选恒等，涉害法等于永远选不出来。
    （这一点在实现时踩过：整圈计数的版本让 18 个样本全部退化为「深浅相同」。）

    返回 None 表示深浅相同（或全为 0），此时不臆断，由调用方标未实现。
    """
    depths: list[tuple[dict[str, Any], int]] = []
    for item in candidates:
        upper = item["upper"]
        upper_element = C.branch_element(upper)
        home = BRANCHES.index(upper)          # 上神的本位
        landed = BRANCHES.index(item["lower"])  # 上神所临的地盘宫位
        # 从所临宫逆行回本位，走的步数 = (landed − home) mod 12
        span = (landed - home) % 12
        depth = 0
        for step in range(1, span):
            branch = BRANCHES[(landed - step) % 12]
            if C.is_ke(C.branch_element(branch), upper_element):
                depth += 1
        depths.append((item, depth))

    best_depth = max(depth for _, depth in depths)
    winners = [item for item, depth in depths if depth == best_depth]
    if best_depth == 0 or len(winners) != 1:
        return None
    return winners[0]


def _fuyin_first_lesson(lessons: list[dict[str, Any]]) -> dict[str, Any]:
    """伏吟取初传：四课上下神相同，无克可取，传统上取**干上神**（一课上神）发用。

    伏吟课体的中传/末传仍按「上所临之支」递推，与贼克法一致；
    差别只在初传的选取依据。
    """
    return lessons[0]


def _fanyin(
    lessons: list[dict[str, Any]],
    sky: dict[str, str],
    day_stem: str,
) -> dict[str, Any]:
    """返吟取初传：月将与时支相冲，四课两两相冲。

    返吟课体在传统上「有克取克、无克取马」；本版本只做前半段（取克），
    无克时如实标为未实现，不用「取马」等需要额外规则的路径硬补。
    """
    result = _zeike(lessons, day_stem)
    if result["implemented"]:
        result["method"] = "返吟"
        result["reason"] = None
    else:
        result["method"] = "返吟"
        result["reason"] = (
            "返吟课体且四课无上下克：传统上须取驿马发用，该规则本版本未实现"
        )
    return result


def calculate(inp: DaliurenInput, conv: DaliurenConvention | None = None) -> ChartResult:
    convention = conv or DaliurenConvention()
    warnings: list[str] = [C.SCHOOL_NOTE]

    zone = _resolve_zone(inp.timezone)
    local_dt = inp.cast_datetime
    lunar = solar_to_lunar(local_dt)
    lunar_obj = _lunar(local_dt.date())

    # ---- 1. 四柱 / 月将 / 昼夜 ----
    day_index = day_pillar_index(_jdn(local_dt))
    day_stem, day_branch = pillar_of_index(day_index)
    hour_text = hour_branch(local_dt.hour, local_dt.minute)
    month_branch = lunar.month_ganzhi[1]

    if convention.month_general_source == "manual":
        if inp.month_general is None:
            raise ValueError("month_general_source=manual 时必须提供 month_general")
        month_general = inp.month_general
    else:
        prev_qi = lunar_obj.getPrevQi()
        if prev_qi is None:
            raise ValueError("无法确定当前中气，无法定月将；请改用手工指定 month_general")
        qi_name = prev_qi.getName()
        month_general = C.QI_TO_MONTH_GENERAL.get(qi_name)
        if month_general is None:
            raise ValueError(f"中气「{qi_name}」不在月将表内")
        if inp.month_general is not None:
            warnings.append(
                f"已按口径用中气「{qi_name}」定月将为{month_general}；"
                f"手工指定的「{inp.month_general}」未生效（需切换 convention.month_general_source=manual）。"
            )

    if convention.day_night == "shichen":
        # 卯（4）至申（8）为昼
        day_night = "day" if 4 <= BRANCHES.index(hour_text) <= 8 else "night"
    else:
        day_night = convention.day_night

    # ---- 2~3. 天地盘与天将 ----
    sky = _build_sky_plate(month_general, hour_text)
    generals = _build_generals(day_stem, day_night)

    # ---- 4. 四课 ----
    lessons = _four_lessons(day_stem, day_branch, sky)

    # ---- 5. 三传 ----
    # 伏吟 / 返吟是**结构性**课体，先于贼克判定：
    # 伏吟时四课上下神相同、无克可取，若不先拦下来会被误判成「无上下克」。
    # 返吟时四课两两相冲，虽可能取到克，但传统上按返吟课体处理。
    fuyin = all(earth == sky[earth] for earth in BRANCHES)
    fanyin = all(
        BRANCHES[(BRANCHES.index(earth) + 6) % 12] == sky[earth] for earth in BRANCHES
    )
    if fuyin:
        zeike = {
            "implemented": True,
            "method": "伏吟",
            "reason": None,
            "candidates": [],
            "first": _fuyin_first_lesson(lessons),
        }
    elif fanyin:
        zeike = _fanyin(lessons, sky, day_stem)
    else:
        zeike = _zeike(lessons, day_stem)
    chuan: dict[str, Any] | None = None
    if zeike["implemented"]:
        first = zeike["first"]
        second_upper = _upper_of(sky, first["upper"])
        third_upper = _upper_of(sky, second_upper)
        chuan = {
            "first": {"branch": first["upper"], "from_lesson": first["index"], "text": first["text"]},
            "middle": {"branch": second_upper},
            "last": {"branch": third_upper},
            "method": zeike["method"],
        }
        for key in ("first", "middle", "last"):
            branch = chuan[key]["branch"]
            chuan[key]["general"] = generals.get(branch)
            chuan[key]["element"] = C.branch_element(branch)
            chuan[key]["chang_sheng"] = C.chang_sheng_of(day_stem, branch)
    else:
        warnings.append(f"三传未判定：{zeike['reason']}")

    # ---- 6. 盘面 ----
    plate = [
        {
            "earth": earth,
            "sky": sky[earth],
            # 天将挂在天盘支上：地盘某宫 → 天盘某支 → 临某将
            "general": generals.get(sky[earth]),
            "sky_element": C.branch_element(sky[earth]),
        }
        for earth in BRANCHES
    ]

    chart_facts: dict[str, Any] = {
        "datetime": {
            "solar": local_dt.isoformat(timespec="minutes"),
            "lunar": lunar.text,
            "timezone": inp.timezone,
            "hour_branch": f"{hour_text}时",
        },
        "pillars": {
            "year": lunar.year_ganzhi,
            "month": lunar.month_ganzhi,
            "day": f"{day_stem}{day_branch}",
            "hour": f"{_hour_stem(day_stem, hour_text)}{hour_text}",
        },
        "month_general": {
            "branch": month_general,
            "name": C.MONTH_GENERAL_NAMES[month_general],
            "source": convention.month_general_source,
            "qi": lunar_obj.getPrevQi().getName() if convention.month_general_source == "prev_qi" else None,
        },
        "day_night": {"value": day_night, "rule": convention.day_night},
        "plate": plate,
        "four_lessons": lessons,
        "san_chuan": chuan,
        "san_chuan_status": {
            "implemented": zeike["implemented"],
            "method": zeike["method"],
            "reason": zeike["reason"],
            "candidates": zeike["candidates"],
        },
        "shen_sha": {
            "tian_ma": C.tian_ma_of(month_branch),
            "jian_chu": C.jian_chu_of(month_branch, day_branch),
            "lodge": C.STEM_LODGE[day_stem],
            "gui_ren": {
                "yang": C.YANG_GUI_REN[day_stem],
                "yin": C.YIN_GUI_REN[day_stem],
                "used": "阳贵" if day_night == "day" else "阴贵",
            },
        },
    }

    input_summary = {
        "cast_at": local_dt.isoformat(timespec="minutes"),
        "timezone": inp.timezone,
        "month_general": inp.month_general,
        "question": inp.question if inp.store_question else None,
    }

    convention_dump = convention.model_dump()
    convention_dump["school_note"] = C.SCHOOL_NOTE
    if inp.question and not inp.store_question:
        warnings.append("已按你的选择丢弃占问原文，命盘只保存起课时刻与盘面。")

    source_refs = [
        {"type": "rule", "id": "daliuren.yuejiang.zhongqi", "note": "月将按中气交接定：雨水亥、春分戌、谷雨酉…大寒子"},
        {"type": "rule", "id": "daliuren.tiandipan.jiashi", "note": "月将加时：月将置于时支地盘宫，其余顺布"},
        {"type": "rule", "id": "daliuren.guiren.daynight", "note": "昼贵夜贵：卯至申为昼用阳贵，其余用阴贵"},
        {"type": "rule", "id": "daliuren.sike.jigong", "note": "日干寄宫（甲寄寅、乙寄辰…癸寄丑）定一课，逐课上神推四课"},
        {"type": "rule", "id": "daliuren.sanchuan.zeike", "note": "三传取贼克法：下贼上优先，同类比用；其余课体本版本不判"},
        {"type": "book", "id": "daliuren.liuren", "note": "大六壬通行法，本仓库只取结构与事实，不取断语"},
    ]

    return ChartResult(
        domain="daliuren",
        algorithm_version=settings.daliuren_algorithm_version,
        input_summary=input_summary,
        convention=convention_dump,
        chart_facts=chart_facts,
        triggered_rules=[],
        warnings=warnings,
        source_refs=source_refs,
    )


def _jdn(local_dt: Any) -> int:
    from app.domains.calendar_core.astronomy import gregorian_to_jdn

    return gregorian_to_jdn(local_dt.year, local_dt.month, local_dt.day)


def _hour_stem(day_stem: str, branch: str) -> str:
    from app.domains.calendar_core.jiazi import hour_stem as compute

    return compute(day_stem, branch)
