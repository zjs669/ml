"""西洋占星（简化版）引擎测试。

期望值不取引擎输出：
- 太阳黄经用**天文锚点**核对：二分二至时太阳视黄经必须等于 0/90/180/270 度；
- 月亮黄经用**运动学约束**核对：日月会合周期内速度落在 11–15°/日，且满月时日月相差约 180°；
- 上升点用**恒等式**核对：ASC 与 MC 必须相差落在合理区间，且第一宫星座 = ASC 星座；
- 整宫制用定义核对：第 N 宫星座 = ASC 星座 + (N−1)。

不做的事也要测：`unavailable` 必须显式列出未实现项，不能悄悄省略。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domains.astrology.engine import (
    UNAVAILABLE,
    ZODIAC_SIGNS,
    _aspect_between,
    _moon_longitude,
    _sign_block,
    calculate,
)
from app.domains.astrology.schemas import AstrologyCalculateIn, AstrologyInput
from app.domains.calendar_core import astronomy

SHANGHAI = {"timezone": "Asia/Shanghai", "latitude": 31.23, "longitude": 121.47}


def _run(birth: str = "1990-05-20T12:00:00", **kwargs):
    inp = AstrologyInput.model_validate({"birth_datetime": birth, **SHANGHAI, **kwargs})
    return calculate(inp).chart_facts


# ---- 太阳黄经：天文锚点 ----

@pytest.mark.parametrize(
    "moment, expected",
    [
        ("2026-03-20T22:00:00", 0.0),    # 春分
        ("2026-06-21T16:00:00", 90.0),   # 夏至
        ("2026-09-23T08:00:00", 180.0),  # 秋分
        ("2026-12-22T04:00:00", 270.0),  # 冬至
    ],
)
def test_sun_longitude_at_equinox_and_solstice(moment: str, expected: float) -> None:
    """二分二至时太阳视黄经必须落在对应度数（容许 1° 内）。"""
    facts = _run(moment)
    longitude = facts["planets"]["sun"]["longitude"]
    delta = abs((longitude - expected + 180) % 360 - 180)
    assert delta < 1.0, f"{moment} 太阳黄经 {longitude}° 偏离 {expected}° 达 {delta}°"


def test_sun_matches_calendar_core() -> None:
    """太阳黄经必须复用 calendar_core，不另写一份。"""
    facts = _run("1990-05-20T12:00:00")
    assert facts["planets"]["sun"]["precision"] == "约 ±0.01°"
    assert facts["moment"]["delta_t_seconds"] > 0


# ---- 月亮黄经：运动学约束 ----

def test_moon_speed_within_physical_range() -> None:
    """月亮黄经日速必须落在 11–15°/日（真实范围约 11.8–14.8）。"""
    from datetime import datetime

    from app.domains.calendar_core import astronomy as astro

    def moon_at(moment: str) -> float:
        dt = datetime.fromisoformat(moment).replace(tzinfo=__import__("datetime").timezone.utc)
        jd = astro.julian_day(dt)
        jd_tt = jd + astro.delta_t_seconds(dt.year) / 86400.0
        return _moon_longitude(jd_tt)

    first = moon_at("2026-10-01T00:00:00")
    second = moon_at("2026-10-02T00:00:00")
    speed = (second - first) % 360
    assert 11.0 <= speed <= 15.0, f"月亮日速 {speed:.3f}° 超出物理范围"


def test_moon_near_opposition_at_full_moon() -> None:
    """满月时日月黄经差应接近 180°（容许 6°）。"""
    facts = _run("2026-10-26T12:00:00")  # 2026-10-26 前后为满月
    sun = facts["planets"]["sun"]["longitude"]
    moon = facts["planets"]["moon"]["longitude"]
    diff = abs((moon - sun) % 360)
    if diff > 180:
        diff = 360 - diff
    assert 170.0 <= diff <= 190.0, f"日月相差 {diff:.2f}°，不是满月附近"


# ---- 星座换算 ----

def test_sign_block_boundaries() -> None:
    assert _sign_block(0.0)["sign"] == "白羊"
    assert _sign_block(29.99)["sign"] == "白羊"
    assert _sign_block(30.0)["sign"] == "金牛"
    assert _sign_block(359.99)["sign"] == "双鱼"
    assert _sign_block(0.0)["element"] == "火"
    assert _sign_block(90.0)["element"] == "水"


def test_all_twelve_signs_reachable() -> None:
    signs = {_sign_block(degree * 30 + 1)["sign"] for degree in range(12)}
    assert signs == set(ZODIAC_SIGNS)


# ---- 上升点与宫位 ----

def test_ascendant_equals_first_house_sign() -> None:
    """整宫制定义：第一宫星座必须等于上升点所在星座。"""
    facts = _run()
    assert facts["houses"][0]["sign"] == facts["angles"]["ascendant"]["sign"]


def test_houses_advance_one_sign_each() -> None:
    """整宫制：第 N 宫星座 = ASC 星座 + (N−1)。"""
    facts = _run()
    asc_index = facts["angles"]["ascendant"]["sign_index"] - 1
    for house in facts["houses"]:
        expected = ZODIAC_SIGNS[(asc_index + house["house"] - 1) % 12]
        assert house["sign"] == expected, house["house"]
    assert len(facts["houses"]) == 12


def test_ascendant_changes_with_time() -> None:
    """上升点对时刻敏感：相隔 6 小时必须不同。"""
    morning = _run("1990-05-20T06:00:00")["angles"]["ascendant"]["longitude"]
    evening = _run("1990-05-20T18:00:00")["angles"]["ascendant"]["longitude"]
    assert abs(morning - evening) > 1.0


def test_ascendant_changes_with_longitude() -> None:
    """经度每差 15° 约等于 1 小时，上升点应随之变化。"""
    east = _run(longitude=121.47)["angles"]["ascendant"]["longitude"]
    west = _run(longitude=100.0)["angles"]["ascendant"]["longitude"]
    assert abs(east - west) > 1.0


# ---- 相位 ----

def test_aspect_detection() -> None:
    assert _aspect_between(10.0, 70.0, 6.0)[0]["aspect"] == "六分相"
    assert _aspect_between(0.0, 90.0, 6.0)[0]["aspect"] == "刑相"
    assert _aspect_between(0.0, 180.0, 6.0)[0]["aspect"] == "对分相"
    assert _aspect_between(0.0, 3.0, 6.0)[0]["aspect"] == "合相"
    assert _aspect_between(0.0, 45.0, 6.0) == []


def test_aspect_orb_is_respected() -> None:
    """超出容许度不报；收紧容许度后原本的边缘相位应消失。"""
    tight = _aspect_between(0.0, 65.0, 3.0)
    loose = _aspect_between(0.0, 65.0, 6.0)
    assert tight == []
    assert loose and loose[0]["aspect"] == "六分相"


def test_aspect_uses_shorter_arc() -> None:
    """相位角取最小差角：350° 与 10° 相差 20°，不是 340°。"""
    result = _aspect_between(350.0, 10.0, 25.0)
    assert result and result[0]["separation"] == 20.0


# ---- 诚实性：未实现项必须显式 ----

def test_unavailable_listed() -> None:
    """未实现的行星必须显式列出，不能静默省略。"""
    facts = _run()
    assert set(facts["unavailable"]) == set(UNAVAILABLE)
    assert "水星" in facts["unavailable"]
    assert "冥王星" in facts["unavailable"]
    assert set(facts["planets"]) == {"sun", "moon"}


def test_precision_is_declared() -> None:
    facts = _run()
    assert facts["planets"]["sun"]["precision"]
    assert facts["planets"]["moon"]["precision"]


def test_school_note_mentions_limits() -> None:
    inp = AstrologyInput.model_validate({"birth_datetime": "1990-05-20T12:00:00", **SHANGHAI})
    result = calculate(inp)
    note = result.convention["school_note"]
    assert "简化" in note and "未实现" in note


# ---- 契约 ----

def test_time_unknown_warns_and_uses_noon() -> None:
    facts = _run(time_known=False)
    assert facts["moment"]["local"].endswith("12:00")
    inp = AstrologyInput.model_validate(
        {"birth_datetime": "1990-05-20T03:00:00", **SHANGHAI, "time_known": False}
    )
    assert any("出生时刻未知" in item for item in calculate(inp).warnings)


def test_polar_latitude_rejected() -> None:
    """极圈内上升点可能不存在，必须明确拒绝而不是给错误值。"""
    with pytest.raises(ValidationError):
        AstrologyInput.model_validate(
            {"birth_datetime": "1990-05-20T12:00:00", "latitude": 70.0, "longitude": 20.0}
        )


def test_rejects_tz_aware_datetime() -> None:
    with pytest.raises(ValidationError):
        AstrologyInput.model_validate(
            {"birth_datetime": "1990-05-20T12:00:00+08:00", **SHANGHAI}
        )


def test_rejects_unknown_house_system() -> None:
    with pytest.raises(ValidationError):
        AstrologyCalculateIn.model_validate(
            {
                "birth_datetime": "1990-05-20T12:00:00",
                **SHANGHAI,
                "convention": {"house_system": "placidus"},
            }
        )


def test_triggered_rules_empty() -> None:
    inp = AstrologyInput.model_validate({"birth_datetime": "1990-05-20T12:00:00", **SHANGHAI})
    assert calculate(inp).triggered_rules == []
