"""题库用的「预计算盘面」：把引擎事实压成一段可直接放进 prompt 的文本。

为什么必须做这一步：
MingLi-Bench 这类题目问的是「此命 1996 年发生何事」，模型如果只拿到出生时间，
只能自己排盘——排错一步整题就废，测出来的是「会不会算」而不是「会不会推」。
评测时把盘面先算好交过去，考的才是推理；同时我们记录 `chart_error`，
排盘失败会被单独计数，不会混进「答错」。
"""

from __future__ import annotations

from typing import Any

from app.domains.registry import get_engine


def compute(domain: str, payload: dict[str, Any]) -> tuple[Any | None, str]:
    """按 domain 调引擎；返回 (ChartResult, 错误类型)。错误不抛给上层。"""
    try:
        spec = get_engine(domain)
        model = spec.input_model.model_validate(payload)
        return spec.calculate(model), ""
    except Exception as exc:
        return None, f"{exc.__class__.__name__}: {str(exc)[:160]}"


def _bazi_summary(facts: dict[str, Any]) -> list[str]:
    pillars = facts.get("pillars") or {}
    order = ("year", "month", "day", "hour")
    text = " ".join(pillars[key]["text"] for key in order if key in pillars)
    lines = [f"四柱：{text}"]

    master = facts.get("day_master") or {}
    lines.append(
        f"日主：{master.get('stem', '')}（{master.get('polarity', '')}{master.get('element', '')}）"
    )
    ten_gods = facts.get("ten_gods") or {}
    if ten_gods:
        labels = {"year": "年", "month": "月", "day": "日", "hour": "时"}
        lines.append(
            "十神："
            + "、".join(
                f"{labels.get(key, key)}柱{value}" for key, value in ten_gods.items()
            )
        )

    counts = facts.get("five_elements_count") or {}
    weighted = counts.get("weighted") or {}
    if weighted:
        lines.append("五行加权：" + "、".join(f"{k}{v:g}" for k, v in weighted.items()))
        missing = counts.get("missing") or []
        if missing:
            lines.append("原值缺失：" + "、".join(missing))

    rules = facts.get("relations", {}).get("rules") if isinstance(facts.get("relations"), dict) else None
    if rules:
        lines.append(
            "关系：" + "；".join(item.get("label", "") for item in rules[:12])
        )

    dayun = facts.get("dayun") or {}
    if dayun.get("computed"):
        lines.append(f"大运{'顺' if dayun.get('forward') else '逆'}排，起运 {dayun.get('start_age', {}).get('text', '')}")
        rows = dayun.get("list") or []
        lines.append(
            "大运序列："
            + "、".join(f"{item['pillar']}({item['start_age_years']}-{item['end_age_years']}岁)" for item in rows[:8])
        )

    liunian = facts.get("liunian") or {}
    if liunian.get("list"):
        lines.append(
            "流年："
            + "、".join(
                f"{row['year']}{row['pillar']}({row['ten_god']})" for row in liunian["list"][:12]
            )
        )
    return lines


def _ziwei_summary(facts: dict[str, Any]) -> list[str]:
    bureau = facts.get("five_element_bureau") or {}
    life = facts.get("life_palace") or {}
    body = facts.get("body_palace") or {}
    lines = [
        f"农历：{(facts.get('lunar_date') or {}).get('text', '')}",
        f"命宫：{life.get('text', '')}（{life.get('branch', '')}宫），五行局{bureau.get('name', '')}",
        f"身宫：{body.get('palace', '')}",
        f"紫微星：{(facts.get('ziwei_star') or {}).get('palace', '')}",
    ]
    for palace in facts.get("palaces") or []:
        stars = "、".join(palace.get("main_stars") or []) or "无主星"
        aux = "、".join(palace.get("aux_stars") or [])
        extra = f"｜辅星 {aux}" if aux else ""
        lines.append(f"{palace['name']}（{palace['branch']}）：{stars}{extra}")
    transformations = facts.get("transformations") or []
    if transformations:
        lines.append(
            "生年四化：" + "、".join(f"{item['star']}化{item['type']}入{item['palace']}" for item in transformations)
        )
    return lines


def _liuyao_summary(facts: dict[str, Any]) -> list[str]:
    original = facts.get("original") or {}
    changed = facts.get("changed") or {}
    lines = [
        f"本卦：{original.get('name', '')}（{original.get('palace', '')}宫，世{original.get('shi')}应{original.get('ying')}）",
        f"动爻：{'、'.join(str(item) for item in facts.get('moving_lines') or []) or '无'}",
    ]
    if changed:
        lines.append(f"变卦：{changed.get('name', '')}（{changed.get('palace', '')}宫）")
    lines.append(f"日辰：{(facts.get('day_pillar') or {}).get('text', '')}")
    lines.append(f"旬空：{'、'.join(facts.get('xun_kong') or [])}")
    return lines


def _qimen_summary(facts: dict[str, Any]) -> list[str]:
    dun = facts.get("dun") or {}
    zhifu = facts.get("zhifu") or {}
    zhishi = facts.get("zhishi") or {}
    lines = [
        f"起局：{facts.get('cast_at', '')}，节气{(facts.get('term') or {}).get('name', '')}",
        f"局：{dun.get('text', '')}（{dun.get('yuan', '')}），符头{(facts.get('fu_tou') or {}).get('pillar', '')}",
        f"值符：{zhifu.get('star', '')} 落{zhifu.get('landing_name', '')}；值使：{zhishi.get('door', '')} 落{zhishi.get('palace_name', '')}",
    ]
    for palace in facts.get("palaces") or []:
        if palace.get("is_center"):
            continue
        lines.append(
            f"{palace['name']}：{palace.get('star') or ''}{('/' + palace['extra_star']) if palace.get('extra_star') else ''}"
            f" {palace.get('door') or ''} {palace.get('deity') or ''} 干{palace.get('earth_stem')}/{palace.get('sky_stem') or ''}"
        )
    return lines


_SUMMARIZERS = {
    "bazi": _bazi_summary,
    "ziwei": _ziwei_summary,
    "liuyao": _liuyao_summary,
    "qimen": _qimen_summary,
}


def summarize(domain: str, result: Any) -> str:
    facts = result.chart_facts or {}
    lines = _SUMMARIZERS.get(domain, lambda _: [])(facts)
    text = "\n".join(line for line in lines if line)
    return text[:4000]
