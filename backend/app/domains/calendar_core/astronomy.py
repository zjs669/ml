"""太阳视黄经与均时差（Meeus《Astronomical Algorithms》第 25/27/28 章）。

用途有两个：
1. 作为离线兜底的节气推算（不依赖任何第三方历法库）；
2. 作为独立来源，与主节气提供器交叉核验。

精度说明（必须如实标注）：本章算法为「低精度」版本，太阳视黄经误差约 0.01°，
折算到节气时刻约 ±15 分钟。因此**默认节气来源不是本模块**，而是
`lunar_terms`（经审查、MIT 许可、可达分钟级）。本模块的定位是兜底与交叉核验。
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

J2000 = 2451545.0


def julian_day(dt_utc: datetime) -> float:
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    dt_utc = dt_utc.astimezone(timezone.utc)
    y, m = dt_utc.year, dt_utc.month
    d = (
        dt_utc.day
        + (dt_utc.hour + dt_utc.minute / 60 + dt_utc.second / 3600 + dt_utc.microsecond / 3.6e9) / 24
    )
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + b - 1524.5


def julian_day_to_datetime(jd: float) -> datetime:
    jd += 0.5
    z = int(jd)
    f = jd - z
    if z < 2299161:
        a = z
    else:
        alpha = int((z - 1867216.25) / 36524.25)
        a = z + 1 + alpha - alpha // 4
    b = a + 1524
    c = int((b - 122.1) / 365.25)
    d = int(365.25 * c)
    e = int((b - d) / 30.6001)
    day = b - d - int(30.6001 * e) + f
    month = e - 1 if e < 14 else e - 13
    year = c - 4716 if month > 2 else c - 4715
    day_int = int(day)
    frac = (day - day_int) * 24
    hour = int(frac)
    minute_f = (frac - hour) * 60
    minute = int(minute_f)
    second = int(round((minute_f - minute) * 60))
    base = datetime(year, month, day_int, hour, minute, tzinfo=timezone.utc)
    return base + timedelta(seconds=second)


def delta_t_seconds(year: float) -> float:
    """TT - UT 近似（Espenak & Meeus 多项式，1900–2150 误差约数秒）。"""
    if year < 1920:
        t = year - 1900
        return -2.79 + 1.494119 * t - 0.0598939 * t**2 + 0.0061966 * t**3 - 0.000197 * t**4
    if year < 1941:
        t = year - 1920
        return 21.20 + 0.84493 * t - 0.076100 * t**2 + 0.0020936 * t**3
    if year < 1961:
        t = year - 1950
        return 29.07 + 0.407 * t - t**2 / 233 + t**3 / 2547
    if year < 1986:
        t = year - 1975
        return 45.45 + 1.067 * t - t**2 / 260 - t**3 / 718
    if year < 2005:
        t = year - 2000
        return (
            63.86
            + 0.3345 * t
            - 0.060374 * t**2
            + 0.0017275 * t**3
            + 0.000651814 * t**4
            + 0.00002373599 * t**5
        )
    if year < 2050:
        t = year - 2000
        return 62.92 + 0.32217 * t + 0.005589 * t**2
    return -20 + 32 * ((year - 1820) / 100) ** 2 - 0.5628 * (2150 - year)


def _sun_terms(t: float) -> tuple[float, float, float, float]:
    """返回 (几何平黄经 L0, 平近点角 M, 中心差 C, 视黄经)。角度单位为度。"""
    l0 = 280.46646 + 36000.76983 * t + 0.0003032 * t**2
    m = 357.52911 + 35999.05029 * t - 0.0001537 * t**2
    m_rad = math.radians(m)
    c = (
        (1.914602 - 0.004817 * t - 0.000014 * t**2) * math.sin(m_rad)
        + (0.019993 - 0.000101 * t) * math.sin(2 * m_rad)
        + 0.000289 * math.sin(3 * m_rad)
    )
    omega = 125.04 - 1934.136 * t
    apparent = l0 + c - 0.00569 - 0.00478 * math.sin(math.radians(omega))
    return l0, m, c, apparent % 360


def apparent_solar_longitude(jd_tt: float) -> float:
    t = (jd_tt - J2000) / 36525.0
    return _sun_terms(t)[3]


def equation_of_time_minutes(jd_ut: float) -> float:
    """均时差（分钟），用于真太阳时换算。Meeus 第 28 章，精度约 1 秒。"""
    t = (jd_ut - J2000) / 36525.0
    l0, _m, _c, lam = _sun_terms(t)
    omega = 125.04 - 1934.136 * t
    eps0 = 23 + 26 / 60 + 21.448 / 3600 - (46.8150 * t + 0.00059 * t**2 - 0.001813 * t**3) / 3600
    eps = eps0 + 0.00256 * math.cos(math.radians(omega))
    lam_rad = math.radians(lam)
    eps_rad = math.radians(eps)
    alpha = math.degrees(math.atan2(math.cos(eps_rad) * math.sin(lam_rad), math.cos(lam_rad))) % 360
    e = l0 - 0.0057183 - alpha
    e = (e + 180) % 360 - 180
    return e * 4.0


_TARGET_CACHE: dict[tuple[int, int], datetime] = {}


def solar_term_instant_utc(year: int, target_longitude: float) -> datetime:
    """求解太阳视黄经等于 target_longitude 的时刻（UTC）。低精度：约 ±15 分钟。"""
    key = (year, int(target_longitude))
    cached = _TARGET_CACHE.get(key)
    if cached is not None:
        return cached

    # 初值：视黄经 ≈ 280.46 + 0.98565 * 天数
    days = (target_longitude - 280.46) % 360 / 0.98565
    guess = datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=days)
    for _ in range(12):
        jd_ut = julian_day(guess)
        jd_tt = jd_ut + delta_t_seconds(guess.year + guess.timetuple().tm_yday / 365.25) / 86400
        diff = (target_longitude - apparent_solar_longitude(jd_tt) + 180) % 360 - 180
        guess = guess + timedelta(days=diff / 0.98565)
        if abs(diff) < 1e-6:
            break
    _TARGET_CACHE[key] = guess
    return guess


# ------------------------------------------------------------ 儒略日换算
#
# 儒略日换算。只做纯日期，不含时区；所有时刻由上层用 tz 归一。


def is_leap(year: int) -> bool:
    return (year % 4 == 0 and year % 100 != 0) or year % 400 == 0


def days_in_month(year: int, month: int) -> int:
    if month == 2:
        return 29 if is_leap(year) else 28
    return 30 if month in (4, 6, 9, 11) else 31


def gregorian_to_jdn(year: int, month: int, day: int) -> int:
    """公历 → 儒略日数（正午起算的整日序号，格里历）。"""
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    return day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045


def jdn_to_gregorian(jdn: int) -> tuple[int, int, int]:
    a = jdn + 32044
    b = (4 * a + 3) // 146097
    c = a - (146097 * b) // 4
    d = (4 * c + 3) // 1461
    e = c - (1461 * d) // 4
    m = (5 * e + 2) // 153
    day = e - (153 * m + 2) // 5 + 1
    month = m + 3 - 12 * (m // 10)
    year = 100 * b + d - 4800 + m // 10
    return year, month, day


# ------------------------------------------------------------ 真太阳时
#
# 真太阳时换算：经度时差 + 均时差。
# 
# 口径写死在这里，并在结果中回显，避免"悄悄修正"用户的出生时刻：
# - 经度时差 = (出生地经度 − 时区标准经线) × 4 分钟/度
# - 均时差 = 由太阳视黄经/赤经差求得（Meeus 第 28 章）
# 真太阳时 = 当地标准时 + 上述两项


def standard_meridian(tz: ZoneInfo, local_dt: datetime) -> float:
    offset = local_dt.replace(tzinfo=tz).utcoffset()
    hours = (offset.total_seconds() if offset else 0) / 3600
    return hours * 15


def true_solar_offset_minutes(local_dt: datetime, tz: ZoneInfo, longitude: float) -> float:
    meridian = standard_meridian(tz, local_dt)
    longitude_minutes = (longitude - meridian) * 4.0
    instant = local_dt.replace(tzinfo=tz).astimezone(timezone.utc)
    eot = equation_of_time_minutes(julian_day(instant))
    return longitude_minutes + eot
