"""小六壬引擎：六宫递推，只产出宫位落点，不做吉凶判断。

固定顺序（任何一步都不是可选流派）：
1. 月上起大安，顺数到所占农历月 → 月宫
2. 从月宫起，顺数到所占农历日 → 日宫
3. 从日宫起，顺数到所占时辰 → 时宫（断事落点）

红线：不输出应期、不输出吉凶结论、不输出行动建议。
`chart_facts` 里只有宫位、宫性、时辰与输入摘要。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings
from app.domains.bazi.schemas import ChartResult
from app.domains.calendar_core.lunar import solar_to_lunar
from app.domains.xiaoliuren import constants as C
from app.domains.xiaoliuren.schemas import XiaoliurenConvention, XiaoliurenInput


def _resolve_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"未知时区: {name}（需要安装 tzdata）") from exc


def _clock_to_shichen(hour: int) -> int:
    """0–23 小时 → 时辰序号 1–12。23:00 起算子时。"""
    return ((hour + 1) // 2) % 12 + 1


def _status_index(counted: int) -> int:
    """把「从 1 起数」的月/日/时数量换成六宫下标。"""
    return (counted - 1) % 6


def _status_block(name: str) -> dict[str, Any]:
    info = C.STATUS_INFO[name]
    return {
        "name": name,
        "element": info["element"],
        "direction": info["direction"],
        "nature": info["nature"],
        "spirit": info["spirit"],
        "numbers": info["numbers"],
        "description": info["description"],
        "poem": C.STATUS_POEMS[name],
    }


def calculate(inp: XiaoliurenInput, conv: XiaoliurenConvention | None = None) -> ChartResult:
    convention = conv or XiaoliurenConvention()
    warnings: list[str] = []

    # ---- 1. 定农历月日 ----
    if inp.input_mode == "gregorian":
        assert inp.date is not None  # schemas 已保证
        zone = _resolve_zone(inp.timezone)
        local_dt: datetime = inp.date.replace(tzinfo=zone)
        lunar = solar_to_lunar(local_dt)
        lunar_month = abs(lunar.month)
        lunar_day = lunar.day
        is_leap_month = lunar.is_leap_month
        lunar_text = lunar.text
        date_text = local_dt.date().isoformat()
    else:
        assert inp.lunar_month is not None and inp.lunar_day is not None
        lunar_month = inp.lunar_month
        lunar_day = inp.lunar_day
        is_leap_month = inp.is_leap_month
        lunar_text = f"农历{'闰' if is_leap_month else ''}{lunar_month}月{lunar_day}日"
        date_text = None
        warnings.append("手工农历输入未校验该日期在目标年份是否真实存在，请自行确认。")

    # ---- 2. 定时辰 ----
    if convention.hour_type == "shichen":
        if not 1 <= inp.hour <= 12:
            raise ValueError("hour_type=shichen 时 hour 必须是 1–12 的时辰序号")
        shichen_index = inp.hour
        clock_hour = None
    else:
        if not 0 <= inp.hour <= 23:
            raise ValueError("hour_type=clock 时 hour 必须是 0–23 的小时数")
        shichen_index = _clock_to_shichen(inp.hour)
        clock_hour = inp.hour
    shichen_name = C.SHICHEN_NAMES[shichen_index - 1]

    # ---- 3. 三宫递推 ----
    counted_month = lunar_month
    if is_leap_month and convention.leap_month_strategy == "advance":
        counted_month = lunar_month % 12 + 1
        warnings.append(f"闰{lunar_month}月按 advance 口径顺延为第 {counted_month} 月参与递推。")

    month_idx = _status_index(counted_month)
    day_idx = (month_idx + lunar_day - 1) % 6
    hour_idx = (day_idx + shichen_index - 1) % 6

    month_status = C.STATUS_ORDER[month_idx]
    day_status = C.STATUS_ORDER[day_idx]
    hour_status = C.STATUS_ORDER[hour_idx]

    if is_leap_month and convention.leap_month_strategy == "repeat":
        warnings.append(f"闰{lunar_month}月按 repeat 口径视同本月，不额外进位。")

    chart_facts: dict[str, Any] = {
        "lunar_date": {"text": lunar_text, "month": lunar_month, "day": lunar_day, "is_leap_month": is_leap_month},
        "shichen": {
            "index": shichen_index,
            "name": f"{shichen_name}时",
            "clock_hour": clock_hour,
            "hour_type": convention.hour_type,
        },
        "month_palace": _status_block(month_status),
        "day_palace": _status_block(day_status),
        # 断事落点：时宫
        "result_palace": _status_block(hour_status),
        "steps": [
            {"step": "month", "from": "大安", "count": counted_month, "landed": month_status},
            {"step": "day", "from": month_status, "count": lunar_day, "landed": day_status},
            {"step": "hour", "from": day_status, "count": shichen_index, "landed": hour_status},
        ],
    }

    input_summary = {
        "input_mode": inp.input_mode,
        "date": date_text,
        "lunar_month": lunar_month,
        "lunar_day": lunar_day,
        "is_leap_month": is_leap_month,
        "hour": inp.hour,
        "shichen": f"{shichen_name}时",
        "timezone": inp.timezone,
        "question": inp.question if inp.store_question else None,
    }

    convention_dump = convention.model_dump()
    convention_dump["school_note"] = C.SCHOOL_NOTE
    warnings.append(C.SCHOOL_NOTE)
    if inp.question and not inp.store_question:
        warnings.append("已按你的选择丢弃占问原文，命盘只保存起课时刻与宫位。")

    source_refs = [
        {"type": "rule", "id": "xiaoliuren.liugong.order", "note": "六宫固定顺序：大安→留连→速喜→赤口→小吉→空亡"},
        {"type": "rule", "id": "xiaoliuren.month.start", "note": "月上起大安，顺数至所占农历月"},
        {"type": "rule", "id": "xiaoliuren.day.from_month", "note": "从月宫起，顺数至所占农历日"},
        {"type": "rule", "id": "xiaoliuren.hour.from_day", "note": "从日宫起，顺数至所占时辰，落点即时宫"},
        {"type": "book", "id": "xiaoliuren.folk", "note": "六宫歌诀取民间通行本（公有领域），仅作文化背景，不参与计算"},
    ]

    return ChartResult(
        domain="xiaoliuren",
        algorithm_version=settings.xiaoliuren_algorithm_version,
        input_summary=input_summary,
        convention=convention_dump,
        chart_facts=chart_facts,
        triggered_rules=[],
        warnings=warnings,
        source_refs=source_refs,
    )
