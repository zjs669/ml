"""六爻（京房纳甲）引擎：只产出确定性盘面事实，不做任何吉凶判断。

固定顺序：定月建日辰 → 起卦 → 本卦/动爻 → 变卦、互卦 → 纳甲、六亲、六神、世应 → 旬空。
任何一步都不是「可选流派」，因此没有分支；口径只影响日的边界与六亲的对照基准。

红线：不输出旺衰、生克制化、用神、应期与吉凶断语。盘面之外的东西一律不做。
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings
from app.domains.bazi.schemas import ChartResult
from app.domains.calendar_core.jiazi import (
    BRANCHES,
    JIE_TO_MONTH_BRANCH,
    day_pillar_index,
    hour_branch,
    pillar_of_index,
    pillar_text,
)
from app.domains.calendar_core.astronomy import gregorian_to_jdn
from app.domains.calendar_core.lunar import solar_to_lunar
from app.domains.calendar_core.solar_terms import SolarTermService, get_term_service
from app.domains.liuyao import constants as C
from app.domains.liuyao.hexagrams import (
    HexagramInfo,
    hexagram_from_bits,
    lines_payload,
)
from app.domains.liuyao.schemas import LiuyaoConvention, LiuyaoInput

#: 老阴/老阳为动爻
MOVING_VALUES = (6, 9)
YANG_VALUES = (7, 9)


def _resolve_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"未知时区: {name}（需要安装 tzdata）") from exc


def _derived_seed(local_dt: datetime) -> int:
    """未给 seed 时，由起卦时刻派生一个稳定种子（不依赖机器时区）。"""
    return int(local_dt.strftime("%Y%m%d%H%M%S")) % 2**32


def _coins(seed: int) -> list[int]:
    """三枚铜钱掷六次：每枚记 2（字/阴）或 3（背/阳），三枚之和为 6–9。

    用 `random.Random(seed)` 而非全局随机源，保证同 seed 同结果，可复现、可回归。
    这不是「真随机」，正式占问请用实体铜钱后手填。
    """
    rng = random.Random(seed)
    return [sum(rng.choice((2, 3)) for _ in range(3)) for _ in range(6)]


def _time_numbers(lunar, hour_index: int) -> tuple[int, int, int]:
    """梅花易数取数：年支序数（子1…亥12）+ 农历月 + 农历日，再加时支序数。

    返回 (上卦数, 下卦数, 动爻位)，余 0 时分别取 8、8、6。
    """
    year_number = BRANCHES.index(lunar.year_ganzhi[1]) + 1
    month_number = abs(lunar.month)
    day_number = lunar.day
    hour_number = hour_index + 1

    upper_number = (year_number + month_number + day_number) % 8 or 8
    lower_number = (year_number + month_number + day_number + hour_number) % 8 or 8
    moving = (year_number + month_number + day_number + hour_number) % 6 or 6
    return upper_number, lower_number, moving


def _time_values(lunar, hour_index: int) -> tuple[list[int], dict[str, Any]]:
    upper_number, lower_number, moving = _time_numbers(lunar, hour_index)
    upper = C.XIAN_TIAN_NUMBER[upper_number]
    lower = C.XIAN_TIAN_NUMBER[lower_number]
    bits = C.TRIGRAM_BITS[lower] + C.TRIGRAM_BITS[upper]
    values: list[int] = []
    for index, bit in enumerate(bits):
        if index + 1 == moving:
            values.append(9 if bit == "1" else 6)
        else:
            values.append(7 if bit == "1" else 8)
    detail = {
        "upper_number": upper_number,
        "lower_number": lower_number,
        "moving_position": moving,
        "year_number": BRANCHES.index(lunar.year_ganzhi[1]) + 1,
        "month_number": abs(lunar.month),
        "day_number": lunar.day,
        "hour_number": hour_index + 1,
    }
    return values, detail


def _hexagram_block(
    info: HexagramInfo,
    *,
    values: list[int] | None,
    day_stem: str,
    palace_element: str | None = None,
) -> dict[str, Any]:
    lines = lines_payload(info, day_stem=day_stem, palace_element=palace_element)
    if values is not None:
        for line, value in zip(lines, values, strict=False):
            line["value"] = value
            line["moving"] = value in MOVING_VALUES
    return {
        "name": info.name,
        "upper": info.upper,
        "lower": info.lower,
        "bits": info.bits,
        "palace": info.palace,
        "palace_element": info.palace_element,
        "phase": info.phase,
        "shi": info.shi,
        "ying": info.ying,
        "is_pure": info.upper == info.lower,
        "lines": lines,
    }


def _markers(
    *,
    original: dict[str, Any],
    moving_lines: list[int],
    kong: tuple[str, str],
) -> list[dict[str, Any]]:
    """结构性标记：只陈述盘面结构，不作吉凶判断。

    刻意避开「上卦/下卦/XX卦」这类字眼，避免与报告校验链的卦名词表扫描互相误伤。
    """
    markers: list[dict[str, Any]] = []

    def emit(rule_id: str, relation: str, label: str, members: list[str], note: str, priority: int) -> None:
        markers.append(
            {
                "rule_id": rule_id,
                "system": "liuyao",
                "kind": "structure",
                "relation": relation,
                "members": members,
                "topic": "structure",
                "priority": priority,
                "note": note,
                "source_ref": "liuyao.zengshanbuyi",
                "version": settings.liuyao_algorithm_version,
                "scope": "line",
                "positions": [label],
                "label": label,
            }
        )

    if not moving_lines:
        emit("liuyao.moving.none", "静盘", "无动爻", [], "六爻皆为少阴少阳，无动爻，本盘无变化之爻。", 40)
    elif len(moving_lines) >= 2:
        emit(
            "liuyao.moving.multiple",
            "多爻动",
            "动爻",
            [f"{item}爻" for item in moving_lines],
            f"共 {len(moving_lines)} 个动爻（第 {'、'.join(str(item) for item in moving_lines)} 爻），属结构性事实。",
            45,
        )

    if original["is_pure"]:
        emit(
            "liuyao.palace.pure",
            "八纯",
            "本宫",
            [original["name"]],
            f"上下同为{original['upper']}，属八纯之列。",
            50,
        )
    if original["phase"] in ("游魂", "归魂"):
        emit(
            f"liuyao.palace.{C.PHASE_SLUG[original['phase']]}",
            original["phase"],
            original["phase"],
            [original["name"]],
            f"本卦在{original['palace']}宫中属{original['phase']}之位，属结构性事实。",
            48,
        )

    shi_line = next(line for line in original["lines"] if line["shi"])
    if shi_line["branch"] in kong:
        emit(
            "liuyao.shi.kong",
            "世爻旬空",
            "世爻",
            [f"{shi_line['position']}爻"],
            f"世爻纳甲{shi_line['najia']}，其地支{shi_line['branch']}正落本旬空亡（{'、'.join(kong)}）。",
            46,
        )
    return markers


def calculate(
    inp: LiuyaoInput,
    conv: LiuyaoConvention | None = None,
    service: SolarTermService | None = None,
) -> ChartResult:
    conv = conv or LiuyaoConvention()
    service = service or get_term_service()
    tz = _resolve_zone(inp.timezone)
    warnings: list[str] = []

    local_dt = inp.cast_datetime
    instant = local_dt.replace(tzinfo=tz).astimezone(timezone.utc)

    # ---- 1. 日辰：受换日口径影响 ----
    day_date = local_dt.date()
    if conv.day_boundary == "zi_hour_policy_a" and local_dt.hour >= 23:
        day_date = day_date + timedelta(days=1)
        warnings.append("起卦时刻在 23:00 之后：日辰按四柱的「23:00 换日」口径归入次日。")
    day_index = day_pillar_index(gregorian_to_jdn(day_date.year, day_date.month, day_date.day))
    day_pillar = pillar_of_index(day_index)

    # ---- 2. 月建：以「节」为界 ----
    prev_jie = service.prev_jie(instant)
    month_branch = JIE_TO_MONTH_BRANCH.get(prev_jie.name)
    if month_branch is None:  # pragma: no cover - 数据异常
        raise RuntimeError(f"节气 {prev_jie.name} 不是定月之节")

    branch_text = hour_branch(local_dt.hour, local_dt.minute)
    hour_index = BRANCHES.index(branch_text)
    lunar = solar_to_lunar(local_dt)

    # ---- 3. 起卦 ----
    time_detail: dict[str, Any] | None = None
    seed_used: int | None = None
    if inp.method == "coins":
        seed_used = inp.seed if inp.seed is not None else _derived_seed(local_dt)
        values = _coins(seed_used)
    elif inp.method == "time":
        values, time_detail = _time_values(lunar, hour_index)
    else:
        values = list(inp.lines or [])

    bits = "".join("1" if value in YANG_VALUES else "0" for value in values)
    moving_lines = [index + 1 for index, value in enumerate(values) if value in MOVING_VALUES]
    changed_bits = "".join(
        ("0" if bit == "1" else "1") if index + 1 in moving_lines else bit
        for index, bit in enumerate(bits)
    )

    original = hexagram_from_bits(bits)
    original_block = _hexagram_block(
        original, values=values, day_stem=day_pillar[0]
    )

    # ---- 4. 变卦 / 互卦 ----
    changed_block: dict[str, Any] | None = None
    if moving_lines:
        changed = hexagram_from_bits(changed_bits)
        changed_block = _hexagram_block(
            changed,
            values=values,
            day_stem=day_pillar[0],
            # 变爻六亲仍以本卦卦宫为「我」，这是京房纳甲的通例
            palace_element=original.palace_element,
        )
        by_position = {line["position"]: line for line in changed_block["lines"]}
        for line in original_block["lines"]:
            if line["moving"]:
                counterpart = by_position[line["position"]]
                line["changed"] = {
                    "polarity": counterpart["polarity"],
                    "najia": counterpart["najia"],
                    "element": counterpart["element"],
                    "six_relation": counterpart["six_relation"],
                }

    # 互卦：二三四爻为下、三四五爻为上
    mutual_bits = bits[1:4] + bits[2:5]
    mutual = hexagram_from_bits(mutual_bits)
    mutual_block = {
        "name": mutual.name,
        "upper": mutual.upper,
        "lower": mutual.lower,
        "palace": mutual.palace,
    }

    # ---- 5. 旬空 ----
    kong = C.xun_kong(day_index)

    markers = _markers(original=original_block, moving_lines=moving_lines, kong=kong)

    chart_facts: dict[str, Any] = {
        "method": inp.method,
        "method_label": C.METHOD_LABELS[inp.method],
        "cast_at": local_dt.strftime("%Y-%m-%d %H:%M"),
        "timezone": str(tz),
        "lunar_date": {
            "year": lunar.year,
            "month": lunar.month,
            "day": lunar.day,
            "is_leap_month": lunar.is_leap_month,
            "text": lunar.text,
            "year_ganzhi": lunar.year_ganzhi,
        },
        "hour_branch": branch_text,
        "day_pillar": {
            "text": pillar_text(day_pillar),
            "stem": day_pillar[0],
            "branch": day_pillar[1],
        },
        "month_build": {
            "branch": month_branch,
            "jie": prev_jie.name,
            "text": f"{month_branch}月",
            "source": prev_jie.source,
        },
        "xun_kong": list(kong),
        "liu_shen_order": list(C.liu_shen_of(day_pillar[0])),
        "seed": seed_used,
        "time_numbers": time_detail,
        "question": inp.question if inp.store_question else None,
        "question_stored": bool(inp.store_question and inp.question),
        "values": values,
        "moving_lines": moving_lines,
        "original": original_block,
        "changed": changed_block,
        "mutual": mutual_block,
    }

    input_summary = {
        "method": inp.method,
        "cast_at": local_dt.isoformat(timespec="minutes"),
        "timezone": inp.timezone,
        "seed": seed_used,
        "lines": values,
        "question": inp.question if inp.store_question else None,
    }

    convention_dump = conv.model_dump()
    convention_dump["school_note"] = C.SCHOOL_NOTE
    warnings.append(C.SCHOOL_NOTE)
    if inp.method == "time":
        warnings.append(
            "时间起卦按梅花易数取数法产生单个动爻；铜钱起卦与手动输入则可能出现多个动爻，"
            "两者不可混为一谈。"
        )
    if inp.method == "coins":
        warnings.append(
            "铜钱起卦由 `random.Random(seed)` 模拟，仅用于复现与联调，不构成真随机；"
            "正式使用请掷实体铜钱后手动输入。"
        )
    if inp.question and not inp.store_question:
        warnings.append("已按你的选择丢弃占问原文，命盘只保存起卦方式与时刻。")

    source_refs = [
        {"type": "rule", "id": "liuyao.palace.eight", "note": "京房八宫卦序与世应定位"},
        {"type": "rule", "id": "liuyao.najia.trigram", "note": "八经卦内外卦纳甲表"},
        {"type": "rule", "id": "liuyao.relation.palace", "note": "六亲以本卦卦宫五行为我，按生克推导"},
        {"type": "rule", "id": "liuyao.liu_shen.day_stem", "note": "六神按日干起于初爻顺排"},
        {"type": "rule", "id": "liuyao.xun_kong.day_pillar", "note": "旬空按日柱所在旬推算"},
        {"type": "rule", "id": "liuyao.time_numbers", "note": "时间起卦：年支+月+日取上卦，再加时支取下卦与动爻"},
        {"type": "book", "id": "liuyao.zengshanbuyi", "note": "《增删卜易》通行装卦法，本仓库只取结构与事实，不取断语"},
    ]

    return ChartResult(
        domain="liuyao",
        algorithm_version=settings.liuyao_algorithm_version,
        input_summary=input_summary,
        convention=convention_dump,
        chart_facts=chart_facts,
        triggered_rules=markers,
        warnings=warnings,
        source_refs=source_refs,
    )
