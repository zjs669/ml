"""紫微飞星查询引擎：定向回答「哪一宫的哪个化落到哪一宫」。

为什么要独立成一个域，而不是扩 `ziwei` 的 `flying_depth`：
`ziwei` 的 `flying` 是「命宫起两跳的串联概览」，回答的是「大致怎么连」；
飞星查询回答的是具体问题：「夫妻宫的忌飞去哪」「哪些宫飞入官禄」。
两者的输入形态不同（一个是深度参数，一个是起点/终点），塞在一起会让
`ziwei` 的入参变成万能参数袋，也让结果无法被稳定校验。

实现上完全复用本命盘的 `palace_transformations`（十二宫 × 四化 = 48 条），
不重推四化表 —— 四化规则只允许在本仓库有一份实现。

红线：只输出链路，不解读吉凶，不把「忌入某宫」读成事件。
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.domains.bazi.schemas import ChartResult
from app.domains.ziwei import constants as ZC
from app.domains.ziwei.engine import calculate as calculate_ziwei
from app.domains.ziwei.schemas import ZiweiConvention, ZiweiInput
from app.domains.ziwei_flying.schemas import FlyingConvention, FlyingInput

MUTAGENS = ("禄", "权", "科", "忌")


def calculate(inp: FlyingInput, conv: FlyingConvention | None = None) -> ChartResult:
    convention = conv or FlyingConvention()
    warnings: list[str] = []

    natal = calculate_ziwei(
        ZiweiInput(
            calendar=inp.calendar,
            birth_datetime=inp.birth_datetime,
            is_leap_month=inp.is_leap_month,
            timezone=inp.timezone,
            gender=inp.gender,
            time_known=inp.time_known,
        ),
        ZiweiConvention(),
    )
    natal_facts = natal.chart_facts
    warnings.extend(f"本命盘：{item}" for item in natal.warnings)

    rows: list[dict[str, Any]] = list(natal_facts.get("palace_transformations") or [])
    if not rows:
        raise ValueError("本命盘未产出宫干四化表，无法进行飞星查询")

    requested = inp.mutagens or (list(MUTAGENS) if convention.empty_means_all else [])
    if requested:
        rows = [row for row in rows if row["type"] in requested]

    # 十二宫宫干索引：用于回显起点宫的干支
    stem_by_palace = {p["name"]: p["heavenly_stem"] for p in natal_facts["palaces"]}
    branch_by_palace = {p["name"]: p["branch"] for p in natal_facts["palaces"]}

    if inp.query_type == "flies_from":
        selected = [row for row in rows if row["from_palace"] == inp.from_palace]
        answer = {
            "query_type": inp.query_type,
            "from_palace": inp.from_palace,
            "from_stem": stem_by_palace.get(inp.from_palace or ""),
            "from_branch": branch_by_palace.get(inp.from_palace or ""),
            "flights": [
                {"type": row["type"], "star": row["star"], "to_palace": row["to_palace"], "to_branch": row["to_branch"]}
                for row in selected
            ],
        }
    elif inp.query_type == "flies_into":
        selected = [row for row in rows if row["to_palace"] == inp.to_palace]
        answer = {
            "query_type": inp.query_type,
            "to_palace": inp.to_palace,
            "to_branch": branch_by_palace.get(inp.to_palace or ""),
            "sources": [
                {
                    "from_palace": row["from_palace"],
                    "from_stem": row["stem"],
                    "type": row["type"],
                    "star": row["star"],
                }
                for row in selected
            ],
        }
    else:  # flies_to
        selected = [
            row
            for row in rows
            if row["from_palace"] == inp.from_palace and row["to_palace"] == inp.to_palace
        ]
        answer = {
            "query_type": inp.query_type,
            "from_palace": inp.from_palace,
            "from_stem": stem_by_palace.get(inp.from_palace or ""),
            "to_palace": inp.to_palace,
            "to_branch": branch_by_palace.get(inp.to_palace or ""),
            "matches": [
                {"type": row["type"], "star": row["star"]} for row in selected
            ],
            "connected": bool(selected),
        }

    # 全表随结果一起给，方便前端在同一屏内切换查询而不必重新排盘
    full_table = [
        {
            "from_palace": row["from_palace"],
            "stem": row["stem"],
            "type": row["type"],
            "star": row["star"],
            "to_palace": row["to_palace"],
            "to_branch": row["to_branch"],
        }
        for row in (natal_facts.get("palace_transformations") or [])
    ]

    chart_facts: dict[str, Any] = {
        "natal": {
            "life_palace": natal_facts["life_palace"],
            "body_palace": natal_facts["body_palace"],
            "year_ganzhi": natal_facts["year_ganzhi"],
            "si_hua": natal_facts["si_hua"],
        },
        "query": {
            "type": inp.query_type,
            "from_palace": inp.from_palace,
            "to_palace": inp.to_palace,
            "mutagens": requested,
            "empty_means_all": convention.empty_means_all,
        },
        "answer": answer,
        "palace_transformations": full_table,
    }

    input_summary = {
        "birth_datetime": inp.birth_datetime.isoformat(timespec="minutes"),
        "timezone": inp.timezone,
        "gender": inp.gender,
        "query_type": inp.query_type,
        "from_palace": inp.from_palace,
        "to_palace": inp.to_palace,
        "mutagens": requested,
    }

    convention_dump = convention.model_dump()
    convention_dump["school_note"] = (
        "飞星只列「宫干四化 → 目标宫」的链路。空四化列表按全部四化处理。"
        "本版本不提供「禄转忌」「忌转忌」这类复合推演，也不解读吉凶。"
    )
    warnings.append(convention_dump["school_note"])
    if inp.query_type == "flies_to" and not answer.get("connected"):
        warnings.append(
            f"「{inp.from_palace}」的四化没有一条落在「{inp.to_palace}」，两宫之间不存在飞化连接。"
        )

    source_refs = [
        {"type": "rule", "id": "ziwei.flying.palace_stem", "note": "十二宫宫干各自四化，落宫由目标星所在宫决定"},
        {"type": "rule", "id": "ziwei.sihua.year_stem", "note": "四化表与生年干四化同源，不另立一份"},
        {"type": "rule", "id": "ziwei.flying.query", "note": "查询分三类：从某宫飞、飞入某宫、两宫之间是否有飞化"},
    ]

    return ChartResult(
        domain="ziwei_flying",
        algorithm_version=settings.ziwei_flying_algorithm_version,
        input_summary=input_summary,
        convention=convention_dump,
        chart_facts=chart_facts,
        triggered_rules=[],
        warnings=warnings,
        source_refs=source_refs,
    )
