"""四柱反查引擎测试。

最重要的一条是「往返一致」：随机抽 500 个真实时刻，用 engine 正排得到四柱，
再用反查把这四柱还原成日期，必须命中原始日期且时辰窗口覆盖原始时刻。
这一条同时锁住了反查层与 engine 的口径一致性（换日、立春、节气、真太阳时）。
"""

from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta

import pytest
from pydantic import ValidationError

from app.domains.bazi.engine import calculate
from app.domains.bazi.reverse import (
    InconsistentPillars,
    ReverseQueryTooLoose,
    resolve_timezone,
    reverse_search,
)
from app.domains.bazi.schemas import BaziInput, Convention
from app.domains.calendar_core.solar_terms import get_term_service
from app.schemas.reverse import PillarQuery, ReverseSearchIn

TZ = resolve_timezone("Asia/Shanghai")
SERVICE = get_term_service()


def _pillars_at(moment: datetime, *, conv: Convention, longitude: float | None = None) -> dict[str, str]:
    result = calculate(
        BaziInput(birth_datetime=moment, timezone="Asia/Shanghai", longitude=longitude),
        conv,
    )
    return {
        "year": result.chart_facts["pillars"]["year"]["text"],
        "month": result.chart_facts["pillars"]["month"]["text"],
        "day": result.chart_facts["pillars"]["day"]["text"],
        "hour": result.chart_facts["pillars"]["hour"]["text"],
    }


def _search(
    pillars: dict[str, str | None],
    *,
    start: date,
    end: date,
    conv: Convention | None = None,
    longitude: float | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict:
    return reverse_search(
        PillarQuery(**pillars),
        start=start,
        end=end,
        tz=TZ,
        conv=conv or Convention(),
        service=SERVICE,
        longitude=longitude,
        limit=limit,
        offset=offset,
    )


def _window_covers(label: str, moment: datetime, day: date) -> bool:
    raw = label.replace("（次日）", "")
    start_text, end_text = raw.split("-")
    sh, sm = (int(part) for part in start_text.split(":"))
    eh, em = (int(part) for part in end_text.split(":"))
    window_start = datetime.combine(day, time(sh, sm))
    window_end = datetime.combine(day, time(eh, em))
    if window_end <= window_start:
        window_end += timedelta(days=1)
    return window_start <= moment < window_end


def test_round_trip_500_random_instants() -> None:
    rng = random.Random(20261024)
    base = date(1800, 1, 1)
    span_days = (date(2199, 12, 31) - base).days
    for _ in range(500):
        moment = datetime.combine(
            base + timedelta(days=rng.randrange(span_days)),
            time(rng.randrange(24), rng.randrange(60)),
        )
        expected = _pillars_at(moment, conv=Convention())
        result = _search(
            expected,
            start=moment.date() - timedelta(days=90),
            end=moment.date() + timedelta(days=90),
        )
        hit = [item for item in result["candidates"] if item["date"] == moment.date()]
        assert hit, f"{moment} 的四柱 {expected} 未被反查命中，诊断：{result['diagnosis']}"
        assert hit[0]["pillars"] == expected
        assert any(
            _window_covers(label, moment, moment.date()) for label in hit[0]["hour_windows"]
        ), f"{moment} 不在任何返回窗口中：{hit[0]['hour_windows']}"


def test_full_four_pillars_hits_single_day() -> None:
    moment = datetime(1990, 5, 20, 12, 30)
    expected = _pillars_at(moment, conv=Convention())
    result = _search(expected, start=date(1990, 1, 1), end=date(1990, 12, 31))
    assert result["total_matches"] == 1
    assert result["candidates"][0]["date"] == date(1990, 5, 20)
    assert result["candidates"][0]["confidence"] == "exact"


def test_day_only_returns_many_days_and_truncates() -> None:
    day_pillar = _pillars_at(datetime(1990, 5, 20, 12, 0), conv=Convention())["day"]
    result = _search({"day": day_pillar}, start=date(1900, 1, 1), end=date(1909, 12, 31), limit=50)
    assert result["truncated"] is True
    assert len(result["candidates"]) == 50
    # 十年约 3653 天，日柱 60 天一循环 → 61 天左右
    assert abs(result["total_matches"] - 3653 / 60) <= 2
    assert result["candidates"][0]["confidence"] == "partial"
    assert "未限定时柱" in result["candidates"][0]["notes"][0]


def test_hour_without_day_still_works() -> None:
    moment = datetime(2001, 2, 4, 15, 20)
    expected = _pillars_at(moment, conv=Convention())
    result = _search(
        {"hour": expected["hour"], "year": expected["year"]},
        start=date(2001, 1, 1),
        end=date(2001, 12, 31),
    )
    assert result["total_matches"] >= 1
    assert any(item["date"] == date(2001, 2, 4) for item in result["candidates"])


def test_inconsistent_hour_is_rejected_with_expected_stem() -> None:
    # 辛亥日的寅时按五鼠遁是庚寅，给甲寅必须被拒绝并指出正确时干
    with pytest.raises(InconsistentPillars) as excinfo:
        _search(
            {"day": "辛亥", "hour": "甲寅"},
            start=date(1990, 1, 1),
            end=date(1990, 12, 31),
        )
    message = str(excinfo.value)
    assert "庚" in message
    assert "五鼠遁" in message


def test_hour_only_query_is_refused() -> None:
    with pytest.raises(ReverseQueryTooLoose):
        _search({"hour": "乙卯"}, start=date(1990, 1, 1), end=date(1990, 12, 31))


def test_range_too_large_is_rejected_by_schema() -> None:
    with pytest.raises(ValidationError):
        ReverseSearchIn(
            pillars={"day": "辛亥"},
            range_start=date(1800, 1, 1),
            range_end=date(2101, 1, 1),
        )


def test_reversed_range_is_rejected_by_schema() -> None:
    with pytest.raises(ValidationError):
        ReverseSearchIn(
            pillars={"day": "辛亥"},
            range_start=date(2000, 1, 1),
            range_end=date(1999, 1, 1),
        )


def test_illegal_ganzhi_is_rejected() -> None:
    with pytest.raises(ValidationError):
        PillarQuery(day="甲丑")  # 阳干配阴支，不在六十甲子内


def test_day_boundary_policies_yield_different_pillars() -> None:
    moment = datetime(1990, 5, 20, 23, 30)
    policy_a = _pillars_at(moment, conv=Convention(day_boundary="zi_hour_policy_a"))
    policy_b = _pillars_at(moment, conv=Convention(day_boundary="zi_hour_policy_b"))
    assert policy_a["day"] != policy_b["day"]

    result_a = _search(
        policy_a,
        start=date(1990, 5, 1),
        end=date(1990, 6, 30),
        conv=Convention(day_boundary="zi_hour_policy_a"),
    )
    result_b = _search(
        policy_b,
        start=date(1990, 5, 1),
        end=date(1990, 6, 30),
        conv=Convention(day_boundary="zi_hour_policy_b"),
    )
    assert result_a["candidates"][0]["date"] == date(1990, 5, 20)
    # 同一钟表时刻在两种口径下日柱不同，反查结果自然也不同
    assert result_a["candidates"][0]["pillars"] != result_b["candidates"][0]["pillars"]


def test_true_solar_time_shifts_window() -> None:
    moment = datetime(1990, 5, 20, 12, 30)
    longitude = 121.47
    conv = Convention(solar_time="true_solar_time")
    expected = _pillars_at(moment, conv=conv, longitude=longitude)
    result = _search(
        expected,
        start=date(1990, 5, 1),
        end=date(1990, 6, 30),
        conv=conv,
        longitude=longitude,
    )
    hit = [item for item in result["candidates"] if item["date"] == date(1990, 5, 20)]
    assert hit, result["diagnosis"]
    assert any(_window_covers(label, moment, moment.date()) for label in hit[0]["hour_windows"])


def test_impossible_combination_reports_diagnosis() -> None:
    moment = datetime(1990, 5, 20, 12, 0)
    expected = _pillars_at(moment, conv=Convention())
    # 把年柱改成一个与该日期完全无关的组合
    bogus = dict(expected)
    bogus["year"] = "甲子" if expected["year"] != "甲子" else "乙丑"
    result = _search(bogus, start=date(1990, 1, 1), end=date(1990, 12, 31))
    assert result["total_matches"] == 0
    assert result["diagnosis"]
    assert any("年柱" in item for item in result["diagnosis"])


def test_pagination_is_stable() -> None:
    first = _search({"day": "辛亥"}, start=date(1990, 1, 1), end=date(1995, 12, 31), limit=5)
    second = _search(
        {"day": "辛亥"}, start=date(1990, 1, 1), end=date(1995, 12, 31), limit=5, offset=5
    )
    assert first["candidates"] and second["candidates"]
    assert first["candidates"][0]["date"] != second["candidates"][0]["date"]
    assert first["total_matches"] == second["total_matches"]
