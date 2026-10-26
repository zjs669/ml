"""四柱八字引擎：只产出确定性事实，不做任何吉凶判断。

对外唯一入口 `calculate(inp, conv)`，返回 `ChartResult`。
上层（关系引擎、AI 报告）只能读取 chart_facts / triggered_rules，不能修改。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings
from app.domains.bazi.constants import (
    HIDDEN_STEMS,
    LEVEL_WEIGHT,
    DayBoundaryNote,
)
from app.domains.bazi import shensha as shensha_table
from app.domains.bazi.schemas import BaziInput, ChartResult, Convention
from app.domains.calendar_core.astronomy import gregorian_to_jdn, true_solar_offset_minutes
from app.domains.calendar_core.jiazi import (
    BRANCHES,
    BRANCH_ELEMENT,
    ELEMENTS,
    JIE_TO_MONTH_BRANCH,
    STEM_ELEMENT,
    STEM_YANG,
    chang_sheng,
    day_pillar_index,
    hour_branch,
    hour_stem,
    jiazi_index,
    month_stem,
    nayin_of_index,
    pillar_of_index,
    pillar_text,
    ten_god,
    xun_of_index,
    year_pillar_index,
)
from app.domains.calendar_core.solar_terms import SolarTermService, get_term_service
from app.domains.relations.engine import attach_to_chart

BOUNDARY_WARNING_MINUTES = 120
PLACEHOLDER_HOUR = 12


def _resolve_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"未知时区: {name}（需要安装 tzdata）") from exc


def lichun_of_year(service: SolarTermService, year: int, tz: ZoneInfo):
    """取某公历年的立春时刻。2 月 15 日必然位于立春与惊蛰之间，向前取即为立春。"""
    probe = datetime(year, 2, 15, 12, 0, tzinfo=tz).astimezone(timezone.utc)
    term = service.prev_jie(probe)
    if term.name != "立春":  # pragma: no cover - 数据异常时兜底
        raise RuntimeError(f"立春定位失败，取到 {term.name}")
    return term


# ------------------------------------------------------------------ 大运
#
# 大运推算。
#
# 口径（写死在代码里并在结果中回显，不做隐式约定）：
# - 顺逆：阳年男 / 阴年女 顺排；阴年男 / 阳年女 逆排。
# - 起运：顺排数到「下一个节」，逆排数到「上一个节」；3 日折 1 年、1 日折 4 个月、
#   1 个时辰（2 小时）折 10 天。
# - 排运：从月柱起，顺排取后续干支，逆排取前序干支，每步 10 年。


def _add_ymd(years: int, months: int, days: int, base: datetime) -> datetime:
    total_months = base.year * 12 + (base.month - 1) + years * 12 + months
    year, month = divmod(total_months, 12)
    month += 1
    day = min(base.day, 28 if month == 2 else 30)
    return datetime(year, month, day) + timedelta(days=days)


def compute_dayun(
    *,
    month_pillar: tuple[str, str],
    year_stem: str,
    gender: str,
    birth_instant: datetime,
    birth_local: datetime,
    prev_jie,
    next_jie,
    steps: int = 8,
) -> dict:
    if gender == "unknown":
        return {
            "computed": False,
            "reason": "性别未知：起运顺逆依赖「阳年男/阴年女顺排」规则，未提供性别时不推算大运。",
        }

    yang_year = STEM_YANG[year_stem]
    forward = (yang_year and gender == "male") or (not yang_year and gender == "female")

    if forward:
        delta = next_jie.instant - birth_instant
        anchor = next_jie
    else:
        delta = birth_instant - prev_jie.instant
        anchor = prev_jie

    delta_days = max(delta.total_seconds() / 86400.0, 0.0)
    years_f = delta_days / 3.0
    years = int(years_f)
    rem_days = delta_days - years * 3
    months = int(rem_days * 4)
    rem_month_f = rem_days * 4 - months
    days = int(rem_month_f * 30)

    start_age_text = f"{years}年{months}个月{days}天"
    start_datetime = _add_ymd(years, months, days, birth_local)

    month_index = BRANCHES.index(month_pillar[1])
    start_index = jiazi_index(*month_pillar)
    fortune: list[dict] = []
    for step in range(1, steps + 1):
        offset = step if forward else -step
        pillar = pillar_of_index(start_index + offset)
        fortune.append(
            {
                "index": step,
                "pillar": pillar_text(pillar),
                "start_age_years": years + (step - 1) * 10,
                "end_age_years": years + step * 10 - 1,
                "start_year": _add_ymd(years + (step - 1) * 10, months, days, birth_local).year,
            }
        )

    return {
        "computed": True,
        "forward": forward,
        "rule": "阳年男/阴年女顺排，阴年男/阳年女逆排；3 日折 1 年",
        "anchor_jie": {"name": anchor.name, "local": anchor.instant.isoformat()},
        "start_offset_days": round(delta_days, 4),
        "start_age": {"years": years, "months": months, "days": days, "text": start_age_text},
        "start_datetime_estimate": start_datetime.strftime("%Y-%m-%d %H:%M"),
        "error_bound": "起运以 3 日折 1 年近似，交节时刻与出生时刻精度约 1 分钟，起运时间可能有数日级误差。",
        "list": fortune,
        "month_branch_index": month_index,
    }


def calculate(inp: BaziInput, conv: Convention | None = None, service: SolarTermService | None = None) -> ChartResult:
    conv = conv or Convention()
    service = service or get_term_service()
    tz = _resolve_zone(inp.timezone)

    warnings: list[str] = []

    # ---- 1. 生效时刻：未知时辰按 12:00 占位，但明确标记为不确定 ----
    local_dt = inp.birth_datetime
    if not inp.time_known:
        local_dt = local_dt.replace(hour=PLACEHOLDER_HOUR, minute=0, second=0, microsecond=0)
        warnings.append(
            "出生时辰未知：时柱按 12:00（午时）占位计算，时柱与相关十神均不确定；"
            "若出生时刻跨 23:00 或节气交节点，日柱/月柱也可能变化。"
        )

    # ---- 2. 真太阳时 ----
    adjusted_dt = local_dt
    solar_adjust = {"applied": False, "delta_minutes": 0.0, "method": conv.solar_time}
    if conv.solar_time == "true_solar_time":
        if inp.longitude is None:
            warnings.append("已选择真太阳时口径，但未提供出生地经度，本次未做校正。")
        else:
            delta_minutes = true_solar_offset_minutes(local_dt, tz, inp.longitude)
            adjusted_dt = local_dt + timedelta(minutes=delta_minutes)
            solar_adjust = {
                "applied": True,
                "delta_minutes": round(delta_minutes, 2),
                "longitude": inp.longitude,
                "method": "longitude+equation_of_time",
            }
            warnings.append(
                f"已按真太阳时校正 {delta_minutes:+.1f} 分钟（经度 {inp.longitude}°，含均时差）。"
            )

    instant = adjusted_dt.replace(tzinfo=tz).astimezone(timezone.utc)

    # ---- 3. 年柱：立春（或立春当日 0 点）为界 ----
    gregorian_year = adjusted_dt.year
    lichun = lichun_of_year(service, gregorian_year, tz)
    if conv.year_boundary == "lichun_day":
        boundary = lichun.instant.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        boundary_instant = boundary.astimezone(timezone.utc)
        warnings.append("年柱口径：以立春所在公历日的 0 点切换年份（非精确交节时刻）。")
    else:
        boundary_instant = lichun.instant

    ganzhi_year = gregorian_year if instant >= boundary_instant else gregorian_year - 1
    year_index = year_pillar_index(ganzhi_year)
    year_pillar = pillar_of_index(year_index)

    # ---- 4. 月柱：以「节」为界 ----
    prev_jie = service.prev_jie(instant)
    next_jie = service.next_jie(instant)
    month_branch = JIE_TO_MONTH_BRANCH.get(prev_jie.name)
    if month_branch is None:  # pragma: no cover - 数据异常
        raise RuntimeError(f"节气 {prev_jie.name} 不是定月之节")
    month_pillar = (month_stem(year_pillar[0], month_branch), month_branch)

    # ---- 5. 日柱：受换日口径影响 ----
    day_date = adjusted_dt.date()
    if conv.day_boundary == "zi_hour_policy_a" and adjusted_dt.hour >= 23:
        day_date = day_date + timedelta(days=1)
    day_index = day_pillar_index(gregorian_to_jdn(day_date.year, day_date.month, day_date.day))
    day_pillar = pillar_of_index(day_index)

    # ---- 6. 时柱：五鼠遁；夜子时取次日子干 ----
    branch = hour_branch(adjusted_dt.hour, adjusted_dt.minute)
    if conv.day_boundary == "zi_hour_policy_b" and adjusted_dt.hour >= 23:
        next_day = adjusted_dt.date() + timedelta(days=1)
        day_stem_for_hour = pillar_of_index(
            day_pillar_index(gregorian_to_jdn(next_day.year, next_day.month, next_day.day))
        )[0]
    else:
        day_stem_for_hour = day_pillar[0]
    hour_pillar = (hour_stem(day_stem_for_hour, branch), branch)

    # ---- 7. 十神 / 藏干 / 五行 ----
    day_master = day_pillar[0]
    pillars = {"year": year_pillar, "month": month_pillar, "day": day_pillar, "hour": hour_pillar}

    pillar_facts: dict[str, dict] = {}
    for position, (stem, br) in pillars.items():
        hidden = [
            {
                "stem": hs,
                "level": level,
                "weight": LEVEL_WEIGHT[level],
                "element": STEM_ELEMENT[hs],
                "ten_god": ten_god(day_master, hs),
            }
            for hs, level in HIDDEN_STEMS[br]
        ]
        index = jiazi_index(stem, br)
        pillar_facts[position] = {
            "stem": stem,
            "branch": br,
            "text": pillar_text((stem, br)),
            "stem_element": STEM_ELEMENT[stem],
            "stem_polarity": "阳" if STEM_YANG[stem] else "阴",
            "branch_element": BRANCH_ELEMENT[br],
            "hidden_stems": hidden,
            "ten_god": "日主" if position == "day" else ten_god(day_master, stem),
            "uncertain": (position == "hour" and not inp.time_known),
            # 与星航/文墨等排盘软件对齐的四行：纳音、旬空、地势、自坐
            "nayin": nayin_of_index(index),
            "xun_kong": list(xun_of_index(index)),
            "dishi": chang_sheng(br, day_master),
            "zizuo": chang_sheng(br, stem),
        }

    raw_count = {element: 0.0 for element in ELEMENTS}
    weighted_count = {element: 0.0 for element in ELEMENTS}
    for position, (stem, br) in pillars.items():
        raw_count[STEM_ELEMENT[stem]] += 1
        raw_count[BRANCH_ELEMENT[br]] += 1
        weighted_count[STEM_ELEMENT[stem]] += 1.0
        for hs, level in HIDDEN_STEMS[br]:
            weighted_count[STEM_ELEMENT[hs]] += LEVEL_WEIGHT[level]

    # ---- 8. 大运 ----
    dayun = compute_dayun(
        month_pillar=month_pillar,
        year_stem=year_pillar[0],
        gender=inp.gender,
        birth_instant=instant,
        birth_local=adjusted_dt,
        prev_jie=prev_jie,
        next_jie=next_jie,
    )

    # ---- 8.5 流年（仅当调用方给了起始年才计算）----
    liunian: dict | None = None
    if inp.liunian_start_year is not None:
        birth_year = adjusted_dt.year
        rows: list[dict] = []
        for offset in range(inp.liunian_years):
            year = inp.liunian_start_year + offset
            index = year_pillar_index(year)
            stem, branch = pillar_of_index(index)
            # 所属大运：大运列表里每步管 10 年，按起运公历年归属
            matched = next(
                (
                    item
                    for item in dayun.get("list", [])
                    if item.get("start_year") is not None
                    and item["start_year"] <= year <= item["start_year"] + 9
                ),
                None,
            )
            lichun = lichun_of_year(service, year, tz)
            lichun_local = lichun.instant.astimezone(tz)
            if conv.year_boundary == "lichun_day":
                # 与年柱口径保持一致：按立春所在公历日的 0 点换年
                lichun_local = lichun_local.replace(hour=0, minute=0, second=0, microsecond=0)
            rows.append(
                {
                    "year": year,
                    "pillar": pillar_text((stem, branch)),
                    "stem": stem,
                    "branch": branch,
                    "stem_element": STEM_ELEMENT[stem],
                    "branch_element": BRANCH_ELEMENT[branch],
                    "ten_god": ten_god(day_master, stem),
                    "virtual_age": year - birth_year + 1,
                    "lichun_local": lichun_local.strftime("%Y-%m-%d %H:%M"),
                    "dayun_pillar": matched["pillar"] if matched else None,
                    "dayun_index": matched["index"] if matched else None,
                }
            )
        liunian = {
            "start_year": inp.liunian_start_year,
            "years": inp.liunian_years,
            "boundary_rule": conv.year_boundary,
            "rule": "流年干支按 (year-4)%60 推；年界与年柱口径一致（立春交节或立春当日 0 点）；虚岁 = 公历年差 + 1",
            "list": rows,
        }

    # ---- 9. 边界提示 ----
    minutes_to_prev = (instant - prev_jie.instant).total_seconds() / 60
    minutes_to_next = (next_jie.instant - instant).total_seconds() / 60
    if minutes_to_prev < BOUNDARY_WARNING_MINUTES or minutes_to_next < BOUNDARY_WARNING_MINUTES:
        warnings.append(
            f"出生时刻紧邻节气「{prev_jie.name if minutes_to_prev < minutes_to_next else next_jie.name}」，"
            "月柱/年柱对交节时刻精度敏感，请核对出生时间与所采用口径。"
        )
    if abs((instant - boundary_instant).total_seconds()) / 60 < BOUNDARY_WARNING_MINUTES:
        warnings.append("出生时刻紧邻立春，年柱归属对口径与时刻精度高度敏感。")

    chart_facts = {
        "pillars": pillar_facts,
        "order": ["year", "month", "day", "hour"],
        "day_master": {
            "stem": day_master,
            "element": STEM_ELEMENT[day_master],
            "polarity": "阳" if STEM_YANG[day_master] else "阴",
        },
        "ten_gods": {position: pillar_facts[position]["ten_god"] for position in pillars},
        "five_elements_count": {
            "raw": raw_count,
            "weighted": {k: round(v, 2) for k, v in weighted_count.items()},
            "missing": [element for element, value in raw_count.items() if value == 0],
            "weight_rule": conv.five_element_weight,
        },
        "jieqi": {
            "prev": prev_jie.to_dict(tz),
            "next": next_jie.to_dict(tz),
            "minutes_to_prev": round(minutes_to_prev, 1),
            "minutes_to_next": round(minutes_to_next, 1),
        },
        "dayun": dayun,
        "shensha": shensha_table.compute(pillar_facts, variant=conv.shensha_variant),
        "solar_time_adjust": solar_adjust,
        "hour_confidence": "known" if inp.time_known else "unknown",
        "timezone": str(tz),
    }
    if liunian is not None:
        chart_facts["liunian"] = liunian

    input_summary = {
        "calendar": inp.calendar,
        "birth_datetime": inp.birth_datetime.isoformat(timespec="minutes"),
        "effective_datetime": adjusted_dt.isoformat(timespec="minutes"),
        "timezone": inp.timezone,
        "time_known": inp.time_known,
        "gender": inp.gender,
        "longitude": inp.longitude,
    }

    convention_dump = conv.model_dump()
    convention_dump["day_boundary_note"] = DayBoundaryNote[conv.day_boundary]
    if conv.shensha_variant == "extended":
        warnings.append(
            "神煞范围已设为 extended：勾绞、童子两类的起法各派不一，本盘按“年支顺数三位”“日柱纳音”占位，"
            "仅供对照，不作为结论依据。"
        )

    analysis = attach_to_chart(chart_facts)

    source_refs = [
        {"type": "rule", "id": "bazi.year.lichun", "note": "年柱以立春交割为界"},
        {"type": "rule", "id": "bazi.month.jie", "note": "月柱以十二节为界，五虎遁定月干"},
        {"type": "rule", "id": "bazi.day.jdn60", "note": "日柱按儒略日 60 循环，锚点见单测"},
        {"type": "rule", "id": "bazi.hour.wushudun", "note": "时柱按五鼠遁"},
        {"type": "rule", "id": "bazi.dayun.3day1year", "note": "3 日折 1 年起运"},
        {"type": "rule", "id": "bazi.liunian.lichun", "note": "流年年界按立春，年干支按 (year-4)%60"},
        {"type": "rule", "id": "bazi.shensha.common", "note": "神煞默认 10 类：天乙/太极/文昌/福星/金舆/华盖/寡宿/天德合/月德合/六秀日/金神/六厄"},
        {"type": "term_source", "id": service.source, "note": "节气时刻来源"},
    ]

    return ChartResult(
        domain="bazi",
        algorithm_version=settings.bazi_algorithm_version,
        input_summary=input_summary,
        convention=convention_dump,
        chart_facts=chart_facts,
        triggered_rules=analysis["rules"],
        warnings=warnings,
        source_refs=source_refs,
    )
