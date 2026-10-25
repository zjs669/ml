"""交叉核验脚本：自研四柱引擎 vs lunar-python（独立实现）。

用法：
    python -m scripts.crosscheck                 # 默认抽样 400 例
    python -m scripts.crosscheck --samples 2000  # 更大样本
    python -m scripts.crosscheck --terms 1990 1992

判定标准：
- 四柱（年/月/日/时）两套换日口径都必须逐字一致；
- 节气时刻与自研 Meeus 推算的差值允许 ≤ 20 分钟（自研为低精度兜底，见 astronomy.py 说明）。

退出码非 0 表示存在超差，必须修代码而不是改样例。
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone

from lunar_python import Solar

from app.domains.bazi.engine import calculate
from app.domains.bazi.schemas import BaziInput, Convention
from app.domains.calendar_core.solar_terms import BEIJING, get_term_service

TERM_TOLERANCE_MINUTES = 20.0


def _lunar_pillars(dt: datetime, sect: int) -> str:
    solar = Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)
    eight = solar.getLunar().getEightChar()
    eight.setSect(sect)
    return " ".join([eight.getYear(), eight.getMonth(), eight.getDay(), eight.getTime()])


def _our_pillars(dt: datetime, policy: str) -> str:
    result = calculate(
        BaziInput(birth_datetime=dt, timezone="Asia/Shanghai", gender="male"),
        Convention(day_boundary=policy),
    )
    pillars = result.chart_facts["pillars"]
    return " ".join(pillars[key]["text"] for key in ("year", "month", "day", "hour"))


def _sampled_datetimes(samples: int, seed: int = 20261024) -> list[datetime]:
    rng = random.Random(seed)
    base = datetime(1901, 1, 1, 0, 0)
    span_days = (datetime(2099, 12, 31) - base).days
    result: list[datetime] = []
    for _ in range(samples):
        day_offset = rng.randint(0, span_days)
        hour = rng.choice([0, 1, 4, 6, 9, 12, 15, 18, 21, 22, 23])
        minute = rng.choice([0, 7, 29, 45, 59])
        result.append(base + timedelta(days=day_offset, hours=hour, minutes=minute))
    return result


def check_pillars(samples: int) -> list[str]:
    diffs: list[str] = []
    for dt in _sampled_datetimes(samples):
        for policy, sect in (("zi_hour_policy_a", 1), ("zi_hour_policy_b", 2)):
            ours = _our_pillars(dt, policy)
            theirs = _lunar_pillars(dt, sect)
            if ours != theirs:
                diffs.append(f"{dt} [{policy}/sect{sect}] ours={ours} lunar={theirs}")
    return diffs


def check_terms(years: list[int]) -> list[str]:
    service = get_term_service("builtin")
    problems: list[str] = []
    for year in years:
        for month in (2, 5, 8, 11):
            probe = datetime(year, month, 15, 12, 0, tzinfo=BEIJING).astimezone(timezone.utc)
            ours_prev, ours_next = service.builtin_prev_next(probe)
            theirs_prev, _ = service.prev_next_jie(probe)
            delta = abs((ours_prev.instant - theirs_prev.instant).total_seconds()) / 60
            if ours_prev.name != theirs_prev.name or delta > TERM_TOLERANCE_MINUTES:
                problems.append(
                    f"{year}-{month:02d} 节名 ours={ours_prev.name} lunar={theirs_prev.name} "
                    f"差值={delta:.1f} 分钟"
                )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="四柱引擎交叉核验")
    parser.add_argument("--samples", type=int, default=400)
    parser.add_argument("--terms", nargs="*", type=int, default=list(range(1901, 2100, 9)))
    args = parser.parse_args()

    pillar_diffs = check_pillars(args.samples)
    term_diffs = check_terms(args.terms)

    total_checks = args.samples * 2
    print(f"四柱核验：{total_checks - len(pillar_diffs)}/{total_checks} 一致")
    for line in pillar_diffs[:20]:
        print("  [DIFF]", line)
    print(f"节气核验：{len(args.terms) * 4 - len(term_diffs)}/{len(args.terms) * 4} 在 {TERM_TOLERANCE_MINUTES} 分钟内")
    for line in term_diffs[:20]:
        print("  [TERM]", line)

    if pillar_diffs or term_diffs:
        print("存在超差项，需修复。")
        return 1
    print("全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
