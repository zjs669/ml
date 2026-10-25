"""四柱反查：由干支组合反推可能的公历日期与时刻。

设计要点：

- **与正排严格互逆**：判定某个时刻是否命中，直接复刻 `engine.calculate` 的取柱顺序
  （同一套 JDN 锚点、五虎遁、五鼠遁、换日口径）。`tests/test_reverse.py` 用 500 个
  随机时刻做往返校验，任何一处口径漂移都会立刻失败。
- **按日柱先筛**：日柱只依赖儒略日，不需要节气，能先过滤掉 98% 的日期；
  只有日柱命中的日期才去算节气，因此 200 年全范围也能在秒级完成。
- **窗口而非时刻**：时柱只能把范围收敛到 2 小时，所以输出的是「钟表时间窗口」；
  子时跨日、真太阳时平移、交节拆分都在这里处理。
- **不猜**：无解时给出逐柱诊断，告诉用户是哪一柱对不上，而不是返回空数组。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.core.errors import AppError
from app.domains.bazi.constants import DayBoundaryNote
from app.domains.bazi.schemas import Convention
from app.domains.calendar_core.jiazi import (
    BRANCHES,
    JIE_TO_MONTH_BRANCH,
    STEMS,
    day_pillar_index,
    hour_branch,
    hour_stem,
    jiazi_index,
    month_stem,
    pillar_of_index,
    pillar_text,
    year_pillar_index,
)
from app.domains.calendar_core.julian import gregorian_to_jdn
from app.domains.calendar_core.solar_terms import SolarTermService
from app.domains.calendar_core.solar_time import true_solar_offset_minutes
from app.schemas.reverse import PillarQuery

POSITIONS = ("year", "month", "day", "hour")
POSITION_LABELS = {"year": "年柱", "month": "月柱", "day": "日柱", "hour": "时柱"}

# 各时辰的起始钟表小时（真太阳时口径下）；子时 23 点起，每支两小时
BRANCH_START_HOUR: dict[str, int] = {
    branch: (2 * index - 1) % 24 for index, branch in enumerate(BRANCHES)
}

_LICHUN_CACHE: dict[tuple[str, int, str], Any] = {}
_OFFSET_CACHE: dict[tuple[str, str, float], float] = {}
_JIE_DAY_CACHE: dict[tuple[str, str], list[datetime]] = {}


class InconsistentPillars(AppError):
    """四柱在历法上不可能同时成立（典型：时干与日干不满足五鼠遁）。"""

    def __init__(self, message: str) -> None:
        super().__init__("INCONSISTENT_PILLARS", message, status_code=400)


class ReverseQueryTooLoose(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("QUERY_TOO_LOOSE", message, status_code=400)


def _lichun(service: SolarTermService, tz: ZoneInfo, year: int):
    key = (tz.key, year, service.source)
    cached = _LICHUN_CACHE.get(key)
    if cached is not None:
        return cached
    probe = datetime(year, 2, 15, 12, 0, tzinfo=tz).astimezone(timezone.utc)
    term = service.prev_jie(probe)
    if term.name != "立春":  # pragma: no cover - 数据异常兜底
        raise RuntimeError(f"立春定位失败，取到 {term.name}")
    _LICHUN_CACHE[key] = term
    return term


def _daily_offset(local_date: date, tz: ZoneInfo, longitude: float | None) -> float:
    """真太阳时相对钟表时间的偏移（分钟）。一天内变化不足半分钟，按日缓存。"""
    if longitude is None:
        return 0.0
    key = (tz.key, local_date.isoformat(), round(longitude, 4))
    cached = _OFFSET_CACHE.get(key)
    if cached is not None:
        return cached
    noon = datetime.combine(local_date, time(12, 0))
    value = true_solar_offset_minutes(noon, tz, longitude)
    _OFFSET_CACHE[key] = value
    return value


def _jie_moments_in_day(local_date: date, tz: ZoneInfo, service: SolarTermService) -> list[datetime]:
    """某钟表日内的交节时刻（本地 naive）；没有交节返回空列表。"""
    key = (tz.key, local_date.isoformat(), service.source)
    if key in _JIE_DAY_CACHE:
        return _JIE_DAY_CACHE[key]
    day_start = datetime.combine(local_date, time(0, 0)).replace(tzinfo=tz).astimezone(timezone.utc)
    day_end = datetime.combine(local_date, time(23, 59, 59)).replace(tzinfo=tz).astimezone(timezone.utc)
    moments: list[datetime] = []
    probe = day_start
    for _ in range(2):
        term = service.next_jie(probe)
        if term.instant > day_end:
            break
        moments.append(term.instant.astimezone(tz).replace(tzinfo=None))
        probe = term.instant + timedelta(seconds=1)
    _JIE_DAY_CACHE[key] = moments
    return moments


def _pillars_at(
    local_dt: datetime,
    *,
    tz: ZoneInfo,
    conv: Convention,
    service: SolarTermService,
    longitude: float | None,
) -> dict[str, str]:
    """给定当地钟表时刻，算出四柱。逐步对应 engine.calculate 的第 2–6 步。"""
    adjusted = local_dt
    if conv.solar_time == "true_solar_time" and longitude is not None:
        # 与 _clock_windows 共用按日缓存的偏移量，保证"窗口"与"校验"用同一套数
        adjusted = local_dt + timedelta(minutes=_daily_offset(local_dt.date(), tz, longitude))
    instant = adjusted.replace(tzinfo=tz).astimezone(timezone.utc)

    lichun = _lichun(service, tz, adjusted.year)
    if conv.year_boundary == "lichun_day":
        boundary = lichun.instant.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        boundary_instant = boundary.astimezone(timezone.utc)
    else:
        boundary_instant = lichun.instant
    ganzhi_year = adjusted.year if instant >= boundary_instant else adjusted.year - 1
    year_pillar = pillar_of_index(year_pillar_index(ganzhi_year))

    prev_jie = service.prev_jie(instant)
    month_branch = JIE_TO_MONTH_BRANCH.get(prev_jie.name)
    if month_branch is None:  # pragma: no cover
        raise RuntimeError(f"节气 {prev_jie.name} 不是定月之节")
    month_pillar = (month_stem(year_pillar[0], month_branch), month_branch)

    day_date = adjusted.date()
    if conv.day_boundary == "zi_hour_policy_a" and adjusted.hour >= 23:
        day_date = day_date + timedelta(days=1)
    day_pillar = pillar_of_index(
        day_pillar_index(gregorian_to_jdn(day_date.year, day_date.month, day_date.day))
    )

    branch = hour_branch(adjusted.hour, adjusted.minute)
    if conv.day_boundary == "zi_hour_policy_b" and adjusted.hour >= 23:
        next_day = adjusted.date() + timedelta(days=1)
        day_stem_for_hour = pillar_of_index(
            day_pillar_index(gregorian_to_jdn(next_day.year, next_day.month, next_day.day))
        )[0]
    else:
        day_stem_for_hour = day_pillar[0]
    hour_pillar = (hour_stem(day_stem_for_hour, branch), branch)

    return {
        "year": pillar_text(year_pillar),
        "month": pillar_text(month_pillar),
        "day": pillar_text(day_pillar),
        "hour": pillar_text(hour_pillar),
    }


def _window_label(start: datetime, end: datetime, day: date) -> str:
    tail = "（次日）" if end.date() > day else ""
    return f"{start:%H:%M}-{end:%H:%M}{tail}"


def _clock_windows(
    day: date,
    branch: str,
    *,
    tz: ZoneInfo,
    conv: Convention,
    longitude: float | None,
) -> list[tuple[datetime, datetime]]:
    """某钟表日内，属于指定时辰的钟表时间区间（可能 0–2 段，子时会跨日拆开）。"""
    start_hour = BRANCH_START_HOUR[branch]
    day_start = datetime.combine(day, time(0, 0))
    day_end = day_start + timedelta(days=1)
    use_solar = conv.solar_time == "true_solar_time" and longitude is not None
    offset = _daily_offset(day, tz, longitude) if use_solar else 0.0
    span = timedelta(minutes=offset)

    windows: list[tuple[datetime, datetime]] = []
    for shift in (-1, 0, 1):
        anchor = datetime.combine(day + timedelta(days=shift), time(start_hour))
        true_start, true_end = anchor, anchor + timedelta(hours=2)
        clock_start, clock_end = true_start - span, true_end - span
        start = max(clock_start, day_start)
        end = min(clock_end, day_end)
        if start < end:
            windows.append((start, end))
    windows.sort()
    return windows


def _representatives(
    start: datetime, end: datetime, jie_moments: list[datetime]
) -> list[datetime]:
    """把区间按交节时刻切开，每段取中点作为代表时刻。"""
    cuts = [moment for moment in jie_moments if start < moment < end]
    points: list[datetime] = []
    cursor = start
    for cut in cuts:
        points.append(cursor + (cut - cursor) / 2)
        cursor = cut
    if cursor < end:
        points.append(cursor + (end - cursor) / 2)
    return points


def _allowed_day_stems(hour_text: str, conv: Convention) -> set[str]:
    """五鼠遁反推：给定时柱，哪些日干才可能在历法上产生这个时干。

    00:00 换日口径下的「夜子时」例外：时干取次日日干，因此当日日干要再顺推一位。
    """
    wanted_stem, branch = hour_text[0], hour_text[1]
    allowed = {stem for stem in STEMS if hour_stem(stem, branch) == wanted_stem}
    if conv.day_boundary == "zi_hour_policy_b" and branch == "子":
        allowed |= {STEMS[(STEMS.index(stem) - 1) % 10] for stem in allowed}
    return allowed


def resolve_timezone(name: str) -> ZoneInfo:
    """反查与正排必须用同一套时区解析（缺 tzdata 时给出同一条报错）。"""
    from app.domains.bazi.engine import _resolve_zone

    return _resolve_zone(name)


def reverse_search(
    query: PillarQuery,
    *,
    start: date,
    end: date,
    tz: ZoneInfo,
    conv: Convention,
    service: SolarTermService,
    longitude: float | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    warnings: list[str] = []
    if conv.solar_time == "true_solar_time" and longitude is None:
        warnings.append("已选择真太阳时口径但未提供经度，本次反查按钟表时间进行。")
    if conv.year_boundary == "lichun_day":
        warnings.append("年柱口径为「立春当日 0 点切换」，立春当天的结果可能与其他口径不同。")
    warnings.append(DayBoundaryNote[conv.day_boundary])

    allowed_stems: set[str] = set()
    if query.hour:
        allowed_stems = _allowed_day_stems(query.hour, conv)
        if query.day and query.day[0] not in allowed_stems:
            expected = hour_stem(query.day[0], query.hour[1])
            if conv.day_boundary == "zi_hour_policy_b" and query.hour[1] == "子":
                next_stem = STEMS[(STEMS.index(query.day[0]) + 1) % 10]
                expected = (
                    f"{expected}（按当日日干）或 {hour_stem(next_stem, '子')}（按次日日干）"
                )
            raise InconsistentPillars(
                f"{query.day}日不可能出现{query.hour}时：按五鼠遁，"
                f"{query.day[0]}日{query.hour[1]}时的时干应为「{expected}」，"
                f"而不是「{query.hour[0]}」。请核对日柱或时柱。"
            )
    if query.hour and not query.day and not query.year and not query.month:
        raise ReverseQueryTooLoose(
            "只填时柱会匹配两百年的每一天，请至少补一个日柱或年柱再查。"
        )

    wanted_day_index = jiazi_index(query.day[0], query.day[1]) if query.day else None
    hour_branch_wanted = query.hour[1] if query.hour else None
    allow_next_day = conv.day_boundary == "zi_hour_policy_a" and hour_branch_wanted == "子"

    per_day: dict[date, dict[str, Any]] = {}
    stage = {"day": 0, "year_month": 0, "hour": 0}
    searched_days = 0
    cursor = start

    while cursor <= end:
        searched_days += 1
        day_index = day_pillar_index(gregorian_to_jdn(cursor.year, cursor.month, cursor.day))
        day_text = pillar_text(pillar_of_index(day_index))

        # ---- 日柱粗筛（纯 JDN，不碰节气）----
        passed = True
        if wanted_day_index is not None:
            passed = day_index == wanted_day_index or (
                allow_next_day and (day_index + 1) % 60 == wanted_day_index
            )
        elif allowed_stems:
            passed = day_text[0] in allowed_stems
        if not passed:
            cursor += timedelta(days=1)
            continue

        stage["day"] += 1
        jie_moments = _jie_moments_in_day(cursor, tz, service)
        branches = [hour_branch_wanted] if hour_branch_wanted else list(BRANCHES)

        year_month_matched = False
        for branch in branches:
            for window_start, window_end in _clock_windows(
                cursor, branch, tz=tz, conv=conv, longitude=longitude
            ):
                label = _window_label(window_start, window_end, cursor)
                for probe in _representatives(window_start, window_end, jie_moments):
                    pillars = _pillars_at(
                        probe, tz=tz, conv=conv, service=service, longitude=longitude
                    )
                    if pillars["hour"][1] != branch:
                        # 真太阳时平移后可能落到相邻时辰，属于窗口边界噪声
                        continue
                    if any(
                        getattr(query, key) and pillars[key] != getattr(query, key)
                        for key in ("year", "month")
                    ):
                        continue
                    year_month_matched = True
                    if query.hour and pillars["hour"] != query.hour:
                        continue
                    if query.day and pillars["day"] != query.day:
                        continue
                    stage["hour"] += 1
                    entry = per_day.setdefault(
                        cursor,
                        {"date": cursor, "windows": [], "pillars": pillars, "variants": set()},
                    )
                    if label not in entry["windows"]:
                        entry["windows"].append(label)
                    entry["variants"].add(tuple(sorted(pillars.items())))
        if year_month_matched:
            stage["year_month"] += 1
        cursor += timedelta(days=1)

    diagnosis: list[str] = []
    if not per_day:
        diagnosis.append(f"范围内共检索 {searched_days} 天。")
        if stage["day"] == 0:
            if query.day:
                diagnosis.append(
                    f"日柱「{query.day}」在范围内没有出现，请检查日柱是否抄错。"
                )
            elif allowed_stems:
                diagnosis.append(
                    "时柱反推出的日干在范围内没有出现，请检查时柱的干支是否抄反。"
                )
        elif stage["year_month"] == 0:
            filled = "、".join(
                f"{POSITION_LABELS[key]}{getattr(query, key)}"
                for key in POSITIONS
                if getattr(query, key) and key != "day"
            )
            diagnosis.append(
                f"日柱匹配 {stage['day']} 天，但{filled or '年/月柱'}均不匹配："
                "请核对年柱与月柱，或把范围放宽到相邻年份。"
            )
        elif query.hour:
            diagnosis.append(
                "日柱与月柱能对上，但时柱无法同时成立："
                "请检查时干是否按五鼠遁推算（时干由日干决定，不能独立填写）。"
            )
        else:
            diagnosis.append("没有命中任何日期，请检查柱位与口径设置。")

    ordered = [per_day[key] for key in sorted(per_day)]
    total = len(ordered)
    page = ordered[offset : offset + limit]
    candidates = []
    for item in page:
        notes: list[str] = []
        if not query.hour:
            notes.append("未限定时柱：该日 12 个时辰均可能，需结合出生时刻进一步确认。")
        if len(item["variants"]) > 1:
            notes.append("该日恰逢交节，窗口内四柱发生变化，请按具体时刻核对。")
        candidates.append(
            {
                "date": item["date"],
                "hour_windows": item["windows"],
                "pillars": item["pillars"],
                "confidence": "exact" if len(query.filled()) == 4 else "partial",
                "notes": notes,
            }
        )

    return {
        "query": query.as_dict(),
        "convention": {**conv.model_dump(), "day_boundary_note": DayBoundaryNote[conv.day_boundary]},
        "searched_days": searched_days,
        "total_matches": total,
        "truncated": total > offset + limit,
        "offset": offset,
        "limit": limit,
        "candidates": candidates,
        "diagnosis": diagnosis,
        "warnings": warnings,
        "algorithm_version": settings.bazi_algorithm_version,
    }


__all__ = [
    "InconsistentPillars",
    "ReverseQueryTooLoose",
    "resolve_timezone",
    "reverse_search",
]
