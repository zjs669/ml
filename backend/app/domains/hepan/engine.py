"""合盘引擎：两张四柱盘的两两干支交互。

固定顺序：
1. 解析双方盘面（chart_id → 取已存盘；birth_datetime → 调 bazi 排盘；pillars → 直接用）；
2. 按 scope 决定比较范围（全部四柱两两比较 / 只比日柱）；
3. 把双方干支拼成一个「临时盘面」交给 `relations.detect_relations` 判定；
4. 汇总触发的规则，按关系类型分组。

为什么把双方拼成一个临时盘面再交给 relations 引擎，而不是写一套「合盘专用」判定：
关系规则（三合、六冲、相刑、天干五合…）在单盘里和跨盘里是同一条规则。
另写一套等于把 66 条规则抄两遍，改一处忘一处，两边结果不一致。

拼接时用前缀区分来源：`L_year` / `R_day`，这样触发的规则能直接看出是跨盘还是盘内。

红线：只列触发的规则与结构标记，不给「合不合」「能不能成」这类结论。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.domains.bazi.engine import calculate as calculate_bazi
from app.domains.bazi.schemas import BaziInput, ChartResult, Convention
from app.domains.hepan.schemas import HepanConvention, HepanInput, HepanSide
from app.domains.relations.engine import detect_relations, load_rules

PILLAR_KEYS = ("year", "month", "day", "hour")
PILLAR_LABELS = {"year": "年柱", "month": "月柱", "day": "日柱", "hour": "时柱"}

SCHOOL_NOTE = (
    "合盘只做两张四柱盘之间的干支交互判定（复用单盘的 66 条关系规则），"
    "结果按「跨盘」「盘内」分组列出。"
    "不判断关系好坏、不预测关系走向、不给建议。"
)


def _from_chart_id(session: Session | None, chart_id: int, owner_id: int | None) -> dict[str, Any]:
    """取已保存的四柱盘面。归属校验由调用方负责（API 层已做）。"""
    if session is None:
        raise ValueError("使用 chart_id 时必须提供数据库会话")
    from app.repositories import chart_repo

    record = chart_repo.get_owned(session, chart_id=chart_id, owner_id=owner_id or 0)
    chart_json = record.chart_json or {}
    if record.domain != "bazi":
        raise ValueError(f"chart_id={chart_id} 是「{record.domain}」盘，合盘只支持四柱盘")
    pillars = chart_json.get("chart_facts", {}).get("pillars", {})
    if not pillars:
        raise ValueError(f"chart_id={chart_id} 的盘面缺少四柱数据")
    return {
        "source": "chart_id",
        "chart_id": chart_id,
        "pillars": {key: pillars[key]["text"] for key in PILLAR_KEYS},
        "algorithm_version": record.algorithm_version,
        "convention": record.convention_json,
    }


def _from_birth(side: HepanSide) -> dict[str, Any]:
    assert side.birth_datetime is not None
    result = calculate_bazi(
        BaziInput(
            birth_datetime=side.birth_datetime,
            timezone=side.timezone,
            gender=side.gender,
        ),
        Convention(),
    )
    pillars = result.chart_facts.get("pillars", {})
    return {
        "source": "birth_datetime",
        "birth_datetime": side.birth_datetime.isoformat(timespec="minutes"),
        "pillars": {key: pillars[key]["text"] for key in PILLAR_KEYS},
        "algorithm_version": result.algorithm_version,
        "convention": result.convention,
    }


def _from_pillars(side: HepanSide) -> dict[str, Any]:
    assert side.pillars is not None
    return {
        "source": "pillars",
        "pillars": dict(side.pillars),
        "algorithm_version": "external",
        "convention": {"school": "external_input"},
    }


def _resolve_side(session: Session | None, side: HepanSide, owner_id: int | None) -> dict[str, Any]:
    if side.chart_id is not None:
        block = _from_chart_id(session, side.chart_id, owner_id)
    elif side.birth_datetime is not None:
        block = _from_birth(side)
    else:
        block = _from_pillars(side)
    block["label"] = side.label
    return block


def _merge_pillars(left: dict[str, str], right: dict[str, str], scope: str) -> dict[str, dict[str, Any]]:
    """把双方四柱拼成 relations 引擎认识的盘面结构（position → {stem, branch}）。

    relations 的 `detect_relations` 按 position 名归并同柱干支，
    因此这里用 `L_year` / `R_day` 这类前缀保证两侧不互相覆盖。
    """
    keys = ("day",) if scope == "day_only" else PILLAR_KEYS
    merged: dict[str, dict[str, Any]] = {}
    for prefix, side in (("L", left), ("R", right)):
        for key in keys:
            text = side[key]
            merged[f"{prefix}_{key}"] = {"stem": text[0], "branch": text[1], "text": text}
    return merged


def _split_positions(position: str) -> tuple[str, str]:
    """`L_year` → ("L", "year")。"""
    prefix, _, key = position.partition("_")
    return prefix, key


def calculate(
    inp: HepanInput,
    conv: HepanConvention | None = None,
    *,
    session: Session | None = None,
    owner_id: int | None = None,
) -> ChartResult:
    convention = conv or HepanConvention()
    warnings: list[str] = [SCHOOL_NOTE]

    left = _resolve_side(session, inp.left, owner_id)
    right = _resolve_side(session, inp.right, owner_id)

    if left["source"] == "pillars" or right["source"] == "pillars":
        warnings.append(
            "有至少一方是直接输入的干支：未经验证，可能来自其他口径（年界、日界不同会改变干支）。"
        )

    merged = _merge_pillars(left["pillars"], right["pillars"], convention.scope)
    rule_version, rules = load_rules()
    # 传入合并后的位置名，让 relations 引擎按这 8 个位置（或 2 个）判定，
    # 而不是只认默认的 year/month/day/hour。
    detected = detect_relations(merged, positions=tuple(merged))

    # 按「跨盘 / 盘内」分组：同一前缀即盘内，不同前缀即跨盘
    cross: list[dict[str, Any]] = []
    internal: list[dict[str, Any]] = []
    for item in detected.get("rules", []):
        positions = item.get("positions", [])
        prefixes = {_split_positions(position)[0] for position in positions}
        bucket = cross if len(prefixes) > 1 else internal
        bucket.append(
            {
                **item,
                "positions_detail": [
                    {
                        "position": position,
                        "side": "left" if _split_positions(position)[0] == "L" else "right",
                        "pillar": _split_positions(position)[1],
                        "pillar_label": PILLAR_LABELS[_split_positions(position)[1]],
                    }
                    for position in positions
                ],
            }
        )

    chart_facts: dict[str, Any] = {
        "relation_type": inp.relation_type,
        "scope": convention.scope,
        "left": left,
        "right": right,
        "cross_chart_relations": cross,
        "internal_relations": internal,
        "conflicts": detected.get("conflicts", []),
        "incomplete": detected.get("incomplete", []),
        "rule_version": rule_version,
        "rule_count": len(rules),
        "summary": {
            "cross_count": len(cross),
            "internal_count": len(internal),
            "left_count": sum(1 for item in internal if all(
                _split_positions(p)[0] == "L" for p in item.get("positions", [])
            )),
            "right_count": sum(1 for item in internal if all(
                _split_positions(p)[0] == "R" for p in item.get("positions", [])
            )),
        },
    }

    input_summary = {
        "relation_type": inp.relation_type,
        "left": {"label": inp.left.label, "source": left["source"]},
        "right": {"label": inp.right.label, "source": right["source"]},
        "scope": convention.scope,
        "question": inp.question if inp.store_question else None,
    }

    convention_dump = convention.model_dump()
    convention_dump["school_note"] = SCHOOL_NOTE
    if inp.question and not inp.store_question:
        warnings.append("已按你的选择丢弃占问原文，命盘只保存双方盘面与触发的规则。")
    if not cross and not internal:
        warnings.append("双方干支之间没有触发任何关系规则。")

    source_refs = [
        {"type": "rule", "id": "hepan.cross_chart", "note": "跨盘关系：双方干支两两比较，复用 relations 的 YAML 规则"},
        {"type": "rule", "id": "hepan.internal", "note": "盘内关系：各盘自身四柱之间的关系，同盘独立判定"},
        {"type": "rule", "id": "hepan.scope", "note": "scope=all 比较全部四柱，scope=day_only 只比日柱"},
        {"type": "book", "id": "bazi.relations", "note": "关系规则与单盘同源，不另立一套合盘专用规则"},
    ]

    return ChartResult(
        domain="hepan",
        algorithm_version=settings.hepan_algorithm_version,
        input_summary=input_summary,
        convention=convention_dump,
        chart_facts=chart_facts,
        triggered_rules=cross + internal,
        warnings=warnings,
        source_refs=source_refs,
    )
