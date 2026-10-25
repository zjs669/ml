"""MBTI 式问卷引擎：逐题计票 → 四维倾向 → 结构化的作答分布。

固定顺序：
1. 校验作答齐全（缺题拒绝，不按缺省值补）；
2. 逐题把 A/B 映射到维度两极并计票；
3. 每维比较两极票数：多数极为倾向，平票记 `X`（未分化）；
4. 拼接四维代码，例如 `ENFP` 或 `EXFP`（中间出现 X 表示该维平票）。

为什么平票不强行归极：40 题版本每维只有 10 题，5:5 是真实可能出现的状态。
把它硬归到某一极会制造「测出来很确定」的假象，比标 `X` 更糟。

红线：只输出票数与倾向，不给人格描述、不给职业建议、不给关系建议。
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.domains.bazi.schemas import ChartResult
from app.domains.mbti import items as K
from app.domains.mbti.schemas import MbtiConvention, MbtiInput

TIE_MARK = "X"


def calculate(inp: MbtiInput, conv: MbtiConvention | None = None) -> ChartResult:
    convention = conv or MbtiConvention()
    warnings: list[str] = [K.SCHOOL_NOTE]

    by_id = {item.id: item for item in K.QUESTIONS}
    tally: dict[str, dict[str, int]] = {
        dim: {pole_a: 0, pole_b: 0} for dim, pole_a, pole_b in K.DIMENSIONS
    }
    per_question: list[dict[str, Any]] = []

    for qid, choice in inp.answers.items():
        question = by_id[qid]
        pole = question.pole_a if choice == "A" else question.pole_b
        tally[question.dimension][pole] += 1
        per_question.append(
            {
                "id": qid,
                "dimension": question.dimension,
                "choice": choice,
                "pole": pole,
            }
        )

    dimensions: list[dict[str, Any]] = []
    code_parts: list[str] = []
    for dim, pole_a, pole_b in K.DIMENSIONS:
        counts = tally[dim]
        total = counts[pole_a] + counts[pole_b]
        if counts[pole_a] > counts[pole_b]:
            tendency = pole_a
        elif counts[pole_b] > counts[pole_a]:
            tendency = pole_b
        else:
            tendency = TIE_MARK
        code_parts.append(tendency)
        dimensions.append(
            {
                "dimension": dim,
                "name": K.DIMENSION_LABELS[dim]["name"],
                "poles": {
                    pole_a: {"label": K.DIMENSION_LABELS[dim][pole_a], "count": counts[pole_a]},
                    pole_b: {"label": K.DIMENSION_LABELS[dim][pole_b], "count": counts[pole_b]},
                },
                "total": total,
                "tendency": tendency,
                "tendency_label": (
                    "未分化（平票）"
                    if tendency == TIE_MARK
                    else K.DIMENSION_LABELS[dim][tendency]
                ),
                "strength": abs(counts[pole_a] - counts[pole_b]),
            }
        )

    code = "".join(code_parts)
    undifferentiated = [item["dimension"] for item in dimensions if item["tendency"] == TIE_MARK]
    if undifferentiated:
        warnings.append(
            f"以下维度平票，记为未分化（X）：{'、'.join(undifferentiated)}；"
            "这表示本次作答在该维度没有明显倾向，不是数据缺失。"
        )

    chart_facts: dict[str, Any] = {
        "bank": {
            "version": K.BANK_VERSION,
            "question_count": len(K.QUESTIONS),
            "per_dimension": {dim: sum(1 for q in K.QUESTIONS if q.dimension == dim) for dim, _, _ in K.DIMENSIONS},
            "self_authored": True,
        },
        "code": code,
        "dimensions": dimensions,
        "undifferentiated": undifferentiated,
        "answers_recorded": inp.store_answers,
    }
    if inp.store_answers:
        chart_facts["answers"] = per_question

    input_summary = {
        "answered": len(inp.answers),
        "question_count": len(K.QUESTIONS),
        "bank_version": K.BANK_VERSION,
        "store_answers": inp.store_answers,
    }

    convention_dump = convention.model_dump()
    convention_dump["school_note"] = K.SCHOOL_NOTE
    if not inp.store_answers:
        warnings.append("已按你的选择不保存作答明细，只保留四维票数。")

    source_refs = [
        {"type": "rule", "id": "mbti.bank.self_authored", "note": f"题库为自编 {len(K.QUESTIONS)} 题，不复制第三方题库"},
        {"type": "rule", "id": "mbti.scoring.equal_weight", "note": "每题一票，不做加权，每维独立计票"},
        {"type": "rule", "id": "mbti.tie.undifferentiated", "note": "平票记为 X（未分化），不强行归到某一极"},
        {"type": "structure", "id": "mbti.four_dimension", "note": "四维二分倾向是公开的测量思路；本实现不是官方 MBTI 量表"},
    ]

    return ChartResult(
        domain="mbti",
        algorithm_version=settings.mbti_algorithm_version,
        input_summary=input_summary,
        convention=convention_dump,
        chart_facts=chart_facts,
        triggered_rules=[],
        warnings=warnings,
        source_refs=source_refs,
    )
