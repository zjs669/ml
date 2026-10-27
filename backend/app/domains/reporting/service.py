"""报告生成编排（计划 6.6）。

固定顺序：加载盘面 → 选技能 → 检索片段 → 预扣额度 → 调模型 → 校验
→ （失败则一次受控重试）→ 结算或退款 → 落库。
任何一步失败都不会留下"半份报告"或"扣了费却没内容"的状态。
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from string import Template
from typing import Any

from sqlalchemy.orm import Session

from app.core import metrics
from app.core.config import settings
from app.core.db import utcnow
from app.domains.billing import ledger
from app.domains.llm.base import LLMRequest, LLMResponse, LLMUnavailable
from app.domains.llm.openai_compatible import get_provider
from app.domains.llm.validator import FATAL, ValidationResult, validate
from app.domains.reporting import coerce, fallback, retrieval
from app.domains.skills import skillfile
from app.domains.skills.loader import SkillSpec, resolve
from app.models import AiReport, ChartRecord
from app.repositories import chart_repo, knowledge_repo, llm_repo, report_repo

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

STATUS_COMPLETE = "complete"
STATUS_DEGRADED = "degraded"

# 把输出契约再写一遍在**用户**消息末尾：实测部分模型对 system 里的格式要求服从度低，
# 但会把最后一段当指令执行。这里只重复结构，不重复业务规则。
OUTPUT_CONTRACT = """
━━━━ 输出契约（逐字遵守）━━━━
只输出一个 JSON 对象，不要 Markdown 代码块，顶层恰好这 7 个键：
{"summary": "字符串",
 "observations": [{"fact": "字符串", "rule_ids": ["rule_id"], "citation_ids": [1]}],
 "traditional_interpretations": [{"claim": "字符串", "citation_ids": [1], "school_note": null}],
 "practical_reflections": ["字符串"],
 "uncertainties": ["字符串"],
 "citations": [1],
 "safety_note": "字符串"}
observations 的元素只允许 fact / rule_ids / citation_ids；
traditional_interpretations 的元素只允许 claim / citation_ids / school_note。
不要输出 skill / version / scope / chart_basis 等自定义字段；不确定的内容写进 uncertainties。
"""


def system_prompt() -> str:
    return (PROMPTS_DIR / f"{settings.prompt_version}.txt").read_text(encoding="utf-8")


def build_user_prompt(
    spec: SkillSpec,
    *,
    facts: dict[str, Any],
    rules: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    depth: str,
    topic: str | None,
    skill_text: str = "",
) -> str:
    rule_payload = {
        "rules": rules,
        "conflicts": facts.get("relations", {}).get("conflicts", []),
        "incomplete": facts.get("relations", {}).get("incomplete", []),
    }
    chunk_payload = [
        {
            "chunk_id": item["chunk_id"],
            "topic": item["topic"],
            "title": item["title"],
            "citation_label": item["citation_label"],
            "location": item["location"],
            "snippet": item["snippet"],
        }
        for item in chunks
    ]
    template = Template(spec.prompt_text())
    body = template.safe_substitute(
        skill_key=spec.skill_key,
        skill_version=spec.version,
        depth=depth,
        facts_json=json.dumps(facts, ensure_ascii=False, indent=2),
        rules_json=json.dumps(rule_payload, ensure_ascii=False, indent=2),
        chunks_json=json.dumps(chunk_payload, ensure_ascii=False, indent=2),
        topic_text=topic or "（未指定，按总览处理）",
    )
    # 把「本次到底触发了哪些规则」写成白名单：模型最容易多写关系，白名单比笼统要求有效得多
    if rules:
        allow = "、".join(str(item["rule_id"]) for item in rules)
        body += f"\n本次真实触发的 rule_id 只有：{allow}。其他 rule_id 一律不许出现，也不要描述未列出的关系。"
    else:
        body += "\n本次没有触发任何关系规则：不要描述任何刑冲合害关系，也不要推测应有而未有的关系。"
    # 蒸馏技能卡：只提供叙述顺序与自查点，不作为事实或引用来源
    body = body.rstrip()
    if skill_text:
        body = skill_text.strip() + "\n\n" + body
    return body + "\n" + OUTPUT_CONTRACT


def _retry_hint(result: ValidationResult) -> str:
    """把"未通过校验"压缩成模型看得懂的修正提示（只取前 3 条 fatal）。"""
    fatal = [issue for issue in result.issues if issue.severity == FATAL][:3]
    if not fatal:
        return "schema_invalid"
    return "；".join(
        f"{issue.path or '-'} {issue.code}：{issue.detail}" for issue in fatal
    )


def _call_with_retry(
    *,
    session: Session,
    user_id: int,
    chart_id: int,
    domain: str,
    spec: SkillSpec,
    facts: dict[str, Any],
    rules: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    warnings: list[str],
    depth: str,
    topic: str | None,
) -> tuple[LLMResponse | None, ValidationResult | None, str, str, list[int], list[str]]:
    """最多两次调用：第一次失败后带"具体问题清单"再试一次。

    返回 (响应, 校验结果, 失败原因, 失败类型, 本次调用记录 id 列表, 本轮技能 id 列表)。
    """
    try:
        provider = get_provider()
    except LLMUnavailable as exc:
        # 选了真实模型却没配 key：不静默退回 mock，也不抛 500，而是明确降级
        return None, None, str(exc), "unconfigured", [], []
    provider_name = getattr(provider, "name", settings.llm_provider)
    model_name = getattr(provider, "model", settings.llm_model)
    system = system_prompt()
    # 必读技能：每次调用都注入（与是否命中卡片无关）
    skill_block = skillfile.render(
        domain,
        text=json.dumps(facts, ensure_ascii=False) + json.dumps(rules, ensure_ascii=False),
    )
    base_user = build_user_prompt(
        spec,
        facts=facts,
        rules=rules,
        chunks=chunks,
        depth=depth,
        topic=topic,
        skill_text=skill_block.text,
    )
    triggered = {item["rule_id"] for item in rules}
    chunk_ids = {item["chunk_id"] for item in chunks}

    call_ids: list[int] = []
    last_reason = "unknown"
    last_kind = "validation"
    for attempt in range(1, 3):
        user_prompt = base_user
        if attempt == 2:
            if "截断" in last_reason:
                # 长案例上模型偶尔会写过头：第二次直接把篇幅压到硬上限
                user_prompt += (
                    "\n\n注意：上一次输出超过 token 上限被截断，无法解析。"
                    "请把 total 输出压到 900 字以内：observations 最多 3 条、"
                    "traditional_interpretations 最多 2 条，删掉重复与铺陈，只保留最关键的事实。"
                )
            else:
                user_prompt += (
                    "\n\n注意：上一次输出未通过服务端校验，具体问题如下：\n"
                    + last_reason
                    + "\n请修正后重新输出。只能输出符合 Schema 的 JSON，"
                    "不得改写任何干支，不得引用未提供的 chunk_id 或 rule_id。"
                )
        request = LLMRequest(
            task=spec.skill_key,
            system_prompt=system,
            user_prompt=user_prompt,
            context={
                "domain": domain,
                "chart_facts": facts,
                "triggered_rules": rules,
                "chunks": chunks,
                "warnings": warnings,
                "depth": depth,
            },
            max_output_tokens=spec.max_output_tokens,
        )
        try:
            response = provider.generate_json(request)
        except LLMUnavailable as exc:
            last_reason = str(exc)
            last_kind = "upstream"
            call = llm_repo.record(
                session,
                task=spec.skill_key,
                provider=provider_name,
                model=model_name,
                prompt_version=settings.prompt_version,
                skill_key=spec.skill_key,
                attempt=attempt,
                ok=False,
                error_code="llm_unavailable",
                user_id=user_id,
                chart_id=chart_id,
            )
            call_ids.append(call.id)
            continue
        # 先整形再校验：模型常在信封上跑偏（自造顶层键、observations 用 facts 数组），
        # 这部分只影响结构，不影响事实；真实问题仍由 validate() 判死。
        # 传入 chunk_ids / triggered，让整形层能删掉「自造的引用」与「未触发的关系」，
        # 而不是把整份报告判死；删掉的条数会写进 uncertainties 告知用户。
        raw_observations = response.payload.get("observations")
        raw_count = len(raw_observations) if isinstance(raw_observations, list) else 0
        payload = coerce.normalize_payload(
            response.payload, allowed_chunk_ids=chunk_ids, allowed_rule_ids=triggered
        )
        if payload:
            removed = raw_count - len(payload["observations"])
            if removed > 0:
                payload["uncertainties"] = [
                    *payload["uncertainties"],
                    f"模型有 {removed} 条描述引用了本次未触发的规则或无法核验的事实，已从报告中移除。",
                ][:20]
        dropped = coerce.dropped_keys(response.payload)
        call = llm_repo.record(
            session,
            task=spec.skill_key,
            provider=response.provider,
            model=response.model,
            prompt_version=settings.prompt_version,
            skill_key=spec.skill_key,
            attempt=attempt,
            latency_ms=response.latency_ms,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            ok=True,
            user_id=user_id,
            chart_id=chart_id,
            meta={
                "finish_reason": response.finish_reason,
                "dropped_keys": dropped,
                "skills_used": skill_block.ids,
            },
        )
        call_ids.append(call.id)
        result = validate(
            payload,
            triggered_rule_ids=triggered,
            chunk_ids=chunk_ids,
            chart_facts=facts,
            domain=domain,
        )
        if result.ok:
            return response, result, "", "", call_ids, skill_block.ids
        last_reason = _retry_hint(result)
        last_kind = "validation"
    return None, None, last_reason, last_kind, call_ids, skill_block.ids


def generate(
    session: Session,
    *,
    chart: ChartRecord,
    user_id: int,
    depth: str,
    topic: str | None,
    skill_key: str | None,
    idempotency_key: str,
) -> tuple[AiReport, bool]:
    """返回 (报告, 是否重放)。重放不重复扣费。"""
    chart_json = chart.chart_json or {}
    facts = dict(chart_json.get("chart_facts", {}))
    rules = list(chart_json.get("triggered_rules", []))
    warnings = list(chart_json.get("warnings", []))

    existing = ledger.find_event(session, idempotency_key)
    if existing is not None:
        replay = report_repo.find_replay(
            session,
            chart_id=chart.id,
            user_id=user_id,
            depth=depth,
            since=existing.created_at - timedelta(seconds=1),
        )
        if replay is not None:
            return replay, True

    resolution = resolve(
        domain=chart.domain,
        depth=depth,
        relation_count=len(rules),
        topic=topic,
        skill_key=skill_key,
        convention=chart.convention_json or {},
    )
    spec = resolution.spec

    # 检索词 = 盘面派生（这份盘真实触发的关系）+ 技能包声明（通用兜底）+ 用户指定
    # 只用手写的静态词表会漏：bazi.relations.v1 声明的七个主题全是地支，
    # 而 triggered_rules 里天干关系高频，导致天干条文永远召回不到。
    derived_topics = retrieval.derive_topics(rules)
    topics = retrieval.merge_topics(
        declared=spec.retrieval.topics,
        derived=derived_topics,
        extra=[topic] if topic else [],
    )
    chunks = knowledge_repo.search_topics(
        session, topics=topics, domain=chart.domain, limit=spec.retrieval.top_k
    )

    reservation = ledger.reserve(
        session,
        user_id=user_id,
        reference_type="report",
        reference_id=f"{chart.id}:{depth}",
        idempotency_key=idempotency_key,
        units=1,
        allow_free=depth == "brief",
    )

    budget = settings.llm_daily_total_budget
    budget_exhausted = budget > 0 and llm_repo.count_today(session) >= budget
    response: LLMResponse | None
    validation: ValidationResult | None
    call_ids: list[int]
    skill_ids: list[str]
    if budget_exhausted:
        response, validation = None, None
        reason, reason_kind = "daily_budget_exhausted", "budget"
        call_ids = []
        skill_ids = []
    else:
        response, validation, reason, reason_kind, call_ids, skill_ids = _call_with_retry(
            session=session,
            user_id=user_id,
            chart_id=chart.id,
            domain=chart.domain,
            spec=spec,
            facts=facts,
            rules=rules,
            chunks=chunks,
            warnings=warnings,
            depth=depth,
            topic=topic,
        )

    if response is not None and validation is not None and validation.ok and validation.payload:
        payload = validation.payload.model_dump()
        status = STATUS_COMPLETE
        metrics.inc("llm_call_total", {"model": response.model, "result": "ok"})
        ledger.settle(session, reservation)
        provider_name = response.provider
        model_name = response.model
        input_tokens = response.input_tokens
        output_tokens = response.output_tokens
        validation_json = {**validation.to_dict(), "skills_used": skill_ids}
    else:
        payload = fallback.build_degraded(
            facts=facts,
            rules=rules,
            chunks=chunks,
            warnings=warnings,
            reason=reason or "validation_failed",
            reason_kind=reason_kind,
            fatal_codes=(validation.fatal_codes if validation else None),
        )
        status = STATUS_DEGRADED
        # 降级原因按 kind 分标签：区分「模型答错」与「预算用尽」是排查的第一步
        metrics.inc("llm_fallback_total", {"reason": reason_kind or "unknown"})
        ledger.refund(session, reservation, reason="report_degraded")
        provider_name = "fallback"
        model_name = "degraded-template-v1"
        input_tokens = 0
        output_tokens = 0
        validation_json = {
            **(validation.to_dict() if validation else {"ok": False, "fatal_codes": [reason], "issues": []}),
            "skills_used": skill_ids,
        }

    report = report_repo.create_report(
        session,
        user_id=user_id,
        chart_id=chart.id,
        domain=chart.domain,
        model_provider=provider_name,
        model_name=model_name,
        skill_version=f"{spec.skill_key}@{spec.version}",
        prompt_version=settings.prompt_version,
        chart_snapshot_hash=chart.snapshot_hash or chart_repo.snapshot_hash(chart_json),
        algorithm_version=chart.algorithm_version,
        depth=depth,
        report_json=payload,
        citations_json=[
            {
                "chunk_id": item["chunk_id"],
                "title": item["title"],
                "citation_label": item["citation_label"],
                "location": item["location"],
                "license_status": item["license_status"],
                "snippet": item["snippet"],
            }
            for item in chunks
        ],
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        validation_json=validation_json,
        status=status,
    )
    llm_repo.attach_report(session, call_ids=call_ids, report_id=report.id)
    session.commit()
    return report, False


def serialize(report: AiReport) -> dict[str, Any]:
    return {
        "id": report.id,
        "chart_id": report.chart_id,
        "domain": report.domain,
        "depth": report.depth,
        "status": report.status,
        "model_provider": report.model_provider,
        "model_name": report.model_name,
        "skill_version": report.skill_version,
        "prompt_version": report.prompt_version,
        "algorithm_version": report.algorithm_version,
        "chart_snapshot_hash": report.chart_snapshot_hash,
        "report": report.report_json,
        "citations": report.citations_json,
        "validation": report.validation_json,
        "created_at": (report.created_at or utcnow()).isoformat() + "Z",
    }
