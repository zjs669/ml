"""大运推算。

口径（写死在代码里并在结果中回显，不做隐式约定）：
- 顺逆：阳年男 / 阴年女 顺排；阴年男 / 阳年女 逆排。
- 起运：顺排数到「下一个节」，逆排数到「上一个节」；3 日折 1 年、1 日折 4 个月、
  1 个时辰（2 小时）折 10 天。
- 排运：从月柱起，顺排取后续干支，逆排取前序干支，每步 10 年。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.domains.calendar_core.jiazi import (
    BRANCHES,
    STEM_YANG,
    jiazi_index,
    pillar_of_index,
    pillar_text,
)


def _add_ymd(years: int, months: int, days: int, base: datetime) -> datetime:
    total_months = base.year * 12 + (base.month - 1) + years * 12 + months
    year, month = divmod(total_months, 12)
    month += 1
    day = min(base.day, 28 if month == 2 else 30)
    return datetime(year, month, day) + timedelta(days=days)


def compute_dayun(
    *,
    month_pillar: tuple[str, str],
    year_stem: str,
    gender: str,
    birth_instant: datetime,
    birth_local: datetime,
    prev_jie,
    next_jie,
    steps: int = 8,
) -> dict:
    if gender == "unknown":
        return {
            "computed": False,
            "reason": "性别未知：起运顺逆依赖「阳年男/阴年女顺排」规则，未提供性别时不推算大运。",
        }

    yang_year = STEM_YANG[year_stem]
    forward = (yang_year and gender == "male") or (not yang_year and gender == "female")

    if forward:
        delta = next_jie.instant - birth_instant
        anchor = next_jie
    else:
        delta = birth_instant - prev_jie.instant
        anchor = prev_jie

    delta_days = max(delta.total_seconds() / 86400.0, 0.0)
    years_f = delta_days / 3.0
    years = int(years_f)
    rem_days = delta_days - years * 3
    months = int(rem_days * 4)
    rem_month_f = rem_days * 4 - months
    days = int(rem_month_f * 30)

    start_age_text = f"{years}年{months}个月{days}天"
    start_datetime = _add_ymd(years, months, days, birth_local)

    month_index = BRANCHES.index(month_pillar[1])
    start_index = jiazi_index(*month_pillar)
    fortune: list[dict] = []
    for step in range(1, steps + 1):
        offset = step if forward else -step
        pillar = pillar_of_index(start_index + offset)
        fortune.append(
            {
                "index": step,
                "pillar": pillar_text(pillar),
                "start_age_years": years + (step - 1) * 10,
                "end_age_years": years + step * 10 - 1,
                "start_year": _add_ymd(years + (step - 1) * 10, months, days, birth_local).year,
            }
        )

    return {
        "computed": True,
        "forward": forward,
        "rule": "阳年男/阴年女顺排，阴年男/阳年女逆排；3 日折 1 年",
        "anchor_jie": {"name": anchor.name, "local": anchor.instant.isoformat()},
        "start_offset_days": round(delta_days, 4),
        "start_age": {"years": years, "months": months, "days": days, "text": start_age_text},
        "start_datetime_estimate": start_datetime.strftime("%Y-%m-%d %H:%M"),
        "error_bound": "起运以 3 日折 1 年近似，交节时刻与出生时刻精度约 1 分钟，起运时间可能有数日级误差。",
        "list": fortune,
        "month_branch_index": month_index,
    }
