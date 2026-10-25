"""奇门遁甲引擎（时家转盘拆补法，单一口径）。

对外唯一入口 `calculate(inp, conv, service)`，返回与四柱同构的 `ChartResult`。
只输出盘面事实（局数、九宫、星门神、旬空、马星）与结构性标记，不做吉凶判断。

固定顺序，任何一步都不能交换——后面的步骤全部依赖前面的结果：

1. 四柱：年柱以立春为界、月柱以「节」为界、日柱受换日口径影响、时柱五鼠遁
2. 节气（含中气）定阴阳遁：冬至→芒种为阳遁，夏至→大雪为阴遁
3. 符头（甲日、己日）地支定上中下元 → 节气三元局数表得局数
4. 地盘三奇六仪：自局数宫起，阳遁按宫数顺布、阴遁按宫数逆布「戊己庚辛壬癸丁丙乙」
5. 旬首 → 所遁之仪 → 旬首宫：该宫本星为值符、本门为值使
6. 时干落宫（甲则取旬首宫）→ 天盘九星在八宫环上刚性旋转（天禽随天芮）
7. 值使门按「旬内步数」在八宫环上顺/逆行 → 八门整体同步旋转
8. 八神自值符星所在宫起，阳遁顺布、阴遁逆布
9. 时柱旬空、时支马星

红线：不取用神、不判旺衰、不择日、不给应期与吉凶断语。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings
from app.domains.bazi.engine import lichun_of_year
from app.domains.bazi.schemas import ChartResult
from app.domains.calendar_core.jiazi import (
    JIE_TO_MONTH_BRANCH,
    day_pillar_index,
    hour_branch,
    hour_stem,
    jiazi_index,
    month_stem,
    pillar_of_index,
    pillar_text,
    year_pillar_index,
)
from app.domains.calendar_core.julian import gregorian_to_jdn
from app.domains.calendar_core.solar_terms import SolarTermService, TermMoment, get_term_service
from app.domains.qimen import constants as C
from app.domains.qimen.schemas import QimenConvention, QimenInput

#: 距节气两小时内提示：阴阳遁与局数对交节时刻精度敏感
TERM_BOUNDARY_MINUTES = 120


def _resolve_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"未知时区: {name}（需要安装 tzdata）") from exc


def _pillars(
    local_dt: datetime,
    instant: datetime,
    tz: ZoneInfo,
    conv: QimenConvention,
    service: SolarTermService,
    warnings: list[str],
) -> tuple[tuple[str, str], tuple[str, str], tuple[str, str], tuple[str, str], TermMoment, date]:
    """四柱 + 定月之节 + 生效日（口径与四柱引擎一致，避免同一时刻两套干支）。"""
    # 年柱：立春为界
    lichun = lichun_of_year(service, local_dt.year, tz)
    ganzhi_year = local_dt.year if instant >= lichun.instant else local_dt.year - 1
    year_pillar = pillar_of_index(year_pillar_index(ganzhi_year))

    # 月柱：以「节」为界
    prev_jie = service.prev_jie(instant)
    month_branch = JIE_TO_MONTH_BRANCH.get(prev_jie.name)
    if month_branch is None:  # pragma: no cover - 数据异常
        raise RuntimeError(f"节气 {prev_jie.name} 不是定月之节")
    month_pillar = (month_stem(year_pillar[0], month_branch), month_branch)

    # 日柱：受换日口径影响
    day_date = local_dt.date()
    if conv.day_boundary == "zi_hour_policy_a" and local_dt.hour >= 23:
        day_date = day_date + timedelta(days=1)
        warnings.append("起局时刻在 23:00 之后：日柱按「23:00 换日」口径归入次日，符头与旬空随之变化。")
    day_pillar = pillar_of_index(
        day_pillar_index(gregorian_to_jdn(day_date.year, day_date.month, day_date.day))
    )

    # 时柱：五鼠遁；夜子时取次日子干
    branch = hour_branch(local_dt.hour, local_dt.minute)
    if conv.day_boundary == "zi_hour_policy_b" and local_dt.hour >= 23:
        next_day = local_dt.date() + timedelta(days=1)
        day_stem_for_hour = pillar_of_index(
            day_pillar_index(gregorian_to_jdn(next_day.year, next_day.month, next_day.day))
        )[0]
    else:
        day_stem_for_hour = day_pillar[0]
    hour_pillar = (hour_stem(day_stem_for_hour, branch), branch)

    return year_pillar, month_pillar, day_pillar, hour_pillar, prev_jie, day_date


def _earth_plate(ju: int, yang: bool) -> dict[int, str]:
    """地盘三奇六仪：自局数宫起，阳遁按宫数顺布、阴遁按宫数逆布。"""
    plate: dict[int, str] = {}
    for offset, stem in enumerate(C.INSTRUMENTS):
        step = offset if yang else -offset
        palace = ((ju - 1 + step) % 9) + 1
        plate[palace] = stem
    return plate


def _markers(
    *,
    term: TermMoment,
    yang: bool,
    ju: int,
    yuan_name: str,
    fu_tou_text: str,
    fu_tou_branch: str,
    xun_head: str,
    xun_instrument: str,
    xun_palace: int,
    zhifu_star: str,
    zhishi_door: str,
    zhishi_palace: int,
    hour_stem_text: str,
    hour_stem_palace: int,
    step: int,
    kong: tuple[str, str],
    ma_branch: str,
    ma_palace: int,
    star_fuyin: bool,
    door_fuyin: bool,
) -> list[dict[str, Any]]:
    """结构性标记：只陈述「哪个盘层落在哪一宫」，不作吉凶判断。"""
    markers: list[dict[str, Any]] = []

    def emit(
        rule_id: str,
        relation: str,
        label: str,
        members: list[str],
        note: str,
        priority: int,
    ) -> None:
        markers.append(
            {
                "rule_id": rule_id,
                "system": "qimen",
                "kind": "structure",
                "relation": relation,
                "members": members,
                "topic": "structure",
                "priority": priority,
                "note": note,
                "source_ref": "qimen.tongzong",
                "version": settings.qimen_algorithm_version,
                "scope": "palace",
                "positions": [label],
                "label": label,
            }
        )

    dun_text = f"{'阳' if yang else '阴'}遁{_numeral(ju)}局"
    emit(
        "qimen.ju.dun",
        dun_text,
        "定局",
        [dun_text],
        f"起局时刻在{term.name}之后，属{'阳' if yang else '阴'}遁；"
        f"符头为{fu_tou_text}（地支{fu_tou_branch}）定{yuan_name}，故排{dun_text}。",
        60,
    )
    emit(
        "qimen.zhifu.star",
        "值符",
        C.palace_name(C.center_redirect(hour_stem_palace)),
        [zhifu_star],
        f"旬首{xun_head}遁于{xun_instrument}，落{C.palace_name(xun_palace)}，该宫本星为值符{zhifu_star}；"
        f"时干{hour_stem_text}落宫为{C.palace_name(hour_stem_palace)}，天盘{zhifu_star}随之转至该宫。",
        58,
    )
    emit(
        "qimen.zhishi.door",
        "值使",
        C.palace_name(zhishi_palace),
        [zhishi_door],
        f"值使为{zhishi_door}，自{C.palace_name(xun_palace)}起按旬内第 {step} 步"
        f"在八宫环上{'顺' if yang else '逆'}行，落{C.palace_name(zhishi_palace)}。",
        56,
    )
    if star_fuyin:
        emit(
            "qimen.fuyin.star",
            "星伏吟",
            "天盘",
            [zhifu_star],
            "天盘九星回到本地盘位置（值符星未离旬首宫），属星伏吟结构。",
            50,
        )
    if door_fuyin:
        emit(
            "qimen.fuyin.door",
            "门伏吟",
            "八门",
            [zhishi_door],
            "八门未发生位移（值使门仍在旬首宫），属门伏吟结构。",
            49,
        )
    emit(
        "qimen.xun_kong",
        "旬空",
        "旬空",
        [f"{xun_head}旬"],
        f"时柱属{xun_head}旬，本旬空亡为{'、'.join(kong)}。",
        46,
    )
    emit(
        "qimen.ma_star",
        "马星",
        C.palace_name(ma_palace),
        [ma_branch],
        f"时支三合推马星在{ma_branch}，对应{C.palace_name(ma_palace)}。",
        44,
    )
    return markers


_NUMERALS = ("", "一", "二", "三", "四", "五", "六", "七", "八", "九")


def _numeral(number: int) -> str:
    return _NUMERALS[number]


def calculate(
    inp: QimenInput,
    conv: QimenConvention | None = None,
    service: SolarTermService | None = None,
) -> ChartResult:
    conv = conv or QimenConvention()
    service = service or get_term_service()
    tz = _resolve_zone(inp.timezone)
    warnings: list[str] = []

    local_dt = inp.cast_datetime
    instant = local_dt.replace(tzinfo=tz).astimezone(timezone.utc)

    # ---- 1. 四柱 ----
    year_pillar, month_pillar, day_pillar, hour_pillar, prev_jie, day_date = _pillars(
        local_dt, instant, tz, conv, service, warnings
    )
    day_index = jiazi_index(*day_pillar)
    hour_index = jiazi_index(*hour_pillar)
    hour_stem_text, hour_branch_text = hour_pillar

    # ---- 2. 节气与阴阳遁 ----
    term = service.prev_term(instant)
    yang = C.is_yang_dun(term.name)
    minutes_to_term = (instant - term.instant).total_seconds() / 60

    # ---- 3. 符头定元与局数 ----
    fu_tou_text, fu_tou_branch, fu_tou_back = C.fu_tou(day_index)
    yuan_index = C.YUAN_BY_BRANCH[fu_tou_branch]
    yuan_name = C.YUAN_NAMES[yuan_index]
    ju = C.ju_number(term.name, yuan_index)
    dun_text = f"{'阳' if yang else '阴'}遁{_numeral(ju)}局"

    # ---- 4. 地盘三奇六仪 ----
    earth = _earth_plate(ju, yang)
    stem_palace = {stem: palace for palace, stem in earth.items()}

    # ---- 5. 旬首 / 值符 / 值使 ----
    xun_head = C.xun_head_of(hour_index)
    xun_instrument = C.XUN_INSTRUMENT[xun_head]
    xun_palace = stem_palace[xun_instrument]
    ring_base = C.RING.index(C.center_redirect(xun_palace))
    zhifu_star = C.STARS_BY_PALACE[xun_palace]
    # 中五宫无门：旬首落中五时值使取寄宫坤二的门
    zhishi_door = C.DOORS_BY_PALACE[C.center_redirect(xun_palace)]

    # ---- 6. 时干落宫 → 天盘九星旋转 ----
    hour_stem_palace = xun_palace if hour_stem_text == "甲" else stem_palace[hour_stem_text]
    ring_target = C.RING.index(C.center_redirect(hour_stem_palace))
    star_offset = (ring_target - ring_base) % 8

    # ---- 7. 值使门按旬内步数移动 → 八门整体旋转 ----
    step = hour_index % 10
    direction = 1 if yang else -1
    door_offset = (step * direction) % 8
    zhishi_palace = C.RING[(ring_base + door_offset) % 8]

    # ---- 8. 九宫装配 ----
    star_base = {index: C.STARS_BY_PALACE[palace] for index, palace in enumerate(C.RING)}
    door_base = {index: C.DOORS_BY_PALACE[palace] for index, palace in enumerate(C.RING)}
    earth_base = {index: earth[palace] for index, palace in enumerate(C.RING)}
    center_star_ring = C.RING.index(C.CENTER_REDIRECT)  # 天芮本位（坤二）
    deities = C.DEITIES_YANG if yang else C.DEITIES_YIN

    palaces: list[dict[str, Any]] = []
    for number in C.PALACE_NUMBERS:
        if number == C.CENTER_PALACE:
            palaces.append(
                {
                    "number": number,
                    "name": C.palace_name(number),
                    "trigram": C.PALACE_TRIGRAM[number],
                    "direction": C.PALACE_DIRECTION[number],
                    "element": C.PALACE_ELEMENT[number],
                    "earth_stem": earth[number],
                    "sky_stem": None,
                    "extra_sky_stem": None,
                    "star": "天禽",
                    "extra_star": None,
                    "door": None,
                    "deity": None,
                    "is_center": True,
                    "is_zhifu": False,
                    "is_zhishi": False,
                    "note": "中五宫无门无神，天禽寄坤二宫",
                }
            )
            continue

        ring_index = C.RING.index(number)
        star_ring = (ring_index - star_offset) % 8
        door_ring = (ring_index - door_offset) % 8
        distance = (ring_index - ring_target) % 8 if yang else (ring_target - ring_index) % 8
        rides_center = star_ring == center_star_ring
        palaces.append(
            {
                "number": number,
                "name": C.palace_name(number),
                "trigram": C.PALACE_TRIGRAM[number],
                "direction": C.PALACE_DIRECTION[number],
                "element": C.PALACE_ELEMENT[number],
                "earth_stem": earth[number],
                "sky_stem": earth_base[star_ring],
                "extra_sky_stem": earth[C.CENTER_PALACE] if rides_center else None,
                "star": star_base[star_ring],
                "extra_star": "天禽" if rides_center else None,
                "door": door_base[door_ring],
                "deity": deities[distance],
                "is_center": False,
                "is_zhifu": number == C.RING[ring_target],
                "is_zhishi": number == zhishi_palace,
            }
        )

    # ---- 9. 旬空 / 马星 / 伏吟 ----
    kong = C.xun_kong(hour_index)
    ma_branch = C.MA_STAR[hour_branch_text]
    ma_palace = C.BRANCH_PALACE[ma_branch]
    star_fuyin = star_offset == 0
    door_fuyin = door_offset == 0

    markers = _markers(
        term=term,
        yang=yang,
        ju=ju,
        yuan_name=yuan_name,
        fu_tou_text=fu_tou_text,
        fu_tou_branch=fu_tou_branch,
        xun_head=xun_head,
        xun_instrument=xun_instrument,
        xun_palace=xun_palace,
        zhifu_star=zhifu_star,
        zhishi_door=zhishi_door,
        zhishi_palace=zhishi_palace,
        hour_stem_text=hour_stem_text,
        hour_stem_palace=hour_stem_palace,
        step=step,
        kong=kong,
        ma_branch=ma_branch,
        ma_palace=ma_palace,
        star_fuyin=star_fuyin,
        door_fuyin=door_fuyin,
    )

    pillar_facts = {
        "year": _pillar_fact(year_pillar),
        "month": _pillar_fact(month_pillar),
        "day": _pillar_fact(day_pillar),
        "hour": _pillar_fact(hour_pillar),
    }

    chart_facts: dict[str, Any] = {
        "cast_at": local_dt.strftime("%Y-%m-%d %H:%M"),
        "timezone": str(tz),
        "pillars": pillar_facts,
        "term": term.to_dict(tz),
        "dun": {
            "type": "阳遁" if yang else "阴遁",
            "is_yang": yang,
            "yuan": yuan_name,
            "ju": ju,
            "text": dun_text,
        },
        "fu_tou": {
            "pillar": fu_tou_text,
            "branch": fu_tou_branch,
            "yuan": yuan_name,
            "date": (day_date - timedelta(days=fu_tou_back)).isoformat(),
        },
        "xun_kong": {
            "xun_head": xun_head,
            "instrument": xun_instrument,
            "branches": list(kong),
        },
        "zhifu": {
            "star": zhifu_star,
            "instrument": xun_instrument,
            "palace": xun_palace,
            "palace_name": C.palace_name(xun_palace),
            "landing_palace": C.RING[ring_target],
            "landing_name": C.palace_name(C.RING[ring_target]),
        },
        "zhishi": {
            "door": zhishi_door,
            "palace": zhishi_palace,
            "palace_name": C.palace_name(zhishi_palace),
            "steps": step,
        },
        "hour_stem_palace": {
            "stem": hour_stem_text,
            "palace": C.RING[ring_target],
            "palace_name": C.palace_name(C.RING[ring_target]),
        },
        "ma_star": {
            "branch": ma_branch,
            "palace": ma_palace,
            "palace_name": C.palace_name(ma_palace),
        },
        "fuyin": {"star": star_fuyin, "door": door_fuyin},
        "palaces": palaces,
        "three_marvels": [
            {"stem": stem, "palace": stem_palace[stem], "palace_name": C.palace_name(stem_palace[stem])}
            for stem in C.THREE_MARVELS
        ],
    }

    input_summary = {
        "cast_datetime": local_dt.isoformat(timespec="minutes"),
        "timezone": inp.timezone,
        "day_boundary": conv.day_boundary,
        "ju": dun_text,
    }

    convention_dump = conv.model_dump()
    convention_dump["school_note"] = C.SCHOOL_NOTE

    # ---- 提示：口径、寄宫、伏吟、节气边界 ----
    warnings.append(C.SCHOOL_NOTE)
    warnings.append("中五宫寄坤二宫：天禽随天芮同宫，八门与八神不入中宫。")
    warnings.append(
        "上中下元按符头（甲日、己日）地支拆补判定，与置闰法在节气交界前后可能相差一局；"
        "本版本不提供置闰选项。"
    )
    if step == 0:
        warnings.append(
            f"时柱为旬首（{pillar_text(hour_pillar)}），天盘与地盘重合、值使门仍在旬首宫，属伏吟局。"
        )
    if 0 <= minutes_to_term < TERM_BOUNDARY_MINUTES:
        warnings.append(
            f"起局时刻距节气「{term.name}」仅 {minutes_to_term:.0f} 分钟，"
            "阴阳遁与局数对交节时刻精度敏感，请核对时间与节气来源。"
        )

    source_refs = [
        {"type": "rule", "id": "qimen.ju.yinyang", "note": "冬至→芒种为阳遁，夏至→大雪为阴遁"},
        {"type": "rule", "id": "qimen.ju.yuan", "note": "符头（甲己日）地支四仲/四生/四墓定上中下元"},
        {"type": "rule", "id": "qimen.ju.table", "note": "二十四节气三元局数表"},
        {"type": "rule", "id": "qimen.pan.dipan", "note": "地盘三奇六仪自局数宫起阳顺阴逆布九干"},
        {"type": "rule", "id": "qimen.zhifu.zhishi", "note": "旬首所遁之仪落宫定值符星与值使门"},
        {"type": "rule", "id": "qimen.pan.tianpan", "note": "值符加时干，天盘九星在八宫环上刚性旋转"},
        {"type": "rule", "id": "qimen.pan.renpan", "note": "值使门按旬内步数在八宫环上顺逆移动，八门同步旋转"},
        {"type": "rule", "id": "qimen.pan.shenpan", "note": "八神自值符宫起阳顺阴逆布，阴遁以勾陈朱雀代白虎玄武"},
        {"type": "rule", "id": "qimen.xun_kong", "note": "旬空按时柱所在旬推算"},
        {"type": "rule", "id": "qimen.ma_star", "note": "马星按时支三合局推算"},
        {"type": "book", "id": "qimen.tongzong", "note": "《奇门遁甲统宗》通行转盘法，本仓库只取盘面结构与事实，不取断语"},
    ]

    return ChartResult(
        domain="qimen",
        algorithm_version=settings.qimen_algorithm_version,
        input_summary=input_summary,
        convention=convention_dump,
        chart_facts=chart_facts,
        triggered_rules=markers,
        warnings=warnings,
        source_refs=source_refs,
    )


def _pillar_fact(pillar: tuple[str, str]) -> dict[str, str]:
    return {"stem": pillar[0], "branch": pillar[1], "text": pillar_text(pillar)}
