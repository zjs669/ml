"""降级模板。

模型两次都没通过校验时，不返回"半个报告"，而是返回一个只含盘面事实的固定结构，
并在顶部明写"知识库依据不足 / 模型输出未通过校验"，让用户知道发生了什么。
降级不使用模型输出的一字一句，避免把不合规内容带到界面。
"""

from __future__ import annotations

from typing import Any

from app.domains.llm.mock import SAFETY_NOTE, pillar_sentence

REASON_TEMPLATES = {
    "validation": "本次 AI 解读未通过服务端校验（{reason}），已降级为仅展示盘面事实。",
    "upstream": "模型服务暂时不可用（{reason}），本次未生成任何解释，已降级为仅展示盘面事实。",
    "budget": "今日模型调用预算已用尽（{reason}），本次未调用模型，已降级为仅展示盘面事实。",
    "unconfigured": "当前未配置可用的大模型（{reason}），已降级为仅展示盘面事实。",
}


def build_degraded(
    *,
    facts: dict[str, Any],
    rules: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    warnings: list[str],
    reason: str,
    reason_kind: str = "validation",
    fatal_codes: list[str] | None = None,
) -> dict[str, Any]:
    observations: list[dict[str, Any]] = []
    for key in ("year", "month", "day", "hour"):
        pillar = facts.get("pillars", {}).get(key)
        if pillar:
            observations.append({"fact": pillar_sentence(key, pillar), "rule_ids": [], "citation_ids": []})

    counts = facts.get("five_elements_count", {})
    raw = counts.get("raw", {})
    if raw:
        detail = "，".join(f"{element} {raw.get(element, 0):g}" for element in ("木", "火", "土", "金", "水"))
        observations.append({"fact": f"五行计数（原值）：{detail}", "rule_ids": [], "citation_ids": []})

    for rule in rules:
        observations.append(
            {
                "fact": f"触发关系规则「{rule['relation']}」：{rule['label']}",
                "rule_ids": [rule["rule_id"]],
                "citation_ids": [],
            }
        )

    uncertainties = [
        REASON_TEMPLATES.get(reason_kind, REASON_TEMPLATES["validation"]).format(reason=reason),
    ]
    if reason_kind in ("budget", "upstream", "unconfigured"):
        uncertainties.append("本次未成功调用模型，已预扣的额度全额退还，不会计费。")
    if fatal_codes:
        uncertainties.append("校验未通过项：" + "、".join(sorted(set(fatal_codes))))
    uncertainties.extend(str(item) for item in warnings)
    if chunks:
        uncertainties.append(
            "知识库已命中相关条目，但未生成带引用的解释；可在知识库页面直接查阅原文。"
        )
    else:
        uncertainties.append("知识库依据不足，因此未给出任何传统解释。")
    uncertainties.append("不同流派对口径与权重的处理存在差异，本页按已声明口径输出。")

    return {
        "summary": (
            f"日主为{facts.get('day_master', {}).get('stem', '')}"
            f"（{facts.get('day_master', {}).get('polarity', '')}{facts.get('day_master', {}).get('element', '')}），"
            f"已触发 {len(rules)} 条关系规则。AI 解读部分已降级，仅保留确定性事实。"
        ),
        "observations": observations,
        "traditional_interpretations": [],
        "practical_reflections": [
            "可先依据盘面事实自行核对出生时间与口径设置，确认无误后再重新生成解读。",
            "如需典籍原文，请到知识库页面检索对应术语。",
        ],
        "uncertainties": uncertainties,
        "citations": [chunk["chunk_id"] for chunk in chunks][:6],
        "safety_note": SAFETY_NOTE,
    }
