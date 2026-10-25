"""梅花易数引擎：起卦 → 本卦 → 互卦/变卦/错卦/综卦 → 体用。

固定顺序（任何一步都不是可选流派）：
1. 按起卦法得到「上卦数、下卦数、动爻数」；
2. 上卦数除 8 取余（余 0 作 8）→ 先天八卦；下卦同理；动爻数除 6 取余（余 0 作 6）；
3. 本卦 = 上卦 + 下卦；动爻所在卦为「用」，另一卦为「体」；
4. 互卦 = 本卦二三四爻为下卦、三四五爻为上卦；
5. 变卦 = 动爻阴阳互换后的六爻；
6. 错卦 = 六爻全变；综卦 = 六爻上下颠倒。

为什么复用 `liuyao.hexagrams`：六十四卦的卦名、卦宫、爻位结构在六爻域已经有
一份经过交叉校验的实现（`NAME_TO_INFO` + 独立推导测试）。梅花易数只需要
「六爻二进制 → 卦名」这一个能力，另写一份等于把 64 条数据抄两遍，迟早不一致。

红线：只输出卦象结构、体用五行与生克方向，不给吉凶结论、不给应期、不给建议。
"""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings
from app.domains.bazi.schemas import ChartResult
from app.domains.calendar_core.jiazi import BRANCHES, ELEMENTS, hour_branch
from app.domains.calendar_core.lunar import solar_to_lunar
from app.domains.liuyao import constants as LC
from app.domains.liuyao.hexagrams import hexagram_from_bits
from app.domains.meihua.schemas import MeihuaConvention, MeihuaInput

#: 先天八卦数 → 卦名（乾一 兑二 离三 震四 巽五 坎六 艮七 坤八）
NUMBER_TO_TRIGRAM: dict[int, str] = dict(LC.XIAN_TIAN_NUMBER)

#: 方位 → 卦名（后天八卦方位）
DIRECTION_TO_TRIGRAM: dict[str, str] = {
    "乾": "乾", "西北": "乾",
    "兑": "兑", "西": "兑",
    "离": "离", "南": "离",
    "震": "震", "东": "震",
    "巽": "巽", "东南": "巽",
    "坎": "坎", "北": "坎",
    "艮": "艮", "东北": "艮",
    "坤": "坤", "西南": "坤",
}

SCHOOL_NOTE = (
    "本版本只实现邵雍《梅花易数》通行法：先天八卦数起卦、动爻除六取余、"
    "动爻所在卦为用、另一卦为体、互卦取二三四与三四五爻、变卦只动一爻。"
    "体用只列五行与生克方向，不判断吉凶，也不推应期。"
)


def _resolve_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"未知时区: {name}（需要安装 tzdata）") from exc


def _mod8(value: int) -> int:
    """除 8 取余，余 0 作 8。"""
    return value % 8 or 8


def _mod6(value: int) -> int:
    """除 6 取余，余 0 作 6（上爻）。"""
    return value % 6 or 6


def _stroke_count(text: str) -> int:
    """字占取笔画数。

    这里只用「字数 × 固定基数」这种可复现的近似，不查笔画表：
    汉字笔画表体积大且各版本有差异，查表会引入一个无法验证的数据源。
    口径写进 warnings 明确告知用户这是近似值。
    """
    return len(text) * 10


def _from_time(inp: MeihuaInput) -> tuple[int, int, int, dict[str, Any]]:
    assert inp.cast_datetime is not None
    zone = _resolve_zone(inp.timezone)
    local_dt = inp.cast_datetime.replace(tzinfo=zone)
    lunar = solar_to_lunar(local_dt)
    year_number = BRANCHES.index(lunar.year_ganzhi[1]) + 1
    month_number = abs(lunar.month)
    day_number = lunar.day
    hour_index = BRANCHES.index(hour_branch(local_dt.hour, local_dt.minute))
    hour_number = hour_index + 1
    upper = _mod8(year_number + month_number + day_number)
    lower = _mod8(year_number + month_number + day_number + hour_number)
    moving = _mod6(year_number + month_number + day_number + hour_number)
    detail = {
        "lunar_date": lunar.text,
        "year_branch_number": year_number,
        "lunar_month": month_number,
        "lunar_day": day_number,
        "hour_branch_number": hour_number,
        "sum_upper": year_number + month_number + day_number,
        "sum_lower": year_number + month_number + day_number + hour_number,
    }
    return upper, lower, moving, detail


def _from_numbers(inp: MeihuaInput) -> tuple[int, int, int, dict[str, Any]]:
    assert inp.numbers
    if len(inp.numbers) == 2:
        first, second = inp.numbers
        upper = _mod8(first)
        lower = _mod8(second)
        moving = _mod6(first + second)
        detail = {"numbers": list(inp.numbers), "sum": first + second}
    else:
        first, second, third = inp.numbers
        upper = _mod8(first)
        lower = _mod8(second)
        moving = _mod6(third)
        detail = {"numbers": list(inp.numbers), "moving_source": "third"}
    return upper, lower, moving, detail


def _from_text(inp: MeihuaInput) -> tuple[int, int, int, dict[str, Any]]:
    assert inp.text
    length = len(inp.text)
    half = (length + 1) // 2
    upper_count = _stroke_count(inp.text[:half])
    lower_count = _stroke_count(inp.text[half:])
    upper = _mod8(upper_count)
    lower = _mod8(lower_count)
    moving = _mod6(_stroke_count(inp.text))
    detail = {
        "text": inp.text,
        "char_count": length,
        "upper_chars": half,
        "lower_chars": length - half,
        "stroke_basis": "字数 × 10（近似，不查笔画表）",
    }
    return upper, lower, moving, detail


def _from_measure(inp: MeihuaInput) -> tuple[int, int, int, dict[str, Any]]:
    assert inp.length_value is not None
    length = inp.length_value
    width = inp.width_value or length
    upper = _mod8(length)
    lower = _mod8(width)
    moving = _mod6(length + width)
    detail = {"length": length, "width": width, "sum": length + width}
    return upper, lower, moving, detail


def _from_direction(inp: MeihuaInput) -> tuple[int, int, int, dict[str, Any]]:
    assert inp.direction
    trigram = DIRECTION_TO_TRIGRAM.get(inp.direction.strip())
    if trigram is None:
        available = "、".join(sorted(DIRECTION_TO_TRIGRAM))
        raise ValueError(f"未知方位「{inp.direction}」；可用：{available}")
    number = next(key for key, value in NUMBER_TO_TRIGRAM.items() if value == trigram)
    upper = number
    lower = number
    moving = _mod6(number * 2)
    detail = {"direction": inp.direction.strip(), "trigram": trigram, "number": number}
    return upper, lower, moving, detail


def _from_hexagram(inp: MeihuaInput) -> tuple[int, int, int, dict[str, Any]]:
    assert inp.upper and inp.lower and inp.moving_line
    upper = next(key for key, value in NUMBER_TO_TRIGRAM.items() if value == inp.upper)
    lower = next(key for key, value in NUMBER_TO_TRIGRAM.items() if value == inp.lower)
    detail = {"upper": inp.upper, "lower": inp.lower, "moving_line": inp.moving_line}
    return upper, lower, inp.moving_line, detail


_DISPATCH = {
    "time": _from_time,
    "numbers": _from_numbers,
    "text": _from_text,
    "measure": _from_measure,
    "direction": _from_direction,
    "hexagram": _from_hexagram,
}


def _hexagram_block(info: Any, *, moving_line: int | None = None) -> dict[str, Any]:
    return {
        "name": info.name,
        "upper": info.upper,
        "lower": info.lower,
        "bits": info.bits,
        "palace": info.palace,
        "palace_element": info.palace_element,
        "phase": info.phase,
        "moving_line": moving_line,
    }


def _relation(me: str, other: str) -> str:
    """体用五行关系：同我 / 生我 / 我生 / 克我 / 我克。"""
    if me == other:
        return "同我"
    me_index = ELEMENTS.index(me)
    other_index = ELEMENTS.index(other)
    if (other_index + 1) % 5 == me_index:
        return "生我"
    if (me_index + 1) % 5 == other_index:
        return "我生"
    if (other_index + 2) % 5 == me_index:
        return "克我"
    return "我克"


def calculate(inp: MeihuaInput, conv: MeihuaConvention | None = None) -> ChartResult:
    convention = conv or MeihuaConvention()
    warnings: list[str] = [SCHOOL_NOTE]

    upper_number, lower_number, moving, detail = _DISPATCH[inp.method](inp)
    upper_name = NUMBER_TO_TRIGRAM[upper_number]
    lower_name = NUMBER_TO_TRIGRAM[lower_number]

    bits = LC.TRIGRAM_BITS[lower_name] + LC.TRIGRAM_BITS[upper_name]
    original = hexagram_from_bits(bits)

    # 动爻自下而上：1 = 初爻
    flipped = list(bits)
    flipped[moving - 1] = "0" if flipped[moving - 1] == "1" else "1"
    changed_bits = "".join(flipped)
    changed = hexagram_from_bits(changed_bits)

    # 互卦：二三四爻为下卦、三四五爻为上卦
    mutual = hexagram_from_bits(bits[1:4] + bits[2:5])

    # 错卦：六爻全变；综卦：六爻上下颠倒
    opposite = hexagram_from_bits("".join("0" if bit == "1" else "1" for bit in bits))
    reversed_hex = hexagram_from_bits("".join(reversed(bits)))

    # 体用：动爻在下卦（1–3）则下卦为用、上卦为体；反之亦然
    moving_in_lower = moving <= 3
    use_trigram = lower_name if moving_in_lower else upper_name
    body_trigram = upper_name if moving_in_lower else lower_name
    body_element = LC.TRIGRAM_ELEMENT[body_trigram]
    use_element = LC.TRIGRAM_ELEMENT[use_trigram]

    changed_lower = next(
        name for name, value in LC.TRIGRAM_BITS.items() if value == changed_bits[:3]
    )
    changed_upper = next(
        name for name, value in LC.TRIGRAM_BITS.items() if value == changed_bits[3:]
    )
    changed_use_trigram = changed_lower if moving_in_lower else changed_upper
    changed_use_element = LC.TRIGRAM_ELEMENT[changed_use_trigram]

    chart_facts: dict[str, Any] = {
        "method": inp.method,
        "casting": {
            "upper_number": upper_number,
            "lower_number": lower_number,
            "moving_line": moving,
            "detail": detail,
        },
        "original": _hexagram_block(original, moving_line=moving),
        "mutual": _hexagram_block(mutual),
        "changed": _hexagram_block(changed, moving_line=moving),
        "opposite": _hexagram_block(opposite),
        "reversed": _hexagram_block(reversed_hex),
        "body_use": {
            "body": {"trigram": body_trigram, "element": body_element},
            "use": {"trigram": use_trigram, "element": use_element},
            "relation": _relation(body_element, use_element),
            "changed_use": {"trigram": changed_use_trigram, "element": changed_use_element},
            "changed_relation": _relation(body_element, changed_use_element),
        },
    }

    if inp.method == "text":
        warnings.append(
            "字占的笔画数按「字数 × 10」近似，未查笔画表；如需精确笔画请改用报数起卦。"
        )
    if inp.method == "direction":
        warnings.append("方位起卦上下卦同取该方位之卦，动爻由两倍卦数取余决定。")

    input_summary = {
        "method": inp.method,
        "cast_at": inp.cast_datetime.isoformat(timespec="minutes") if inp.cast_datetime else None,
        "timezone": inp.timezone,
        "question": inp.question if inp.store_question else None,
    }

    convention_dump = convention.model_dump()
    convention_dump["school_note"] = SCHOOL_NOTE
    if inp.question and not inp.store_question:
        warnings.append("已按你的选择丢弃占问原文，命盘只保存起卦方式与卦象。")

    source_refs = [
        {"type": "rule", "id": "meihua.number.xiantian", "note": "先天八卦数：乾一兑二离三震四巽五坎六艮七坤八"},
        {"type": "rule", "id": "meihua.cast.mod8", "note": "上下卦数除 8 取余，余 0 作 8"},
        {"type": "rule", "id": "meihua.cast.mod6", "note": "动爻数除 6 取余，余 0 作上爻"},
        {"type": "rule", "id": "meihua.mutual.palace", "note": "互卦取本卦二三四爻为下卦、三四五爻为上卦"},
        {"type": "rule", "id": "meihua.body_use.moving", "note": "动爻所在卦为用，另一卦为体"},
        {"type": "book", "id": "meihua.meihuashu", "note": "邵雍《梅花易数》通行法，本仓库只取结构与事实，不取断语"},
    ]

    return ChartResult(
        domain="meihua",
        algorithm_version=settings.meihua_algorithm_version,
        input_summary=input_summary,
        convention=convention_dump,
        chart_facts=chart_facts,
        triggered_rules=[],
        warnings=warnings,
        source_refs=source_refs,
    )
