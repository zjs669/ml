"""西洋占星（简化版）引擎：太阳/月亮黄经 + 上升/天顶 + 整宫制 + 相位。

**精度与范围必须如实标注**（本模块的每条 warning 都写明了这一点）：

| 项目 | 本版本 | 精度 |
| --- | --- | --- |
| 太阳视黄经 | Meeus 低精度章（复用 `calendar_core.astronomy`） | 约 ±0.01° |
| 月亮黄经 | Meeus 第 47 章前 7 项主摄动 | 约 ±0.3° |
| 上升点 / 天顶 | 恒星时 + 黄赤交角球面三角 | 依赖上面两项与出生时刻精度 |
| 宫位 | 整宫制（whole sign） | 定义精确，但与 Placidus 结果不同 |
| 十行星 / 交点 / 莉莉丝 | **未实现** | — |

为什么不硬凑十行星：`pyswisseph` 需要 MSVC 编译（实测装不上），
自研摄动级数在 0.1° 量级上不可靠，输出出来会被当成专业星历使用。
宁可明确写「未实现」，也不给一个精度不足的假星盘。

红线：只输出黄经、星座、宫位、相位角，不做性格判断、不给事件预测。
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings
from app.domains.bazi.schemas import ChartResult
from app.domains.calendar_core import astronomy
from app.domains.astrology.schemas import AstrologyConvention, AstrologyInput

J2000 = 2451545.0

#: 黄道十二星座，按黄经 0° 起（白羊 0–30、金牛 30–60 …）
ZODIAC_SIGNS: tuple[str, ...] = (
    "白羊", "金牛", "双子", "巨蟹", "狮子", "处女",
    "天秤", "天蝎", "射手", "摩羯", "水瓶", "双鱼",
)
ZODIAC_ELEMENTS: tuple[str, ...] = ("火", "土", "风", "水")

#: 五大主要相位与角度
ASPECTS: tuple[tuple[str, float], ...] = (
    ("合相", 0.0),
    ("六分相", 60.0),
    ("刑相", 90.0),
    ("三分相", 120.0),
    ("对分相", 180.0),
)

SCHOOL_NOTE = (
    "本版本是简化占星：只算太阳与月亮的视黄经、上升点、天顶与整宫制宫位。"
    "十行星、月亮交点、莉莉丝与 Placidus 等高精度宫制均未实现；"
    "月亮黄经精度约 ±0.3°，上升点精度受出生时刻影响。"
    "结果只用于结构对照，不可当作专业星历使用。"
)

#: 显式列出未实现项，避免用户以为「没列出来就是没算错」
UNAVAILABLE = (
    "水星", "金星", "火星", "木星", "土星", "天王星", "海王星", "冥王星",
    "月亮北交点", "月亮南交点", "莉莉丝", "凯龙星",
)


def _resolve_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"未知时区: {name}（需要安装 tzdata）") from exc


def _obliquity_degrees(jd_tt: float) -> float:
    """黄赤交角（度），Meeus 第 22 章低精度式。"""
    t = (jd_tt - J2000) / 36525.0
    seconds = 21.448 - 46.8150 * t - 0.00059 * t**2 + 0.001813 * t**3
    return 23 + 26 / 60 + seconds / 3600


def _greenwich_sidereal_degrees(jd_ut: float) -> float:
    """格林尼治平恒星时（度），Meeus 第 12 章。"""
    t = (jd_ut - J2000) / 36525.0
    theta = (
        280.46061837
        + 360.98564736629 * (jd_ut - J2000)
        + 0.000387933 * t**2
        - t**3 / 38710000
    )
    return theta % 360


def _moon_longitude(jd_tt: float) -> float:
    """月亮视黄经（度），Meeus 第 47 章主摄动项（7 项，约 ±0.3°）。"""
    t = (jd_tt - J2000) / 36525.0
    l_prime = 218.3164477 + 481267.88123421 * t - 0.0015786 * t**2
    d = 297.8501921 + 445267.1114034 * t - 0.0018819 * t**2
    m = 357.5291092 + 35999.0502909 * t - 0.0001536 * t**2
    m_prime = 134.9633964 + 477198.8675055 * t + 0.0087414 * t**2
    f = 93.2720950 + 483202.0175233 * t - 0.0036539 * t**2

    def rad(deg: float) -> float:
        return math.radians(deg % 360)

    longitude = (
        l_prime
        + 6.288774 * math.sin(rad(m_prime))
        + 1.274027 * math.sin(rad(2 * d - m_prime))
        + 0.658314 * math.sin(rad(2 * d))
        + 0.213618 * math.sin(rad(2 * m_prime))
        - 0.185116 * math.sin(rad(m))
        - 0.114332 * math.sin(rad(2 * f))
    )
    return longitude % 360


def _sign_block(longitude: float) -> dict[str, Any]:
    index = int(longitude // 30) % 12
    degree_in_sign = longitude - index * 30
    return {
        "sign": ZODIAC_SIGNS[index],
        "sign_index": index + 1,
        "element": ZODIAC_ELEMENTS[index % 4],
        "degree_in_sign": round(degree_in_sign, 4),
        "absolute_degree": round(longitude, 4),
    }


def _ascendant(ramc_deg: float, obliquity_deg: float, latitude_deg: float) -> float:
    """上升点黄经（度）。

    球面三角：上升点是黄道与东方地平圈的交点。
    `ASC = atan2(cos(RAMC), -(sin(RAMC)·cos(ε) + tan(φ)·sin(ε)))`
    """
    ramc = math.radians(ramc_deg % 360)
    eps = math.radians(obliquity_deg)
    phi = math.radians(latitude_deg)
    y = math.cos(ramc)
    x = -(math.sin(ramc) * math.cos(eps) + math.tan(phi) * math.sin(eps))
    return math.degrees(math.atan2(y, x)) % 360


def _midheaven(ramc_deg: float, obliquity_deg: float) -> float:
    """天顶黄经（度）：`MC = atan2(sin(RAMC), cos(RAMC)·cos(ε))`。"""
    ramc = math.radians(ramc_deg % 360)
    eps = math.radians(obliquity_deg)
    return math.degrees(math.atan2(math.sin(ramc), math.cos(ramc) * math.cos(eps))) % 360


def _aspect_between(first: float, second: float, orb: float) -> list[dict[str, Any]]:
    """两个黄经之间的主要相位。相位角取最小差角。"""
    diff = abs(first - second) % 360
    if diff > 180:
        diff = 360 - diff
    found: list[dict[str, Any]] = []
    for name, angle in ASPECTS:
        delta = abs(diff - angle)
        if delta <= orb:
            found.append(
                {
                    "aspect": name,
                    "exact_angle": angle,
                    "orb": round(delta, 3),
                    "separation": round(diff, 3),
                }
            )
    return found


def calculate(inp: AstrologyInput, conv: AstrologyConvention | None = None) -> ChartResult:
    convention = conv or AstrologyConvention()
    warnings: list[str] = [SCHOOL_NOTE]

    zone = _resolve_zone(inp.timezone)
    local_dt = inp.birth_datetime
    if not inp.time_known:
        local_dt = local_dt.replace(hour=12, minute=0, second=0, microsecond=0)
        warnings.append(
            "出生时刻未知：按 12:00 占位计算，上升点与宫位会明显偏移，只有日月黄经大致可用。"
        )

    aware = local_dt.replace(tzinfo=zone)
    utc_dt = aware.astimezone(timezone.utc)
    jd_ut = astronomy.julian_day(utc_dt)
    delta_t = astronomy.delta_t_seconds(
        utc_dt.year + utc_dt.timetuple().tm_yday / 365.25
    )
    jd_tt = jd_ut + delta_t / 86400.0

    sun_longitude = astronomy.apparent_solar_longitude(jd_tt) % 360
    moon_longitude = _moon_longitude(jd_tt)
    obliquity = _obliquity_degrees(jd_tt)

    # 恒星时：格林尼治平恒星时 + 经度（东经为正）
    gmst = _greenwich_sidereal_degrees(jd_ut)
    ramc = (gmst + inp.longitude) % 360
    ascendant = _ascendant(ramc, obliquity, inp.latitude)
    midheaven = _midheaven(ramc, obliquity)

    sun_sign = _sign_block(sun_longitude)
    moon_sign = _sign_block(moon_longitude)
    asc_sign = _sign_block(ascendant)
    mc_sign = _sign_block(midheaven)

    # 整宫制：上升所在星座为第一宫，其后每宫一个星座
    asc_index = asc_sign["sign_index"] - 1
    houses = [
        {
            "house": number + 1,
            "sign": ZODIAC_SIGNS[(asc_index + number) % 12],
            "sign_index": ((asc_index + number) % 12) + 1,
            "cusps_degree": ((asc_index + number) % 12) * 30.0,
        }
        for number in range(12)
    ]

    chart_facts: dict[str, Any] = {
        "moment": {
            "local": local_dt.isoformat(timespec="minutes"),
            "utc": utc_dt.isoformat(timespec="minutes"),
            "timezone": inp.timezone,
            "julian_day_ut": round(jd_ut, 6),
            "delta_t_seconds": round(delta_t, 2),
            "time_known": inp.time_known,
        },
        "place": {
            "latitude": inp.latitude,
            "longitude": inp.longitude,
            "note": "东经为正、北纬为正；上升点与宫位依赖这两个值。",
        },
        "angles": {
            "obliquity": round(obliquity, 5),
            "sidereal_degrees": round(ramc, 5),
            "ascendant": {**asc_sign, "longitude": round(ascendant, 4)},
            "midheaven": {**mc_sign, "longitude": round(midheaven, 4)},
        },
        "planets": {
            "sun": {**sun_sign, "longitude": round(sun_longitude, 4), "precision": "约 ±0.01°"},
            "moon": {**moon_sign, "longitude": round(moon_longitude, 4), "precision": "约 ±0.3°"},
        },
        "unavailable": list(UNAVAILABLE),
        "houses": houses,
        "aspects": [
            {"between": ["sun", "moon"], **item}
            for item in _aspect_between(sun_longitude, moon_longitude, convention.aspect_orb)
        ],
        "aspect_orb": convention.aspect_orb,
    }

    input_summary = {
        "birth_datetime": inp.birth_datetime.isoformat(timespec="minutes"),
        "timezone": inp.timezone,
        "latitude": inp.latitude,
        "longitude": inp.longitude,
        "time_known": inp.time_known,
    }

    convention_dump = convention.model_dump()
    convention_dump["school_note"] = SCHOOL_NOTE
    warnings.append(
        "月亮黄经为低精度主摄动项，误差约 ±0.3°；若月相接近星座交界，星座归属可能翻转。"
    )
    if not chart_facts["aspects"]:
        warnings.append(
            f"日月之间没有落在 {convention.aspect_orb}° 容许度内的主要相位。"
        )

    source_refs = [
        {"type": "rule", "id": "astrology.sun.longitude", "note": "太阳视黄经：Meeus 第 25 章低精度式（复用 calendar_core）"},
        {"type": "rule", "id": "astrology.moon.longitude", "note": "月亮黄经：Meeus 第 47 章前 7 项主摄动，约 ±0.3°"},
        {"type": "rule", "id": "astrology.sidereal", "note": "格林尼治平恒星时：Meeus 第 12 章"},
        {"type": "rule", "id": "astrology.angles", "note": "上升点与天顶由恒星时、黄赤交角与纬度解球面三角得到"},
        {"type": "rule", "id": "astrology.house.whole_sign", "note": "整宫制：上升所在星座为第一宫，其后每宫一个星座"},
        {"type": "rule", "id": "astrology.aspect.orb", "note": "五大主要相位（0/60/90/120/180）与可配置容许度"},
    ]

    return ChartResult(
        domain="astrology",
        algorithm_version=settings.astrology_algorithm_version,
        input_summary=input_summary,
        convention=convention_dump,
        chart_facts=chart_facts,
        triggered_rules=[],
        warnings=warnings,
        source_refs=source_refs,
    )
