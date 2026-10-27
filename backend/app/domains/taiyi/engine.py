"""太乙九星引擎：年/月/日/时四层九星观测。

本模块只做「九星在哪、属什么」，不做太乙神数的七十二局推演。

为什么这样划边界：
- 七十二局需要《太乙金鏡式經》的阴阳七十二局表、主客算、大小将、十六神，
  工作量与风险都远超九星观测，且各版本表项不一致（taibu 的 ALGORITHM_RULES.md
  也明确写了「不能用某一个程序作唯一真值」）；
- 九星观测的输入输出是确定且可核验的：同一日期同一层，九星固定；
- 把两者混在一个域里，用户会以为拿到的是完整太乙盘。

九星数据来自 `lunar-python`（MIT，6tail）的九星表，本模块只做组织与校验。

红线：只列九星编号、太乙名、五行、方位、传统吉凶分类，不给事件判断。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings
from app.domains.bazi.schemas import ChartResult
from app.domains.calendar_core.jiazi import BRANCHES, hour_branch
from app.domains.calendar_core.lunar import solar_to_lunar
from app.domains.taiyi.schemas import TaiyiConvention, TaiyiInput

#: 九星在太乙体系里的名称，按索引 0–8（与 lunar-python 的 fromIndex 一致）
TAIYI_STAR_NAMES: tuple[str, ...] = (
    "太乙", "摄提", "轩辕", "招摇", "天符", "青龙", "咸池", "太阴", "天乙",
)

MODE_LABELS: dict[str, str] = {
    "year": "年盘",
    "month": "月盘",
    "day": "日盘",
    "hour": "时盘",
}

SCHOOL_NOTE = (
    "本版本只实现太乙九星观测（年/月/日/时四层九星的位置与属性），"
    "不实现七十二局、主客算、大小将与十六神推演。"
    "九星的传统吉凶分类照原样列出，不据此判断事件。"
)


def _resolve_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"未知时区: {name}（需要安装 tzdata）") from exc


def _lunar_object(day: Any):
    from lunar_python import Solar

    return Solar.fromYmd(day.year, day.month, day.day).getLunar()


def _hour_star_index(*, solar_ymd: str, winter_solstice: str, summer_solstice: str, day_branch: str, hour_index: int) -> int:
    """时层九星索引（0–8）。按九星入中宫顺逆推法独立实现。

    为什么不直接用 `LunarTime.getNineStar()`：lunar-python 1.4.8 的该方法把
    `Solar` 对象与字符串直接比较，运行期抛 TypeError。这里按**同一套规则**
    自行实现并单测锁定，而不是绕过这一步给个空值。

    规则（《太乙金鏡式經》九星入中宫法）：
    - 冬至到夏至前为阳（asc=True），起数 7；夏至到冬至前为阴，起数 3；
    - 日支属子午卯酉者，阳起 1、阴起 9；
    - 日支属辰戌丑未者，阳起 4、阴起 6；
    - 阳：index = 起数 + 时支序 − 1；阴：index = 起数 − 时支序 − 1；
    - 结果归一到 0–8。
    """
    asc = winter_solstice <= solar_ymd < summer_solstice
    start = 7 if asc else 3
    if day_branch in "子午卯酉":
        start = 1 if asc else 9
    elif day_branch in "辰戌丑未":
        start = 4 if asc else 6
    index = start + hour_index - 1 if asc else start - hour_index - 1
    return index % 9


def _star_block(star: Any, scale: str) -> dict[str, Any]:
    return {
        "scale": scale,
        "scale_label": MODE_LABELS.get(scale, scale),
        "index": star.getIndex() + 1,
        "number": star.getNumber(),
        "color": star.getColor(),
        "element": star.getWuXing(),
        "position": star.getPosition(),
        "position_desc": star.getPositionDesc(),
        "taiyi_name": star.getNameInTaiYi(),
        "taiyi_type": star.getTypeInTaiYi(),
        "bei_dou_name": star.getNameInBeiDou(),
        "xuan_kong_name": star.getNameInXuanKong(),
        "qi_men_name": star.getNameInQiMen(),
        "qi_men_luck": star.getLuckInQiMen(),
        "qi_men_yin_yang": star.getYinYangInQiMen(),
        "qi_men_gate": star.getBaMenInQiMen() or None,
        "taiyi_song": star.getSongInTaiYi(),
    }


def calculate(inp: TaiyiInput, conv: TaiyiConvention | None = None) -> ChartResult:
    convention = conv or TaiyiConvention()
    warnings: list[str] = [SCHOOL_NOTE]

    # 只为校验时区是否合法：非法时区在这里就抛错，不要留到后面才炸
    _resolve_zone(inp.timezone)
    lunar = _lunar_object(inp.date)
    lunar_date = solar_to_lunar(inp.date)

    # 四层九星：年、月、日三层由日期决定；时层由 hour 决定
    layers: dict[str, Any] = {
        "year": _star_block(lunar.getYearNineStar(), "year"),
        "month": _star_block(lunar.getMonthNineStar(), "month"),
        "day": _star_block(lunar.getDayNineStar(), "day"),
    }
    hour_index = None
    hour_name = None
    if inp.hour is not None:
        from lunar_python import NineStar

        hour_name = hour_branch(inp.hour)
        hour_index = BRANCHES.index(hour_name)
        jie_qi = lunar.getJieQiTable()
        index = _hour_star_index(
            solar_ymd=lunar.getSolar().toYmd(),
            winter_solstice=jie_qi["冬至"].toYmd(),
            summer_solstice=jie_qi["夏至"].toYmd(),
            day_branch=lunar.getDayZhi(),
            hour_index=hour_index,
        )
        layers["hour"] = _star_block(NineStar.fromIndex(index), "hour")

    if inp.mode == "hour" and "hour" not in layers:
        raise ValueError("mode=hour 时未能取到时层九星")

    primary = layers[inp.mode]

    chart_facts: dict[str, Any] = {
        "mode": inp.mode,
        "mode_label": MODE_LABELS[inp.mode],
        "date": {
            "solar": inp.date.isoformat(),
            "timezone": inp.timezone,
            "hour": inp.hour,
            "shichen": f"{hour_name}时" if hour_name else None,
        },
        "lunar_date": {
            "text": lunar_date.text,
            "year_ganzhi": lunar_date.year_ganzhi,
            "month_ganzhi": lunar_date.month_ganzhi,
            "day_ganzhi": lunar_date.day_ganzhi,
            "year_zodiac": lunar_date.year_zodiac,
        },
        "jie_qi": lunar.getJieQi() or None,
        "day_officer": lunar.getZhiXing(),
        "tian_shen": {
            "name": lunar.getDayTianShen(),
            "luck": lunar.getDayTianShenLuck(),
        },
        "xiu": {"name": lunar.getXiu(), "luck": lunar.getXiuLuck()},
        "primary": primary,
        "layers": layers,
    }

    input_summary = {
        "date": inp.date.isoformat(),
        "timezone": inp.timezone,
        "mode": inp.mode,
        "hour": inp.hour,
        "question": inp.question if inp.store_question else None,
    }

    convention_dump = convention.model_dump()
    convention_dump["school_note"] = SCHOOL_NOTE
    if inp.question and not inp.store_question:
        warnings.append("已按你的选择丢弃占问原文，命盘只保存日期与九星。")
    if inp.mode != "hour" and inp.hour is None:
        warnings.append("未提供 hour：只出年/月/日三层九星，时层留空。")

    source_refs = [
        {"type": "library", "id": "lunar-python", "note": "MIT License, 6tail；提供年月日时四层九星表"},
        {"type": "rule", "id": "taiyi.jiuxing.index", "note": "九星索引 0–8 对应太乙、摄提、轩辕、招摇、天符、青龙、咸池、太阴、天乙"},
        {"type": "rule", "id": "taiyi.layer.four", "note": "年/月/日三层由日期决定，时层由时辰决定"},
        {"type": "book", "id": "taiyi.jinjing", "note": "九星体系参考《太乙金鏡式經》；本仓库只取星位与属性，不取七十二局与断法"},
    ]

    return ChartResult(
        domain="taiyi",
        algorithm_version=settings.taiyi_algorithm_version,
        input_summary=input_summary,
        convention=convention_dump,
        chart_facts=chart_facts,
        triggered_rules=[],
        warnings=warnings,
        source_refs=source_refs,
    )
