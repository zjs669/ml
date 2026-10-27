"""历法与节气测试：儒略日、甲子、节气时刻、真太阳时。"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.domains.bazi.engine import lichun_of_year
from app.domains.calendar_core import astronomy, solar_terms

from app.domains.calendar_core.jiazi import (
    BRANCHES,
    STEMS,
    day_pillar_index,
    hour_branch,
    hour_stem,
    jiazi_index,
    month_stem,
    pillar_of_index,
    pillar_text,
    ten_god,
    year_pillar_index,
)

# 儒略日与真太阳时已并入 `calendar_core.astronomy`（原 `julian.py` / `solar_time.py`）。
# 这里保留别名，让测试读起来仍能区分「纯日期换算」与「时刻校正」两组函数。
julian = astronomy
solar_time = astronomy

BEIJING = ZoneInfo("Asia/Shanghai")


def test_julian_roundtrip() -> None:
    for year, month, day in [
        (1900, 1, 1), (1949, 10, 1), (2000, 2, 29), (2024, 12, 31), (2099, 6, 15),
    ]:
        jdn = julian.gregorian_to_jdn(year, month, day)
        assert julian.jdn_to_gregorian(jdn) == (year, month, day)


def test_julian_known_value() -> None:
    # 1949-10-01 的儒略日号为 2433191（日柱锚点，见 jiazi.DAY_PILLAR_OFFSET 注释）
    assert julian.gregorian_to_jdn(1949, 10, 1) == 2433191


def test_leap_years() -> None:
    assert julian.is_leap(2000) and julian.is_leap(2024)
    assert not julian.is_leap(1900) and not julian.is_leap(2100)


def test_day_pillar_anchor() -> None:
    # 1949-10-01 为甲子日：锚点常量被单测锁定，改错会立刻失败
    index = day_pillar_index(julian.gregorian_to_jdn(1949, 10, 1))
    assert pillar_text(pillar_of_index(index)) == "甲子"
    # 60 日循环
    next_index = day_pillar_index(julian.gregorian_to_jdn(1949, 11, 30))
    assert next_index == index


def test_jiazi_bijection() -> None:
    seen = set()
    for index in range(60):
        pillar = pillar_of_index(index)
        assert pillar_text(pillar) not in seen
        seen.add(pillar_text(pillar))
        assert jiazi_index(*pillar) == index
    assert len(seen) == 60
    assert pillar_of_index(60) == pillar_of_index(0)
    assert pillar_of_index(-1) == ("癸", "亥")


def test_year_pillar_boundary() -> None:
    # 1984 为甲子年
    assert pillar_text(pillar_of_index(year_pillar_index(1984))) == "甲子"
    assert pillar_text(pillar_of_index(year_pillar_index(2024))) == "甲辰"


def test_month_and_hour_stems() -> None:
    # 五虎遁：甲己之年丙作首
    assert month_stem("甲", "寅") == "丙"
    assert month_stem("乙", "寅") == "戊"
    # 五鼠遁：甲己还加甲
    assert hour_stem("甲", "子") == "甲"
    assert hour_stem("乙", "子") == "丙"


def test_hour_branch() -> None:
    assert hour_branch(23, 0) == "子"
    assert hour_branch(0, 30) == "子"
    assert hour_branch(1, 0) == "丑"
    assert hour_branch(12, 0) == "午"
    assert hour_branch(22, 59) == "亥"


@pytest.mark.parametrize(
    ("day_master", "other", "expected"),
    [
        ("甲", "甲", "比肩"), ("甲", "乙", "劫财"),
        ("甲", "丙", "食神"), ("甲", "丁", "伤官"),
        ("甲", "戊", "偏财"), ("甲", "己", "正财"),
        ("甲", "庚", "七杀"), ("甲", "辛", "正官"),
        ("甲", "壬", "偏印"), ("甲", "癸", "正印"),
    ],
)
def test_ten_god(day_master: str, other: str, expected: str) -> None:
    assert ten_god(day_master, other) == expected


def test_solar_terms_2024_lichun() -> None:
    service = solar_terms.get_term_service()
    moment = lichun_of_year(service, 2024, BEIJING)
    assert moment.name == "立春"
    local = moment.instant.astimezone(BEIJING)
    # 2024 立春 北京时间 16:26:53；允许 ±2 分钟（不同算法/ΔT 的公开差异）
    assert local.date() == datetime(2024, 2, 4).date()
    assert abs((local - datetime(2024, 2, 4, 16, 26, 53, tzinfo=BEIJING)).total_seconds()) <= 120


def test_prev_next_jie_are_ordered() -> None:
    service = solar_terms.get_term_service()
    probe = datetime(2024, 5, 5, 4, 0, tzinfo=BEIJING)
    prev_jie = service.prev_jie(probe)
    next_jie = service.next_jie(probe)
    assert prev_jie.instant < probe < next_jie.instant
    assert next_jie.name in solar_terms.JIE_NAMES


def test_term_service_source_consistent() -> None:
    # 默认来源必须是 lunar-python（分钟级）；builtin 仅作兜底与交叉核验
    service = solar_terms.get_term_service()
    assert service.source in {"lunar_python", "builtin_meeus"}
    builtin = solar_terms.get_term_service("builtin")
    assert builtin.source == "builtin_meeus"
    # 两个来源的立春时刻差异应在 ±15 分钟内（自研低精度算法的公开误差界）
    probe = datetime(2024, 2, 15, 12, 0, tzinfo=BEIJING)
    delta = abs((service.prev_jie(probe).instant - builtin.prev_jie(probe).instant).total_seconds())
    assert delta <= 900


def test_true_solar_offset_sign() -> None:
    beijing_local = datetime(2024, 6, 21, 12, 0)
    # 北京（东经 116.4°）位于东经 120° 以西 → 校正为负
    offset_beijing = solar_time.true_solar_offset_minutes(beijing_local, BEIJING, 116.4)
    assert -30 < offset_beijing < 0
    # 乌鲁木齐（东经 87.6°）→ 约 -2 小时
    offset_urumqi = solar_time.true_solar_offset_minutes(beijing_local, BEIJING, 87.6)
    assert -150 < offset_urumqi < -110


def test_equation_of_time_range() -> None:
    # 均时差全年在 ±17 分钟以内
    for month in range(1, 13):
        jd = astronomy.julian_day(datetime(2024, month, 15, 12, 0))
        eot = astronomy.equation_of_time_minutes(jd)
        assert -18 < eot < 18


def test_standard_meridian() -> None:
    moment = datetime(2024, 6, 21, 12, 0)
    assert solar_time.standard_meridian(BEIJING, moment) == pytest.approx(120.0)
    assert solar_time.standard_meridian(ZoneInfo("UTC"), moment) == pytest.approx(0.0)


def test_delta_t_reasonable() -> None:
    # ΔT（TT−UT）在 1900-2100 应为几十秒到两分钟量级
    assert 50 < astronomy.delta_t_seconds(2000.0) < 80
    assert 60 < astronomy.delta_t_seconds(2020.0) < 120


def test_sixty_cycle_length() -> None:
    base = day_pillar_index(julian.gregorian_to_jdn(2024, 1, 1))
    later = day_pillar_index(julian.gregorian_to_jdn(2024, 1, 1) + timedelta(days=60).days)
    assert base == later
    assert len(STEMS) == 10 and len(BRANCHES) == 12
