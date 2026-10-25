"""黄历引擎：通书日级条目，只列事实，不作吉凶结论。

数据来源是 `lunar-python`（MIT，6tail）的历法条目表，本模块只做三件事：
1. 把公历日期换成农历与干支四柱（复用 `calendar_core`）；
2. 取出宜、忌、值星、星宿、神煞、方位、九星等条目；
3. 组织成结构化事实并标注来源。

为什么不在本模块重写条目表：黄历条目是**约定俗成的编纂结果**，不是可推导的
天文事实。自己编一份等于造一个没有出处的版本，比直接引用一个有许可证的库更糟。

红线：不判断「适不适合做某事」，不排序宜忌的重要性，不输出任何吉凶结论。
"""

from __future__ import annotations

from datetime import date as Date
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings
from app.domains.bazi.schemas import ChartResult
from app.domains.calendar_core.lunar import solar_to_lunar
from app.domains.almanac.schemas import AlmanacConvention, AlmanacInput


def _resolve_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"未知时区: {name}（需要安装 tzdata）") from exc


def _lunar_object(day: Date):
    """取 lunar-python 的 Lunar 实例。缺库时由 calendar_core 抛 LunarLibraryMissing。"""
    from lunar_python import Solar

    return Solar.fromYmd(day.year, day.month, day.day).getLunar()


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    return [str(item) for item in value if item]


def calculate(inp: AlmanacInput, conv: AlmanacConvention | None = None) -> ChartResult:
    convention = conv or AlmanacConvention()
    warnings: list[str] = []

    zone = _resolve_zone(inp.timezone)
    target = inp.date
    lunar = _lunar_object(target)
    lunar_date = solar_to_lunar(target)

    # ---- 日级条目 ----
    nine_star = lunar.getDayNineStar()
    times = lunar.getTimes()

    chart_facts: dict[str, Any] = {
        "date": {
            "solar": target.isoformat(),
            "timezone": inp.timezone,
            "weekday": target.isoweekday(),
            "weekday_name": "一二三四五六日"[target.isoweekday() - 1],
        },
        "lunar_date": {
            "text": lunar_date.text,
            "year": lunar_date.year,
            "month": lunar_date.month,
            "day": lunar_date.day,
            "is_leap_month": lunar_date.is_leap_month,
            "year_ganzhi": lunar_date.year_ganzhi,
            "month_ganzhi": lunar_date.month_ganzhi,
            "day_ganzhi": lunar_date.day_ganzhi,
            "year_zodiac": lunar_date.year_zodiac,
        },
        "day_pillar": {
            "ganzhi": lunar_date.day_ganzhi,
            "na_yin": lunar.getDayNaYin(),
            "zhi_xing": lunar.getZhiXing(),
            "tian_shen_luck": lunar.getDayTianShenLuck(),
        },
        "yi": _as_list(lunar.getDayYi()),
        "ji": _as_list(lunar.getDayJi()),
        "ji_shen": _as_list(lunar.getDayJiShen()),
        "xiong_sha": _as_list(lunar.getDayXiongSha()),
        "chong": {
            "desc": lunar.getDayChongDesc(),
            "sheng_xiao": lunar.getDayChongShengXiao(),
            "gan": lunar.getDayChongGan(),
        },
        "sha_direction": lunar.getDaySha(),
        "xiu": {
            "name": lunar.getXiu(),
            "luck": lunar.getXiuLuck(),
            "zheng": lunar.getZheng(),
            "animal": lunar.getAnimal(),
            "song": lunar.getXiuSong(),
        },
        "nine_star": {
            "full": nine_star.toFullString(),
            "number": nine_star.getNumber(),
            "color": nine_star.getColor(),
            "element": nine_star.getWuXing(),
            "position": nine_star.getPosition(),
            "position_desc": nine_star.getPositionDesc(),
            "xuan_kong": {
                "name": nine_star.getNameInXuanKong(),
                "luck": nine_star.getLuckInXuanKong(),
            },
            "qi_men": {
                "name": nine_star.getNameInQiMen(),
                "luck": nine_star.getLuckInQiMen(),
            },
            "tai_yi": {
                "name": nine_star.getNameInTaiYi(),
                "type": nine_star.getTypeInTaiYi(),
            },
            "bei_dou": nine_star.getNameInBeiDou(),
        },
        "positions": {
            "xi": {"branch": lunar.getDayPositionXi(), "desc": lunar.getDayPositionXiDesc()},
            "yang_gui": {
                "branch": lunar.getDayPositionYangGui(),
                "desc": lunar.getDayPositionYangGuiDesc(),
            },
            "yin_gui": {
                "branch": lunar.getDayPositionYinGui(),
                "desc": lunar.getDayPositionYinGuiDesc(),
            },
            "fu": {"branch": lunar.getDayPositionFu(), "desc": lunar.getDayPositionFuDesc()},
            "cai": {"branch": lunar.getDayPositionCai(), "desc": lunar.getDayPositionCaiDesc()},
            "tai_sui": {
                "branch": lunar.getDayPositionTaiSui(),
                "desc": lunar.getDayPositionTaiSuiDesc(),
            },
        },
        "hour_slots": [
            {
                "index": index + 1,
                "ganzhi": item.getGanZhi(),
                "yi": _as_list(item.getYi()),
                "ji": _as_list(item.getJi()),
                "chong": item.getChongDesc(),
                "sha": item.getSha(),
                "tian_shen_luck": item.getTianShenLuck(),
            }
            for index, item in enumerate(times)
        ],
    }

    # ---- 个性化对照（只标注，不参与宜忌）----
    if inp.birth_date is not None:
        birth_lunar = _lunar_object(inp.birth_date)
        chart_facts["personal"] = {
            "birth_date": inp.birth_date.isoformat(),
            "birth_day_ganzhi": birth_lunar.getDayInGanZhi(),
            "birth_year_ganzhi": birth_lunar.getYearInGanZhi(),
            "birth_zodiac": birth_lunar.getYearShengXiao(),
            "note": "仅作对照标注，不参与宜忌判定，也不改变任何条目。",
        }
        warnings.append(
            "已按出生日期标注对照信息；黄历条目本身仍是通书通用条目，不因个人出生日期而改变。"
        )

    input_summary = {
        "date": target.isoformat(),
        "timezone": inp.timezone,
        "birth_date": inp.birth_date.isoformat() if inp.birth_date else None,
    }

    convention_dump = convention.model_dump()
    convention_dump["school_note"] = (
        "本版本只提供通书日级条目（宜、忌、值星、星宿、神煞、方位、九星），"
        "不做择日推荐、不做时辰择吉、不做个人命局配合。"
    )
    warnings.append(convention_dump["school_note"])
    warnings.append("黄历条目属约定俗成的编纂结果，不同通书版本可能不一致；本页只呈现当前数据源的条目。")

    source_refs = [
        {"type": "library", "id": "lunar-python", "note": "MIT License, 6tail；提供农历换算与通书日级条目"},
        {"type": "rule", "id": "almanac.day.boundary", "note": "黄历按自然日 00:00 换日，与四柱 23:00 换日不同口径"},
        {"type": "rule", "id": "almanac.hour.shichen", "note": "时辰吉凶按十二时辰分段，每段两小时"},
    ]

    return ChartResult(
        domain="almanac",
        algorithm_version=settings.almanac_algorithm_version,
        input_summary=input_summary,
        convention=convention_dump,
        chart_facts=chart_facts,
        triggered_rules=[],
        warnings=warnings,
        source_refs=source_refs,
    )
