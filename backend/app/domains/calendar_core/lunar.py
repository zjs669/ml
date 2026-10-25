"""农历换算（基于 `lunar-python`）。

紫微斗数与六爻时间起卦必须先转农历，因此 `lunar-python` 是**运行时依赖**，
不再是测试期交叉核验工具。这里只做最小封装：

- `solar_to_lunar()` 公历 → 农历（含闰月标记、干支、月建名）
- `lunar_to_solar()` 农历 → 公历（负月份表示闰月，与上游库一致）
- `leap_month_of()` 某农历年的闰月序号

**缺库时抛 `LunarLibraryMissing`，绝不静默按公历硬算** —— 装作能算比算不出来更危险：
紫微会安错命宫，六爻会起错卦，而用户完全看不出来。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

__all__ = [
    "LunarDate",
    "LunarLibraryMissing",
    "LunarRangeError",
    "leap_month_of",
    "lunar_to_solar",
    "solar_to_lunar",
]


class LunarLibraryMissing(RuntimeError):
    """运行环境缺少 `lunar-python`，农历相关术数无法计算。"""


class LunarRangeError(ValueError):
    """农历日期不存在（如该年无闰月、闰月序号越界、月份或日越界）。"""


@dataclass(frozen=True)
class LunarDate:
    """一次农历换算的结果。字段命名与 MySQL / 前端约定保持一致。"""

    #: 农历年（以正月初一为界，不是立春）
    year: int
    #: 农历月，**闰月为负**（-4 表示闰四月），与 lunar-python 同口径
    month: int
    day: int
    is_leap_month: bool
    #: "四月" / "闰四月"
    month_name: str
    #: "廿六"
    day_name: str
    year_ganzhi: str
    month_ganzhi: str
    day_ganzhi: str
    year_zodiac: str

    @property
    def text(self) -> str:
        return f"{self.year}年{self.month_name}{self.day_name}"


def _load() -> tuple[Any, Any, Any]:
    try:
        from lunar_python import Lunar, LunarYear, Solar
    except ModuleNotFoundError as exc:  # pragma: no cover - 正常安装环境不会触发
        raise LunarLibraryMissing(
            "农历换算需要 lunar-python，请先执行 `pip install 'lunar-python>=1.3.10'`"
            "（已列在 backend/pyproject.toml 的运行时依赖中）"
        ) from exc
    return Solar, Lunar, LunarYear


def _month_name(chinese: str) -> str:
    """`getMonthInChinese()` 已带「闰」前缀（闰四 / 四），补上「月」。"""
    return f"{chinese}月"


def solar_to_lunar(moment: datetime | date) -> LunarDate:
    """公历 → 农历。传入 `datetime` 时只取年月日，时刻不参与换算。"""
    solar_cls, _, _ = _load()
    lunar = solar_cls.fromYmd(moment.year, moment.month, moment.day).getLunar()
    raw_month = int(lunar.getMonth())
    return LunarDate(
        year=int(lunar.getYear()),
        month=raw_month,
        day=int(lunar.getDay()),
        is_leap_month=raw_month < 0,
        month_name=_month_name(lunar.getMonthInChinese()),
        day_name=lunar.getDayInChinese(),
        year_ganzhi=lunar.getYearInGanZhi(),
        month_ganzhi=lunar.getMonthInGanZhi(),
        day_ganzhi=lunar.getDayInGanZhi(),
        year_zodiac=lunar.getYearShengXiao(),
    )


def lunar_to_solar(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
    second: int = 0,
) -> datetime:
    """农历 → 公历。

    `month` 为负表示闰月（-4 = 闰四月）。该年无此闰月或日期越界时抛
    `LunarRangeError`，而不是悄悄当成普通月份。
    """
    _, lunar_cls, _ = _load()
    leap = leap_month_of(year)
    if month < 0 and leap != -month:
        raise LunarRangeError(f"{year} 年没有闰 {-month} 月（该年闰月：{leap or '无'}）")
    if month > 12 or month == 0:
        raise LunarRangeError(f"农历月份 {month} 不合法")
    try:
        solar = lunar_cls.fromYmdHms(year, month, day, hour, minute, second).getSolar()
    except Exception as exc:  # 上游库对越界日期抛 ValueError 或 IndexError
        raise LunarRangeError(f"农历 {year}-{month}-{day} 不存在：{exc}") from exc
    return datetime(
        int(solar.getYear()),
        int(solar.getMonth()),
        int(solar.getDay()),
        int(solar.getHour()),
        int(solar.getMinute()),
        int(solar.getSecond()),
    )


def leap_month_of(year: int) -> int:
    """返回该农历年的闰月序号（1–12），无闰月返回 0。"""
    _, _, lunar_year_cls = _load()
    return int(lunar_year_cls.fromYear(year).getLeapMonth())
