"""命盘导出（纯文本 / Markdown）。

导出内容统一带 AI 生成内容标识（《人工智能生成合成内容标识办法》要求），
并且把口径、算法版本、规则 ID 一并写明，方便复核。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chart import ChartRecord
from app.models.report import AiReport

AI_NOTICE = "本内容由「玄枢国学研习台」生成，含 AI 生成的解释文本，仅供传统文化研习与娱乐参考，不构成医疗、法律、投资或其他专业建议。"


def _pillar_block(facts: dict[str, Any]) -> list[str]:
    pillars = facts.get("pillars", {})
    labels = {"year": "年柱", "month": "月柱", "day": "日柱", "hour": "时柱"}
    lines = ["| 位置 | 干支 | 天干五行 | 地支五行 | 十神 | 藏干 |", "| --- | --- | --- | --- | --- | --- |"]
    for key in ("year", "month", "day", "hour"):
        item = pillars.get(key)
        if not item:
            continue
        hidden = "、".join(f"{h['stem']}({h['level']})" for h in item.get("hidden_stems", []))
        lines.append(
            f"| {labels[key]} | {item['text']} | {item['stem_element']} | {item['branch_element']} "
            f"| {item['ten_god']} | {hidden} |"
        )
    return lines


def _element_block(facts: dict[str, Any]) -> list[str]:
    counts = facts.get("five_elements_count", {})
    raw = counts.get("raw", {})
    weighted = counts.get("weighted", {})
    cells = [f"{element} {raw.get(element, 0):g}/{weighted.get(element, 0):g}" for element in ("木", "火", "土", "金", "水")]
    return ["五行（原值/加权）: " + "，".join(cells), ""]


def _relation_block(facts: dict[str, Any]) -> list[str]:
    relations = facts.get("relations", {})
    rules = relations.get("rules", [])
    if not rules:
        return ["刑冲合害：本盘未触发任何已登记的关系规则。", ""]
    lines = ["刑冲合害（仅列触发事实，不含吉凶判断）："]
    for item in rules:
        lines.append(f"- [{item['relation']}] {item['label']} `{item['rule_id']}` — {item['note']}")
    for conflict in relations.get("conflicts", []):
        lines.append(f"- 提示：{conflict['type']}（{('、'.join(conflict['relations']))}）")
    lines.append("")
    return lines


def _dayun_block(facts: dict[str, Any]) -> list[str]:
    dayun = facts.get("dayun", {})
    if not dayun.get("computed"):
        return [f"大运：{dayun.get('reason', '未推算')}", ""]
    start = dayun.get("start_age", {})
    lines = [
        f"大运：{'顺排' if dayun.get('forward') else '逆排'}，起运 {start.get('text', '')}，"
        f"起运年份约 {dayun.get('start_datetime_estimate', '')}",
        "注意：" + dayun.get("error_bound", ""),
        "",
    ]
    for item in dayun.get("list", []):
        lines.append(f"- 第 {item['index']} 运 {item['pillar']}（{item['start_age_years']}–{item['end_age_years']} 岁）")
    lines.append("")
    return lines


def build_export_text(record: ChartRecord, fmt: str = "md", session: Session | None = None) -> str:
    chart = record.chart_json or {}
    facts = chart.get("chart_facts", {})
    convention = record.convention_json

    lines: list[str] = []
    lines.append(f"# {record.title or '未命名命盘'}")
    lines.append("")
    lines.append(f"> {AI_NOTICE}")
    lines.append("")
    lines.append(f"- 算法版本：{record.algorithm_version}")
    lines.append(f"- 排盘口径：年界 {convention.get('year_boundary')}，换日 {convention.get('day_boundary')}，"
                 f"真太阳时 {convention.get('solar_time')}，体系 {convention.get('school')}")
    lines.append(f"- 出生信息：{chart.get('input_summary', {}).get('birth_datetime')} "
                 f"({chart.get('input_summary', {}).get('timezone')})")
    lines.append(f"- 导出时间（UTC）：{record.updated_at.isoformat()}")
    lines.append("")
    lines.append("## 四柱")
    lines.append("")
    lines.extend(_pillar_block(facts))
    lines.append("")
    day_master = facts.get("day_master", {})
    lines.append(f"日主：{day_master.get('stem', '')}（{day_master.get('polarity', '')}{day_master.get('element', '')}）")
    lines.append("")
    lines.extend(_element_block(facts))
    lines.extend(_relation_block(facts))
    lines.extend(_dayun_block(facts))

    for warning in chart.get("warnings", []):
        lines.append(f"- 提醒：{warning}")
    lines.append("")

    if session is not None:
        report = session.scalar(
            select(AiReport)
            .where(AiReport.chart_id == record.id)
            .order_by(AiReport.created_at.desc())
            .limit(1)
        )
        if report is not None:
            payload = report.report_json or {}
            lines.append("## AI 解读（已标注依据）")
            lines.append("")
            lines.append(f"> 模型 {report.model_provider}/{report.model_name}，技能 {report.skill_version}，"
                         f"生成于 {report.created_at.isoformat()}（UTC）")
            lines.append("")
            for key, heading in (
                ("summary", "概要"),
                ("observations", "盘面事实"),
                ("traditional_interpretations", "传统解释"),
                ("practical_reflections", "现实可验证的建议"),
                ("uncertainties", "不确定项"),
            ):
                value = payload.get(key)
                if not value:
                    continue
                lines.append(f"### {heading}")
                lines.append("")
                if isinstance(value, str):
                    lines.append(value)
                else:
                    for item in value:
                        if isinstance(item, dict):
                            lines.append(f"- {item.get('fact') or item.get('claim') or item}")
                            for cid in item.get("citation_ids", []) or []:
                                lines.append(f"  - 依据：{cid}")
                        else:
                            lines.append(f"- {item}")
                lines.append("")
            lines.append(f"**安全说明**：{payload.get('safety_note', '')}")
            lines.append("")

    text = "\n".join(lines)
    if fmt == "txt":
        text = text.replace("| --- | --- | --- | --- | --- | --- |", "-" * 40)
        for mark in ("# ", "## ", "### ", "- ", "> "):
            text = text.replace(mark, "")
        text = text.replace("|", " ")
    return text
