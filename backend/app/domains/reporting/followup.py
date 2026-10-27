"""报告追问：在同一份报告的材料范围内续答。

与 `service.generate()` 的差别（也是刻意保留的差别）：

- 不重新选技能、不重新检索知识：追问只能引用「原报告引用过的片段」。
  这样前后口径不会飘，也避免用户用追问反复触发检索去套取新内容。
- 不扣额度，但受日预算与每小时限流约束。理由：追问是同一份已付费报告的延续，
  再收一次费会迫使免费用户不敢追问；而预算熔断保证成本仍有上界。
- 校验链不变：引用必须真实、盘面不得改写、禁词一律拦。
  不合格先重试一次，仍不合格就返回**确定性降级回复**（只复述已验证的事实）。
"""

from __future__ import annotations

import json
from pathlib import Path
from string import Template
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.domains.llm.base import LLMRequest, LLMResponse, LLMUnavailable
from app.domains.llm.openai_compatible import get_provider
from app.domains.llm.validator import FollowupValidation, validate_followup
from app.domains.reporting import coerce
from app.domains.skills import skillfile
from app.models import ChartRecord
from app.models import AiReport, ReportFollowup
from app.repositories import llm_repo, report_repo

PROMPT_FILE = Path(__file__).resolve().parent / "prompts" / "followup_v1.txt"

#: 同一份报告最多追问多少轮。20 轮足够问清一个问题，又不至于把报告变成聊天室。
MAX_TURNS = 20
#: 只把最近若干轮放进上下文，避免长对话把 token 打满
HISTORY_TURNS = 6

SAFETY_NOTE = "本回答由 AI 生成，仅复述盘面事实与传统解释，不构成任何专业建议。"

#: 追问的约束全部写在模板里，system 只保留一句“你是 JSON 生成器”，
#: 避免与报告的系统提示词（七字段契约）互相干扰。
FOLLOWUP_SYSTEM = "你是一个严格基于给定材料作答的助手。只输出 JSON 对象，不要输出其它任何内容。"


class FollowupLimit(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("FOLLOWUP_LIMIT", message, status_code=400)


def prompt_template() -> str:
    return PROMPT_FILE.read_text(encoding="utf-8")


def _chunk_payload(report: AiReport) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": item.get("chunk_id"),
            "title": item.get("title"),
            "citation_label": item.get("citation_label"),
            "location": item.get("location"),
            "snippet": item.get("snippet"),
        }
        for item in (report.citations_json or [])
        if item.get("chunk_id") is not None
    ]


def _history_text(rows: list[ReportFollowup]) -> str:
    if not rows:
        return "（这是第一轮追问）"
    lines: list[str] = []
    for row in rows:
        answer = (row.answer_json or {}).get("answer") or ""
        lines.append(f"Q{row.seq}：{row.question}\nA{row.seq}：{answer[:300]}")
    return "\n".join(lines)


def _build_prompt(
    *,
    chart: ChartRecord,
    report: AiReport,
    chunks: list[dict[str, Any]],
    history: list[ReportFollowup],
    question: str,
    skill_text: str = "",
) -> str:
    chart_json = chart.chart_json or {}
    facts = chart_json.get("chart_facts", {})
    body = Template(prompt_template()).safe_substitute(
        facts_json=json.dumps(facts, ensure_ascii=False, indent=2),
        report_json=json.dumps(report.report_json or {}, ensure_ascii=False, indent=2),
        chunks_json=json.dumps(chunks, ensure_ascii=False, indent=2),
        history_text=_history_text(history),
        question=question,
    )
    if skill_text:
        body = skill_text.strip() + "\n\n" + body
    return body


#: 降级原因 → 用户可理解的两类。前端据此给不同引导：
#: OUT_OF_SCOPE 建议「重新生成报告」，MODEL_UNAVAILABLE 建议「稍后重试」。
#: 这两类混在一起时，用户会把「这个问题超出本报告材料」误读成「系统坏了」。
REASON_KIND_OUT_OF_SCOPE = "OUT_OF_SCOPE"
REASON_KIND_MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"

#: 内部 kind → 对外 reason_kind。
#: - validation：模型答了但引用越界/事实不符 → 材料不够，重新生成报告更有效
#: - unconfigured / upstream / budget：模型侧没跑起来 → 重试或稍后再说
_REASON_KIND_MAP: dict[str, str] = {
    "validation": REASON_KIND_OUT_OF_SCOPE,
    "unconfigured": REASON_KIND_MODEL_UNAVAILABLE,
    "upstream": REASON_KIND_MODEL_UNAVAILABLE,
    "budget": REASON_KIND_MODEL_UNAVAILABLE,
}


def reason_kind(kind: str) -> str:
    """把内部失败原因归成两类对外语义。未知值按「模型不可用」处理（保守：不引导用户重做无用功）。"""
    return _REASON_KIND_MAP.get(kind, REASON_KIND_MODEL_UNAVAILABLE)


def _degraded(report: AiReport, reason: str, kind: str) -> dict[str, Any]:
    """降级回复只复述「原报告里已经过校验的事实」，不生成任何新句子。

    `kind` 会写进 answer_json.reason_kind，前端据此区分「超出材料范围」与
    「模型暂时不可用」—— 前者引导重新生成报告，后者引导稍后重试。
    """
    observations = [
        item.get("fact", "") for item in (report.report_json or {}).get("observations", [])
    ]
    points = [text for text in observations if text][:5]
    return {
        "answer": "这个问题目前无法给出可靠回答，原因已列在下方。以下是原报告中已核验过的盘面事实，可据此自行核对。",
        "points": points,
        "citations": [],
        "uncertainties": [reason],
        "reason_kind": reason_kind(kind),
        "safety_note": SAFETY_NOTE,
    }


def _call_with_retry(
    *,
    session: Session,
    chart: ChartRecord,
    report: AiReport,
    user_id: int,
    chunks: list[dict[str, Any]],
    history: list[ReportFollowup],
    question: str,
) -> tuple[LLMResponse | None, FollowupValidation | None, str, str, list[str]]:
    try:
        provider = get_provider()
    except LLMUnavailable as exc:
        return None, None, str(exc), "unconfigured", []

    provider_name = getattr(provider, "name", settings.llm_provider)
    model_name = getattr(provider, "model", settings.llm_model)
    facts = (chart.chart_json or {}).get("chart_facts", {})
    skill_block = skillfile.render(
        chart.domain, text=json.dumps(facts, ensure_ascii=False) + question
    )
    user_prompt = _build_prompt(
        chart=chart,
        report=report,
        chunks=chunks,
        history=history,
        question=question,
        skill_text=skill_block.text,
    )
    chunk_ids = {item["chunk_id"] for item in chunks}
    last_reason = "unknown"
    last_kind = "validation"

    for attempt in range(1, 3):
        prompt = user_prompt
        if attempt == 2:
            prompt += (
                "\n\n注意：上一次输出未通过服务端校验，具体问题如下：\n"
                + last_reason
                + "\n请修正后只输出符合契约的 JSON，不得引用未提供的 chunk_id，不得改写盘面事实。"
            )
        request = LLMRequest(
            task="followup",
            system_prompt=FOLLOWUP_SYSTEM,
            user_prompt=prompt,
            context={"domain": chart.domain, "chart_facts": facts, "chunks": chunks},
            max_output_tokens=1200,
        )
        try:
            response = provider.generate_json(request)
        except LLMUnavailable as exc:
            last_reason = str(exc)
            last_kind = "upstream"
            llm_repo.record(
                session,
                task="followup",
                provider=provider_name,
                model=model_name,
                prompt_version=settings.prompt_version,
                skill_key=report.skill_version,
                attempt=attempt,
                ok=False,
                error_code="llm_unavailable",
                user_id=user_id,
                chart_id=chart.id,
                report_id=report.id,
            )
            continue

        payload = coerce.normalize_followup(response.payload)
        llm_repo.record(
            session,
            task="followup",
            provider=response.provider,
            model=response.model,
            prompt_version=settings.prompt_version,
            skill_key=report.skill_version,
            attempt=attempt,
            latency_ms=response.latency_ms,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            ok=True,
            user_id=user_id,
            chart_id=chart.id,
            report_id=report.id,
            meta={"finish_reason": response.finish_reason},
        )
        result = validate_followup(
            payload, chunk_ids=chunk_ids, chart_facts=facts, domain=chart.domain
        )
        if result.ok:
            return response, result, "", "", skill_block.ids
        last_reason = "；".join(
            f"{issue.path or '-'} {issue.code}：{issue.detail}"
            for issue in result.issues
            if issue.severity == "fatal"
        )[:600] or "schema_invalid"
        last_kind = "validation"
    return None, None, last_reason, last_kind, skill_block.ids


def answer(
    session: Session,
    *,
    chart: ChartRecord,
    report: AiReport,
    user_id: int,
    question: str,
) -> ReportFollowup:
    """生成一轮追问并落库。调用方负责先确认 report 属于该用户。"""
    used = report_repo.count_followups(session, report_id=report.id)
    if used >= MAX_TURNS:
        raise FollowupLimit(
            f"这份报告最多追问 {MAX_TURNS} 轮，建议针对新的疑点重新生成一份报告。"
        )

    chunks = _chunk_payload(report)
    history = report_repo.list_followups(session, report_id=report.id, limit=HISTORY_TURNS)

    budget = settings.llm_daily_total_budget
    budget_exhausted = budget > 0 and llm_repo.count_today(session) >= budget

    if budget_exhausted:
        payload = _degraded(report, "今日模型调用预算已用尽，追问暂不生成。", "budget")
        status = "degraded"
        provider_name, model_name = "fallback", "degraded-template-v1"
        tokens: tuple[int | None, int | None, int | None] = (0, 0, None)
        validation_json: dict[str, Any] = {"ok": False, "fatal_codes": ["daily_budget_exhausted"], "skills_used": []}
    else:
        response, validation, reason, failure_kind, skill_ids = _call_with_retry(
            session=session,
            chart=chart,
            report=report,
            user_id=user_id,
            chunks=chunks,
            history=history,
            question=question,
        )
        if response is not None and validation is not None and validation.ok and validation.payload:
            payload = validation.payload.model_dump()
            status = "complete"
            provider_name, model_name = response.provider, response.model
            tokens = (response.input_tokens, response.output_tokens, response.latency_ms)
            validation_json = {**validation.to_dict(), "skills_used": skill_ids}
        else:
            payload = _degraded(report, f"模型回答未通过校验：{reason[:200]}", failure_kind)
            status = "degraded"
            provider_name, model_name = "fallback", "degraded-template-v1"
            tokens = (0, 0, None)
            validation_json = {
                **(validation.to_dict() if validation else {"ok": False, "fatal_codes": [reason]}),
                "skills_used": skill_ids,
            }

    cited_ids = set(payload.get("citations") or [])
    cited = [item for item in chunks if item["chunk_id"] in cited_ids]
    row = report_repo.create_followup(
        session,
        report_id=report.id,
        user_id=user_id,
        seq=used + 1,
        question=question,
        answer_json=payload,
        citations_json=cited,
        validation_json=validation_json,
        status=status,
        model_provider=provider_name,
        model_name=model_name,
        input_tokens=tokens[0],
        output_tokens=tokens[1],
        latency_ms=tokens[2],
    )
    session.commit()
    return row


def serialize(row: ReportFollowup) -> dict[str, Any]:
    return {
        "id": row.id,
        "report_id": row.report_id,
        "seq": row.seq,
        "question": row.question,
        "answer": row.answer_json or {},
        "citations": row.citations_json or [],
        "status": row.status,
        "model_provider": row.model_provider,
        "model_name": row.model_name,
        "validation": row.validation_json,
        "created_at": (row.created_at.isoformat() + "Z") if row.created_at else "",
    }
