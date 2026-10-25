"""紫微运限引擎：在本命盘上叠时间层，只出宫位与星曜。

为什么不复用 `ziwei.engine.calculate` 的 `review_age` / `review_year`：
那两个字段只覆盖「大限四化 + 流年四化」两层，且不产出流月/流日/流时的落宫。
运限需要六层（大限 → 小限 → 流年 → 流月 → 流日 → 流时）逐层递推，
每一层都从上一层落宫起算，硬塞进本命盘的入参会让 `ziwei` 的契约变成万能参数袋。

因此这里**先调本命盘**拿到宫位、星曜、大限表与四化，再在结果上叠时间层。
本命盘的口径完全由 `ziwei` 域负责，本模块不重算任何安星。

六层递推（各派起法不同，本版本固定一种并在 `convention` 回显）：
1. 大限：由虚岁落在哪个大限区间决定（复用本命盘的 `dayun` 表）
2. 小限：由虚岁与性别决定（复用本命盘的 `xiaoxian_ages`）
3. 流年：流年支对应本命盘哪一宫（复用 `liunian_table`）
4. 流月：斗君法 —— 流年宫起正月逆数生月，再起子时顺数生时，得正月宫；其后逐月顺行
5. 流日：自流月宫起初一顺行
6. 流时：自流日宫起子时顺行

红线：不判吉凶、不断事件、不把星曜组合读成结论。
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.domains.bazi.schemas import ChartResult
from app.domains.calendar_core.jiazi import BRANCHES, hour_branch
from app.domains.calendar_core.lunar import solar_to_lunar
from app.domains.ziwei import constants as ZC
from app.domains.ziwei.engine import calculate as calculate_ziwei
from app.domains.ziwei.schemas import ZiweiConvention, ZiweiInput
from app.domains.ziwei_horoscope.schemas import HoroscopeConvention, HoroscopeInput

PALACE_ORDER = ZC.PALACES


def _palace_by_name(palaces: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    for palace in palaces:
        if palace.get("name") == name:
            return palace
    return None


def _palace_at(palaces: list[dict[str, Any]], branch: str) -> dict[str, Any] | None:
    for palace in palaces:
        if palace.get("branch") == branch:
            return palace
    return None


def _virtual_age(birth_year: int, target_year: int) -> int:
    """虚岁：出生即 1 岁，每过农历年 +1。"""
    return target_year - birth_year + 1


def calculate(inp: HoroscopeInput, conv: HoroscopeConvention | None = None) -> ChartResult:
    convention = conv or HoroscopeConvention()
    warnings: list[str] = []

    # ---- 1. 本命盘（口径完全交给 ziwei 域）----
    # 本命盘的流年表窗口由 `review_year` 决定，起点即目标年，
    # 否则默认从出生年起算 10 年，运限目标年可能落在窗口外。
    natal_input = ZiweiInput(
        calendar=inp.calendar,
        birth_datetime=inp.birth_datetime,
        is_leap_month=inp.is_leap_month,
        timezone=inp.timezone,
        gender=inp.gender,
        time_known=inp.time_known,
        review_year=inp.target_date.year,
    )
    natal = calculate_ziwei(natal_input, ZiweiConvention())
    natal_facts = natal.chart_facts
    palaces: list[dict[str, Any]] = natal_facts["palaces"]
    warnings.extend(f"本命盘：{item}" for item in natal.warnings)

    birth_lunar = solar_to_lunar(inp.birth_datetime)
    birth_year = birth_lunar.year
    birth_month = abs(birth_lunar.month)
    target_lunar = solar_to_lunar(inp.target_date)
    target_year = target_lunar.year
    age = _virtual_age(birth_year, target_year)
    if age < 1:
        raise ValueError("运限目标日期早于出生年，无法计算虚岁")

    # ---- 2. 大限 ----
    dayun_table: list[dict[str, Any]] = natal_facts["dayun"]
    decadal = next(
        (item for item in dayun_table if item["start_age"] <= age <= item["end_age"]), None
    )
    if decadal is None:
        warnings.append(
            f"虚岁 {age} 超出本命盘 12 个大限（最大 {dayun_table[-1]['end_age']} 岁）的覆盖范围，"
            "大限层留空，不推测。"
        )
    decadal_palace = decadal["palace"] if decadal else None

    # ---- 3. 小限 ----
    xiaoxian_palace = None
    for palace in palaces:
        ages = palace.get("xiaoxian_ages") or []
        if age in ages:
            xiaoxian_palace = palace["name"]
            break

    # ---- 4. 流年 ----
    liunian_row = next(
        (row for row in natal_facts["liunian_table"] if row["year"] == target_year), None
    )
    liunian_palace = liunian_row["palace"] if liunian_row else None
    liunian_pillar = liunian_row["pillar"] if liunian_row else None
    if liunian_palace is None:
        warnings.append(f"本命盘的流年表未覆盖 {target_year} 年，流年层留空。")

    # ---- 5. 流月（斗君法）----
    # 流年宫 → 起正月：逆数生月；再自该宫起子时顺数至生时
    hour_index = BRANCHES.index(hour_branch(inp.birth_datetime.hour, inp.birth_datetime.minute))
    liunian_palace_obj = _palace_by_name(palaces, liunian_palace) if liunian_palace else None
    monthly_palace = None
    if liunian_palace_obj is not None:
        start_index = (liunian_palace_obj["order"] - (birth_month - 1)) % 12
        doujun_order = (start_index + hour_index) % 12
        target_month = abs(target_lunar.month)
        monthly_order = (doujun_order + (target_month - 1)) % 12
        monthly_palace = PALACE_ORDER[monthly_order]
    else:
        warnings.append("流年宫缺失，流月层无法起宫，留空。")

    # ---- 6. 流日 ----
    daily_palace = None
    if monthly_palace:
        monthly_order = PALACE_ORDER.index(monthly_palace)
        daily_order = (monthly_order + (target_lunar.day - 1)) % 12
        daily_palace = PALACE_ORDER[daily_order]
    else:
        warnings.append("流月宫缺失，流日层无法起宫，留空。")

    # ---- 7. 流时 ----
    hourly_palace = None
    if daily_palace:
        daily_order = PALACE_ORDER.index(daily_palace)
        target_hour_index = BRANCHES.index(hour_branch(inp.target_hour))
        hourly_order = (daily_order + target_hour_index) % 12
        hourly_palace = PALACE_ORDER[hourly_order]
    else:
        warnings.append("流日宫缺失，流时层无法起宫，留空。")

    def layer(name: str, palace_name: str | None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        block: dict[str, Any] = {"layer": name, "palace": palace_name}
        if palace_name:
            palace = _palace_by_name(palaces, palace_name)
            if palace:
                block["branch"] = palace["branch"]
                block["heavenly_stem"] = palace["heavenly_stem"]
                block["main_stars"] = palace["main_stars"]
                block["aux_stars"] = palace["aux_stars"]
                block["minor_stars"] = palace["minor_stars"]
        if extra:
            block.update(extra)
        return block

    layers = [
        layer("大限", decadal_palace, {"age_range": f"{decadal['start_age']}-{decadal['end_age']}"} if decadal else None),
        layer("小限", xiaoxian_palace),
        layer("流年", liunian_palace, {"year": target_year, "pillar": liunian_pillar}),
        layer("流月", monthly_palace, {"month": abs(target_lunar.month), "is_leap_month": target_lunar.is_leap_month}),
        layer("流日", daily_palace, {"day": target_lunar.day}),
        layer("流时", hourly_palace, {"hour": inp.target_hour, "shichen": hour_branch(inp.target_hour)}),
    ]

    chart_facts: dict[str, Any] = {
        "natal": {
            "life_palace": natal_facts["life_palace"],
            "body_palace": natal_facts["body_palace"],
            "five_element_bureau": natal_facts["five_element_bureau"],
            "year_ganzhi": natal_facts["year_ganzhi"],
            "si_hua": natal_facts["si_hua"],
            "palace_count": len(palaces),
        },
        "target": {
            "solar_date": inp.target_date.date().isoformat(),
            "lunar_date": target_lunar.text,
            "lunar_year": target_year,
            "lunar_month": abs(target_lunar.month),
            "lunar_day": target_lunar.day,
            "virtual_age": age,
            "hour": inp.target_hour,
            "shichen": hour_branch(inp.target_hour),
        },
        "layers": layers,
        "transit_transformations": _transit_transformations(layers, palaces, natal_facts),
    }

    input_summary = {
        "birth_datetime": inp.birth_datetime.isoformat(timespec="minutes"),
        "timezone": inp.timezone,
        "gender": inp.gender,
        "target_date": inp.target_date.date().isoformat(),
        "target_hour": inp.target_hour,
    }

    convention_dump = convention.model_dump()
    convention_dump["school_note"] = (
        "运限在本命盘（三合派）之上叠六层时间：大限、小限、流年、流月、流日、流时。"
        "流月用斗君法，流日自流月宫起初一顺行，流时自流日宫起子时顺行。"
        "本版本只给落宫与星曜，不判吉凶、不断事件。"
    )
    warnings.append(convention_dump["school_note"])
    if inp.gender == "unknown":
        warnings.append("性别未知：大限与小限方向按「阳年顺、阴年逆」占位，结果可能与实际不符。")

    source_refs = [
        {"type": "rule", "id": "ziwei.horoscope.decadal", "note": "大限由虚岁落在哪个十年区间决定，复用本命盘大限表"},
        {"type": "rule", "id": "ziwei.horoscope.xiaoxian", "note": "小限由虚岁与性别决定，复用本命盘小限表"},
        {"type": "rule", "id": "ziwei.horoscope.liunian", "note": "流年宫取流年支在本命盘对应宫位"},
        {"type": "rule", "id": "ziwei.horoscope.doujun", "note": "斗君法起流月：流年宫逆数生月，再顺数生时"},
        {"type": "rule", "id": "ziwei.horoscope.daily", "note": "流日自流月宫起初一顺行"},
        {"type": "rule", "id": "ziwei.horoscope.hourly", "note": "流时自流日宫起子时顺行"},
        {"type": "book", "id": "ziwei.quanshu", "note": "《紫微斗数全书》通行运限法，本仓库只取结构与事实，不取断语"},
    ]

    return ChartResult(
        domain="ziwei_horoscope",
        algorithm_version=settings.ziwei_horoscope_algorithm_version,
        input_summary=input_summary,
        convention=convention_dump,
        chart_facts=chart_facts,
        triggered_rules=[],
        warnings=warnings,
        source_refs=source_refs,
    )


def _transit_transformations(
    layers: list[dict[str, Any]],
    palaces: list[dict[str, Any]],
    natal_facts: dict[str, Any],
) -> list[dict[str, Any]]:
    """逐层列出该层落宫的宫干四化去向 —— 只列链路，不解读。

    复用本命盘已经算好的 `palace_transformations`，不重推四化表，
    避免同一个四化规则在本仓库出现两份实现。
    """
    by_from: dict[str, list[dict[str, Any]]] = {}
    for row in natal_facts.get("palace_transformations", []) or []:
        by_from.setdefault(row["from_palace"], []).append(row)

    result: list[dict[str, Any]] = []
    for item in layers:
        palace_name = item.get("palace")
        if not palace_name:
            continue
        rows = by_from.get(palace_name, [])
        result.append(
            {
                "layer": item["layer"],
                "from_palace": palace_name,
                "stem": rows[0]["stem"] if rows else None,
                "flights": [
                    {"type": row["type"], "star": row["star"], "to_palace": row["to_palace"]}
                    for row in rows
                ],
            }
        )
    return result
