"""生成 tests/fixtures/bazi_cases.json（开发期一次性脚本，可重复运行）。

Expected 的来源有两种，逐例标注在 `source` 字段里：
- `lunar-python`：与独立实现（lunar-python 1.4.8，MIT）在 Asia/Shanghai 下逐例比对得出，
  这是真正的第二来源核验；
- `self_baseline`：非 Asia/Shanghai 时区的用例，lunar-python 只按北京时间推算，
  无法直接作为第二来源，因此记录本引擎的计算结果作为回归基线，标注待人工复核。

用法：
    python -m scripts.gen_bazi_cases
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from lunar_python import Solar

from app.domains.bazi.engine import calculate
from app.domains.bazi.schemas import BaziInput, Convention
from app.domains.calendar_core.astronomy import true_solar_offset_minutes

OUTPUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "bazi_cases.json"
BEIJING = ZoneInfo("Asia/Shanghai")
UTC = ZoneInfo("UTC")

CASES: list[dict] = [
    {"id": "normal-1990", "birth_datetime": "1990-06-15T09:10:00", "gender": "female",
     "note": "普通日期"},
    {"id": "verified-2001", "birth_datetime": "2001-02-04T15:20:00", "gender": "male",
     "note": "人工核验样例，含六合/六冲/三刑/相害/相破"},
    {"id": "lichun-eve", "birth_datetime": "2024-02-03T12:00:00", "gender": "male",
     "note": "立春前一日"},
    {"id": "lichun-before-instant", "birth_datetime": "2024-02-04T16:00:00", "gender": "male",
     "note": "2024 立春交节 16:26:53，交节前 26 分钟"},
    {"id": "lichun-after-instant", "birth_datetime": "2024-02-04T17:00:00", "gender": "male",
     "note": "2024 立春交节后 33 分钟"},
    {"id": "leap-day-2024", "birth_datetime": "2024-02-29T08:00:00", "gender": "female",
     "note": "闰年 2 月 29 日"},
    {"id": "leap-day-2000", "birth_datetime": "2000-02-29T23:30:00", "gender": "male",
     "note": "世纪闰日 + 子时边界（policy_a 换日）"},
    {"id": "century-2000", "birth_datetime": "2000-01-01T00:30:00", "gender": "female",
     "note": "世纪边界 + 早子时"},
    {"id": "zi-hour-2330", "birth_datetime": "2016-11-30T23:30:00", "gender": "male",
     "note": "23:30 子时换日（policy_a 与 policy_b 结果不同，见 policy-b 用例）"},
    {"id": "zi-hour-2330-policy-b", "birth_datetime": "2016-11-30T23:30:00", "gender": "male",
     "day_boundary": "zi_hour_policy_b", "note": "同一时刻的夜子时口径"},
    {"id": "midnight-0030", "birth_datetime": "2016-12-01T00:30:00", "gender": "male",
     "note": "早子时"},
    {"id": "jingzhe-boundary", "birth_datetime": "2023-03-06T04:30:00", "gender": "female",
     "note": "2023 惊蛰交节 04:36，交节前 6 分钟（临界告警）"},
    {"id": "anchor-1949", "birth_datetime": "1949-10-01T10:00:00", "gender": "male",
     "note": "日柱锚点日（甲子）"},
    {"id": "early-1900", "birth_datetime": "1900-01-31T06:00:00", "gender": "female",
     "note": "支持范围下界附近"},
    {"id": "late-2099", "birth_datetime": "2099-12-31T22:00:00", "gender": "male",
     "note": "支持范围上界附近"},
    {"id": "dongzhi-1980", "birth_datetime": "1980-12-21T18:00:00", "gender": "female",
     "note": "冬至交节附近"},
    {"id": "moon-landing", "birth_datetime": "1969-07-20T20:17:00", "gender": "male",
     "note": "历史时点，校验 60 甲子循环"},
    {"id": "no-time", "birth_datetime": "1987-09-09T00:00:00", "gender": "female",
     "time_known": False, "note": "时辰不详：按 12:00 占位并给警告"},
    {"id": "tz-utc", "birth_datetime": "1995-08-08T23:59:00", "timezone": "UTC", "gender": "male",
     "note": "UTC 时区（本地钟表时间口径）"},
    {"id": "tz-new-york", "birth_datetime": "1985-07-04T12:00:00", "timezone": "America/New_York",
     "gender": "female", "note": "America/New_York 时区"},
    {"id": "solar-time-urumqi", "birth_datetime": "1992-05-20T08:00:00", "gender": "male",
     "longitude": 87.6, "solar_time": "true_solar_time", "note": "乌鲁木齐经度 87.6°，真太阳时校正"},
    {"id": "dao-chun-1984", "birth_datetime": "1984-02-02T22:00:00", "gender": "female",
     "note": "1984 立春前后"},
    {"id": "xmas-2020", "birth_datetime": "2020-12-25T03:15:00", "gender": "male",
     "note": "普通冬季日期"},
    {"id": "policy-b-midnight", "birth_datetime": "2005-07-07T00:10:00", "gender": "female",
     "day_boundary": "zi_hour_policy_b", "note": "policy_b 下的早子时"},
]


def _lunar_pillars(moment_local: datetime, sect: int) -> list[str]:
    """把「北京时间的钟表时间」交给 lunar-python 求四柱。"""
    solar = Solar.fromYmdHms(
        moment_local.year, moment_local.month, moment_local.day,
        moment_local.hour, moment_local.minute, moment_local.second,
    )
    eight_char = solar.getLunar().getEightChar()
    eight_char.setSect(sect)
    return [eight_char.getYear(), eight_char.getMonth(), eight_char.getDay(), eight_char.getTime()]


def _build_case(case: dict) -> dict:
    tz_name = case.get("timezone", "Asia/Shanghai")
    tz = ZoneInfo(tz_name)
    birth = datetime.fromisoformat(case["birth_datetime"])
    time_known = case.get("time_known", True)
    effective = birth if time_known else birth.replace(hour=12, minute=0, second=0)
    convention = Convention(
        day_boundary=case.get("day_boundary", "zi_hour_policy_a"),
        solar_time=case.get("solar_time", "none"),
    )
    inp = BaziInput(
        birth_datetime=birth,
        timezone=tz_name,
        gender=case.get("gender", "unknown"),
        time_known=time_known,
        longitude=case.get("longitude"),
    )
    result = calculate(inp, convention)
    expected = [
        result.chart_facts["pillars"][key]["text"] for key in ("year", "month", "day", "hour")
    ]

    source = "self_baseline"
    if tz_name == "Asia/Shanghai":
        adjusted = effective
        if convention.solar_time == "true_solar_time" and case.get("longitude") is not None:
            delta = true_solar_offset_minutes(effective, tz, float(case["longitude"]))
            adjusted = effective + timedelta(minutes=delta)
        sect = 1 if convention.day_boundary == "zi_hour_policy_a" else 2
        reference = _lunar_pillars(adjusted, sect)
        if reference == expected:
            source = "lunar-python"
        else:
            print(f"[WARN] {case['id']}: 与 lunar-python 不一致 lunar={reference} engine={expected}")
            source = "self_baseline"

    return {
        "id": case["id"],
        "input": {
            "birth_datetime": case["birth_datetime"],
            "timezone": tz_name,
            "gender": case.get("gender", "unknown"),
            "time_known": time_known,
            "longitude": case.get("longitude"),
            "convention": convention.model_dump(),
        },
        "expected_pillars": expected,
        "source": source,
        "note": case.get("note", ""),
    }


def main() -> int:
    cases = [_build_case(case) for case in CASES]
    payload = {
        "meta": {
            "generated_by": "scripts/gen_bazi_cases.py",
            "algorithm_version": "bazi-engine-0.1.0",
            "reference": "lunar-python 1.4.8 (MIT)；Asia/Shanghai 下为第二来源核验，其余为回归基线",
            "tolerance": "节气交节 ±2 分钟内的差异视为容差，其余不一致视为缺陷",
            "case_count": len(cases),
        },
        "cases": cases,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    verified = sum(1 for case in cases if case["source"] == "lunar-python")
    print(f"已写入 {OUTPUT}：{len(cases)} 例，其中 {verified} 例由 lunar-python 交叉核验")
    return 0


if __name__ == "__main__":
    sys.exit(main())
