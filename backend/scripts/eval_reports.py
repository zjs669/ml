"""真实模型报告评测。

    python -m scripts.eval_reports --cases 10
    python -m scripts.eval_reports --cases 24 --depth brief --out ../docs/模型评测.md

跑基准命例 → 保存命盘 → 生成报告，统计四项门槛：
schema 通过率 ≥95%、引用合法率 100%、降级率 ≤5%、P50/P95 延迟与 token 成本。
结果写成 Markdown，方便直接贴进验收记录。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal, utcnow
from app.core.security import hash_password
from app.domains.bazi.engine import calculate as calculate_bazi
from app.domains.billing import ledger
from app.domains.reporting import service as reporting_service
from app.models.user import User
from app.repositories import chart_repo
from app.schemas.charts import CalculateIn

DEFAULT_CASES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "bazi_cases.json"
# 2026-10 重构：三份评测文档已合并为 docs/模型评测.md
DEFAULT_OUT = Path(__file__).resolve().parents[2] / "docs" / "模型评测.md"

PANEL = "=" * 60


def _percentile(values: list[int], ratio: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * ratio))))
    return ordered[index]


def _citation_ok(report_json: dict[str, Any], citations: list[dict[str, Any]]) -> bool:
    """每条传统解释的引用必须落在本次真实检索出的片段集合里。"""
    available = {item.get("chunk_id") for item in citations}
    interpretations = report_json.get("traditional_interpretations") or []
    if not interpretations:
        return True
    if not available:
        return False
    for item in interpretations:
        ids = item.get("citation_ids") or []
        if not ids or not set(ids) <= available:
            return False
    return True


def _ensure_user(session: Session, credits: int) -> User:
    user = User(
        email=f"eval_{uuid.uuid4().hex[:10]}@example.com",
        password_hash=hash_password("Eval0nly!Pass"),
        status="active",
        token_version=0,
    )
    session.add(user)
    session.flush()
    ledger.grant(
        session,
        user_id=user.id,
        units=credits,
        reason="模型评测临时额度",
        idempotency_key=f"eval-grant:{user.id}",
    )
    session.commit()
    return user


def _run_case(
    session: Session, *, user: User, case: dict[str, Any], depth: str
) -> dict[str, Any]:
    payload = CalculateIn.model_validate(case["input"])
    result = calculate_bazi(payload, payload.convention)
    chart = chart_repo.create_chart(
        session,
        owner_id=user.id,
        domain=result.domain,
        title=f"评测-{case['id']}",
        input_json=result.input_summary,
        chart_json=result.model_dump(),
        convention_json=result.convention,
        algorithm_version=result.algorithm_version,
        delete_after=None,
    )
    session.commit()

    started = time.monotonic()
    report, _ = reporting_service.generate(
        session,
        chart=chart,
        user_id=user.id,
        depth=depth,
        topic=None,
        skill_key=None,
        idempotency_key=f"eval-{case['id']}-{uuid.uuid4().hex[:8]}",
    )
    elapsed_ms = int((time.monotonic() - started) * 1000)

    validation = report.validation_json or {}
    report_json = report.report_json or {}
    citations = report.citations_json or []
    complete = report.status == "complete"
    return {
        "id": case["id"],
        "status": report.status,
        "pillars": " ".join(
            item["text"] for item in (result.model_dump()["chart_facts"]["pillars"]).values()
        ),
        "latency_ms": elapsed_ms,
        "tokens_in": report.input_tokens or 0,
        "tokens_out": report.output_tokens or 0,
        "schema_ok": bool(complete and validation.get("ok") is True),
        "citation_ok": _citation_ok(report_json, citations),
        "degraded": report.status == "degraded",
        "degraded_reason": (
            (report_json.get("uncertainties") or [""])[0] if report.status == "degraded" else ""
        ),
    }


def _render(rows: list[dict[str, Any]], *, depth: str) -> str:
    total = len(rows)
    schema_pass = sum(1 for row in rows if row["schema_ok"]) / total if total else 0.0
    citation_pass = sum(1 for row in rows if row["citation_ok"]) / total if total else 0.0
    degraded = sum(1 for row in rows if row["degraded"]) / total if total else 0.0
    latencies = [row["latency_ms"] for row in rows]
    tokens_in = sum(row["tokens_in"] for row in rows)
    tokens_out = sum(row["tokens_out"] for row in rows)
    cost = settings.estimate_cost(tokens_in, tokens_out)

    lines = [
        "# 模型评测",
        "",
        f"> 生成时间：{utcnow().isoformat()}Z　　脚本：`python -m scripts.eval_reports`",
        "",
    ]
    if not settings.llm_configured:
        lines.extend(
            [
                "> **警告：本次运行不是真实模型（`LLM_MODE=mock` 或未配置 key），"
                "以下数字只能证明管线跑通，不能作为模型质量结论。**",
                "",
            ]
        )
    lines.extend(
        [
            "## 运行环境",
            "",
            f"- LLM_MODE：`{settings.llm_mode}`",
            f"- 模型：`{settings.llm_model}`",
            f"- JSON 模式：`{settings.llm_json_mode}`",
            f"- 解读深度：`{depth}`",
            f"- 命例数：{total}",
            f"- 单价（元/千 token）：输入 {settings.llm_price_input_per_1k} / 输出 {settings.llm_price_output_per_1k}",
            "",
            "## 门槛结果",
            "",
            "| 指标 | 实测 | 门槛 | 判定 |",
            "|---|---:|---:|---|",
            f"| schema 通过率 | {schema_pass:.1%} | ≥95% | {'通过' if schema_pass >= 0.95 else '未达'} |",
            f"| 引用合法率 | {citation_pass:.1%} | 100% | {'通过' if citation_pass >= 1.0 else '未达'} |",
            f"| 降级率 | {degraded:.1%} | ≤5% | {'通过' if degraded <= 0.05 else '未达'} |",
            f"| P50 延迟 | {_percentile(latencies, 0.5)} ms | — | — |",
            f"| P95 延迟 | {_percentile(latencies, 0.95)} ms | — | — |",
            f"| token 合计 | 输入 {tokens_in} / 输出 {tokens_out} | — | — |",
            f"| 成本合计 | {'未配置单价' if cost is None else f'{cost:.6f} 元'} | — | — |",
            "",
            "## 逐例结果",
            "",
            "| 命例 | 四柱 | 状态 | schema | 引用 | 延迟(ms) | token(入/出) |",
            "|---|---|---|---|---|---:|---|",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row['id']} | {row['pillars']} | {row['status']} | "
            f"{'✓' if row['schema_ok'] else '✗'} | {'✓' if row['citation_ok'] else '✗'} | "
            f"{row['latency_ms']} | {row['tokens_in']}/{row['tokens_out']} |"
        )
    failures = [row for row in rows if row["degraded"]]
    if failures:
        lines.extend(["", "## 降级明细", ""])
        for row in failures:
            lines.append(f"- `{row['id']}`：{row['degraded_reason'] or '（无原因文本）'}")
    lines.extend(
        [
            "",
            "## 说明",
            "",
            "- schema 通过率统计的是「完整返回且通过服务端校验」的比例，降级报告一律记为未通过；",
            "- 引用合法率检查每条传统解释的 `citation_ids` 是否真实落在本次检索到的片段里；",
            "- 延迟为端到端耗时（含检索、调用、校验、落库），不是模型单次响应时间；",
            "- 本文件由脚本覆盖生成，不要手工编辑。",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="真实模型报告评测")
    parser.add_argument("--cases", type=int, default=10, help="跑前 N 个基准命例")
    parser.add_argument("--depth", default="brief", choices=["brief", "detailed"])
    parser.add_argument("--suite", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    suite = json.loads(args.suite.read_text(encoding="utf-8"))
    cases = suite["cases"][: max(1, args.cases)]

    print(PANEL)
    print(f"模式 {settings.llm_mode} | 模型 {settings.llm_model} | 命例 {len(cases)} | 深度 {args.depth}")
    if not settings.llm_configured:
        print("提示：当前不是真实模型（LLM_MODE=mock 或未配 key），本次结果只能验证管线，不能当作模型质量结论。")
    print(PANEL)

    session = SessionLocal()
    try:
        user = _ensure_user(session, credits=len(cases) + 5)
        rows: list[dict[str, Any]] = []
        for index, case in enumerate(cases, start=1):
            row = _run_case(session, user=user, case=case, depth=args.depth)
            rows.append(row)
            print(
                f"[{index}/{len(cases)}] {row['id']:<18} {row['status']:<9} "
                f"schema={'OK' if row['schema_ok'] else 'NG'} "
                f"cite={'OK' if row['citation_ok'] else 'NG'} {row['latency_ms']}ms"
            )
    finally:
        session.close()

    markdown = _render(rows, depth=args.depth)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(markdown, encoding="utf-8")

    total = len(rows)
    schema_pass = sum(1 for row in rows if row["schema_ok"]) / total
    citation_pass = sum(1 for row in rows if row["citation_ok"]) / total
    degraded = sum(1 for row in rows if row["degraded"]) / total
    print(PANEL)
    print(f"schema 通过率 {schema_pass:.1%} | 引用合法率 {citation_pass:.1%} | 降级率 {degraded:.1%}")
    print(f"评测报告已写入 {args.out}")
    print(PANEL)
    ok = schema_pass >= 0.95 and citation_pass >= 1.0 and degraded <= 0.05
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
