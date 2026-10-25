"""真太阳时换算：经度时差 + 均时差。

口径写死在这里，并在结果中回显，避免"悄悄修正"用户的出生时刻：
- 经度时差 = (出生地经度 − 时区标准经线) × 4 分钟/度
- 均时差 = 由太阳视黄经/赤经差求得（Meeus 第 28 章）
真太阳时 = 当地标准时 + 上述两项
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.domains.calendar_core import astronomy


def standard_meridian(tz: ZoneInfo, local_dt: datetime) -> float:
    offset = local_dt.replace(tzinfo=tz).utcoffset()
    hours = (offset.total_seconds() if offset else 0) / 3600
    return hours * 15


def true_solar_offset_minutes(local_dt: datetime, tz: ZoneInfo, longitude: float) -> float:
    meridian = standard_meridian(tz, local_dt)
    longitude_minutes = (longitude - meridian) * 4.0
    instant = local_dt.replace(tzinfo=tz).astimezone(timezone.utc)
    eot = astronomy.equation_of_time_minutes(astronomy.julian_day(instant))
    return longitude_minutes + eot
