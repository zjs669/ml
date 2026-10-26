"""题库评测：把本地题库跑一遍，产出准确率报告与可蒸馏的错例集。

用法：
    python -m scripts.bench_eval --dataset generic \
        --file data/bench/mingli_bench/cases.jsonl --limit 50

产物：
- `docs/模型评测.md`（第二部分·题库）：覆盖面、准确率、延迟分位、按术数拆分、失败样例；
- `backend/data/bench/attempts.jsonl`：逐题记录，供 `distill_skills.py` 聚类蒸馏。

注意：
- 不做任何「猜答案」的兜底。解析失败就是错，计入 parse_failed。
- `LLM_MODE=mock` 时 mock 不会答选择题，全部计错，但报告骨架照常生成——
  这是为了让无网络的机器也能跑通链路，不代表模型水平。
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.db import SessionLocal
from app.domains.llm.base import LLMRequest, LLMUnavailable
from app.domains.llm.openai_compatible import OpenAICompatibleProvider, get_provider
from app.domains.skills import skillfile
from app.repositories import knowledge_repo
from scripts.bench import charts as chart_tools
from scripts.bench import mingli as mingli_dataset
from scripts.bench.datasets import BenchCase, append_jsonl, load_cases, write_jsonl

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
DEFAULT_ATTEMPTS = BACKEND_DIR / "data" / "bench" / "attempts.jsonl"
# 2026-10 重构：三份评测文档已合并为 docs/模型评测.md，脚本只覆盖「题库」这一部分
DEFAULT_REPORT = REPO_ROOT / "docs" / "模型评测.md"

SYSTEM = (
    "你是命理题库的答题器。第一行必须只包含一个 JSON 对象，"
    "不要输出推理过程、不要写 Markdown 代码块、不要重复题目。"
)


def build_prompt(
    case: BenchCase,
    chunks: list[dict[str, Any]] | None = None,
    chart_text: str = "",
    skill_text: str = "",
) -> str:
    options = "\n".join(f"{key}. {text}" for key, text in case.options)
    knowledge = ""
    if chunks:
        rows = "\n".join(
            f"[{item['chunk_id']}] {item['title']}（{item.get('location') or '未标注位置'}）：{item['snippet']}"
            for item in chunks
        )
        knowledge = (
            "\n可参考的知识库片段（已审核）。有依据时优先按它们作答，没有依据就按通识判断：\n"
            + rows
            + "\n"
        )
    chart_block = ""
    if chart_text:
        chart_block = (
            "\n以下是该命例的盘面事实，由确定性引擎算出，可直接引用，不要自行重算或改写：\n"
            + chart_text
            + "\n"
        )
    body = (
        f"题型：单选。请只依据题目给出的条件作答，不要引入题目之外的信息。\n"
        f"{chart_block}{knowledge}\n"
        f"题目：\n{case.question}\n\n选项：\n{options}\n\n"
        '只输出：{"answer": "选项字母", "confidence": 0.0, "reason": "不超过 80 字"}\n'
    )
    if skill_text:
        body = skill_text.strip() + "\n\n" + body
    return body


def _parse_answer(payload: dict[str, Any], case: BenchCase) -> str:
    raw = payload.get("answer") or payload.get("choice") or payload.get("option")
    if raw is None:
        return ""
    text = str(raw).strip().upper()
    keys = [key for key, _ in case.options]
    if text[:1] in keys:
        return text[:1]
    if text.isdigit():
        index = int(text) - 1
        if 0 <= index < len(case.options):
            return case.options[index][0]
    return ""


def run_cases(
    cases: list[BenchCase],
    *,
    run_id: str,
    run_tag: str,
    session: Any | None = None,
    max_output_tokens: int = 400,
    model: str | None = None,
    use_skills: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """逐题作答。`session` 非空时先检索知识库，把片段一起交给模型。

    这就是用户要的顺序：**先根据知识回答** → 错了再看为什么错 → 蒸馏成技能卡。
    检索失败（库不可用）时降级为无知识作答，并在记录里标 `kb_error`，不静默。
    """
    provider = OpenAICompatibleProvider(model=model) if model else get_provider()
    records: list[dict[str, Any]] = []
    latencies: list[int] = []
    kb_hits = 0
    for case in cases:
        started = time.monotonic()
        chunks: list[dict[str, Any]] = []
        kb_error = ""
        if session is not None:
            try:
                chunks = knowledge_repo.search(
                    session, query=case.question, domain=case.domain, limit=3
                )
            except Exception as exc:  # 知识库不可用不应阻断评测
                kb_error = exc.__class__.__name__
        if chunks:
            kb_hits += 1
        chart_text = ""
        chart_error = ""
        if case.chart_input:
            result, chart_error = chart_tools.compute(case.domain, case.chart_input)
            if result is not None:
                chart_text = chart_tools.summarize(case.domain, result)
        skill_block = (
            skillfile.render(case.domain, text=case.question + chart_text, profile="bench")
            if use_skills
            else None
        )
        record: dict[str, Any] = {
            "run_id": run_id,
            "run_tag": run_tag,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "id": case.id,
            "domain": case.domain,
            "question": case.question,
            "category": case.split,
            "expected": case.answer_key,
            "got": "",
            "correct": False,
            "error": "",
            "latency_ms": 0,
            "source": case.source,
            "model": getattr(provider, "model", settings.llm_model),
            "kb_chunks": [item["chunk_id"] for item in chunks],
            "kb_error": kb_error,
            "chart_ok": bool(chart_text),
            "chart_error": chart_error,
            "chart_notes": (case.raw or {}).get("notes") or [],
            "skills": skill_block.ids if skill_block else [],
        }
        try:
            prompt = build_prompt(
                case, chunks, chart_text, skill_block.text if skill_block else ""
            )
            response = None
            last_error = ""
            for attempt in range(2):
                try:
                    response = provider.generate_json(
                        LLMRequest(
                            task="bench.mcq",
                            system_prompt=SYSTEM,
                            user_prompt=prompt,
                            context={"domain": case.domain, "chunks": chunks},
                            max_output_tokens=max_output_tokens,
                        )
                    )
                    break
                except LLMUnavailable as exc:
                    last_error = str(exc)
                    # 这类模型容易先写一大段分析再给 JSON，撞上 token 上限：
                    # 第二次直接压成一行，不让它铺陈。
                    if attempt == 0 and "截断" in last_error:
                        prompt += "\n\n上一次输出被截断。只输出一行 JSON，不要写任何分析过程。\n"
                        continue
                    raise
            if response is None:  # pragma: no cover - 循环内已抛异常
                raise LLMUnavailable(last_error or "empty response")
            record["got"] = _parse_answer(response.payload, case)
            record["correct"] = record["got"] == case.answer_key and bool(record["got"])
            if not record["got"]:
                record["error"] = "answer_not_parsed"
            record["raw"] = json.dumps(response.payload, ensure_ascii=False)[:600]
        except LLMUnavailable as exc:
            record["error"] = str(exc)
        except Exception as exc:  # 单题失败不终止整轮评测
            record["error"] = f"{exc.__class__.__name__}: {exc}"
        record["latency_ms"] = int((time.monotonic() - started) * 1000)
        latencies.append(record["latency_ms"])
        records.append(record)

    total = len(records)
    correct = sum(1 for item in records if item["correct"])
    parse_failed = sum(1 for item in records if item["error"] == "answer_not_parsed")
    errors = sum(1 for item in records if item["error"] and item["error"] != "answer_not_parsed")
    by_domain: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "correct": 0})
    by_category: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "correct": 0})
    chart_failed = 0
    for item in records:
        bucket = by_domain[item["domain"]]
        bucket["total"] += 1
        bucket["correct"] += 1 if item["correct"] else 0
        category = str(item.get("category") or "未分类")
        cat_bucket = by_category[category]
        cat_bucket["total"] += 1
        cat_bucket["correct"] += 1 if item["correct"] else 0
        if item.get("chart_error"):
            chart_failed += 1

    summary = {
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else 0.0,
        "parse_failed": parse_failed,
        "errors": errors,
        "kb_hit_rate": round(kb_hits / total, 4) if total else 0.0,
        "chart_failed": chart_failed,
        "p50_ms": int(statistics.median(latencies)) if latencies else 0,
        "p95_ms": int(sorted(latencies)[max(int(len(latencies) * 0.95) - 1, 0)]) if latencies else 0,
        "by_domain": dict(by_domain),
        "by_category": dict(by_category),
        "model": getattr(provider, "model", settings.llm_model),
        "provider": getattr(provider, "name", settings.llm_provider),
        "llm_mode": settings.llm_mode,
    }
    return records, summary


def render_report(*, dataset: str, file: Path, loaded, summary: dict[str, Any], records: list[dict[str, Any]]) -> str:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# 题库评测报告",
        "",
        f"> 本文件由 `python -m scripts.bench_eval` 覆盖生成（{stamp}），不要手工编辑。",
        "",
        "## 1. 本轮配置",
        "",
        "| 项 | 值 |",
        "|---|---|",
        f"| 数据集格式 | `{dataset}` |",
        f"| 题目文件 | `{file}` |",
        f"| 本轮 run_id | `{summary['run_id']}` |",
        f"| 参与评测 | {summary['total']} 题（{summary['skipped']} 题因缺题目/选项/答案被跳过） |",
        f"| 模型 | `{summary['provider']}` / `{summary['model']}` |",
        f"| LLM_MODE | `{summary['llm_mode']}` |",
        "",
        "## 2. 结果",
        "",
        "| 指标 | 值 |",
        "|---|---|",
        f"| 准确率 | **{summary['accuracy'] * 100:.1f}%**（{summary['correct']}/{summary['total']}） |",
        f"| 答案解析失败（未作答） | {summary['parse_failed']} |",
        f"| 调用失败 | {summary['errors']} |",
        f"| 知识库命中率 | {summary.get('kb_hit_rate', 0) * 100:.1f}% |",
        f"| 排盘失败 | {summary.get('chart_failed', 0)} |",
        f"| 延迟 P50 / P95 | {summary['p50_ms']} ms / {summary['p95_ms']} ms |",
        "",
        "跨轮次「每道题错几次」看 `docs/题库复盘.md`（由 `scripts.bench_stats` 生成）。",
        "",
    ]
    if summary["llm_mode"] == "mock":
        lines.append(
            "> 当前为 `LLM_MODE=mock`：mock provider 不答选择题，全部计错。"
            "这一轮只能证明脚本链路可用，不能用来评价模型。",
        )
        lines.append("")

    lines.extend(["## 3. 按术数拆分", "", "| 术数 | 正确 / 总数 | 准确率 |", "|---|---|---|"])
    for domain, bucket in sorted(summary["by_domain"].items()):
        total = bucket["total"] or 1
        lines.append(
            f"| {domain} | {bucket['correct']} / {bucket['total']} | {bucket['correct'] / total * 100:.1f}% |"
        )
    lines.append("")

    categories = summary.get("by_category") or {}
    if categories:
        lines.extend(
            ["## 3.1 按题目类目", "", "| 类目 | 正确 / 总数 | 准确率 |", "|---|---|---|"]
        )
        for category, bucket in sorted(categories.items(), key=lambda item: item[1]["total"], reverse=True):
            total = bucket["total"] or 1
            lines.append(
                f"| {category} | {bucket['correct']} / {bucket['total']} | {bucket['correct'] / total * 100:.1f}% |"
            )
        lines.append("")

    failed = [item for item in records if not item["correct"]][:20]
    lines.extend(["## 4. 失败样例（前 20 条，供蒸馏用）", ""])
    if not failed:
        lines.append("本轮没有失败样例。")
    else:
        lines.append("| id | 术数 | 期望 | 实际 | 原因 |")
        lines.append("|---|---|---|---|---|")
        for item in failed:
            question = item["question"].replace("|", "｜")[:40]
            lines.append(
                f"| `{item['id']}` | {item['domain']} | {item['expected']} | "
                f"{item['got'] or '—'} | {(item['error'] or '选错')[:40]} |"
            )
            lines.append(f"|  |  | 题目 | {question} |  |")
    lines.extend(
        [
            "",
            "## 5. 下一步",
            "",
            "1. 把 `data/bench/attempts.jsonl` 喂给 `python -m scripts.distill_skills`，产出 `_draft/` 技能卡；",
            "2. 人工复核草稿，确认没有编造规则后改 `status: approved` 并移出 `_draft/`；",
            "3. 重跑本脚本，比较准确率与 `parse_failed` 的变化。",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="命理题库评测")
    parser.add_argument("--dataset", default="generic", help="generic / mingli_bench / fate_bench / baziqa")
    parser.add_argument("--file", required=True, help="cases.jsonl 路径")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--output", default=str(DEFAULT_REPORT))
    parser.add_argument("--attempts", default=str(DEFAULT_ATTEMPTS))
    parser.add_argument("--summary-json", default="", help="把本轮汇总写成 JSON，供蒸馏循环读取")
    parser.add_argument("--tag", default="", help="本轮标记，例如 round-2-with-skills")
    parser.add_argument("--max-tokens", type=int, default=1200, help="单题输出 token 上限")
    parser.add_argument(
        "--model",
        default="",
        help="覆盖 LLM_MODEL（评测与产品配置解耦；建议用输出短的模型跑批量）",
    )
    parser.add_argument(
        "--no-skills",
        action="store_true",
        help="不注入 SKILL.md（消融基线，用来衡量技能卡是否真的有用）",
    )
    parser.add_argument(
        "--no-knowledge",
        action="store_true",
        help="不检索知识库（默认先检索已审核片段再作答）",
    )
    parser.add_argument(
        "--no-append",
        action="store_true",
        help="不追加历史（默认追加，否则「同一道题错几次」就统计不出来）",
    )
    args = parser.parse_args(argv)

    path = Path(args.file)
    if not path.is_absolute():
        path = (BACKEND_DIR / path).resolve() if not path.exists() else path.resolve()

    loaded = (
        mingli_dataset.load(path, limit=args.limit)
        if args.dataset == "mingli_bench"
        else load_cases(path, fmt=args.dataset, limit=args.limit)
    )
    if not loaded.cases:
        print(f"没有可评测的题目：{path}")
        for reason in loaded.reasons:
            print(" -", reason)
        return 2

    run_id = uuid.uuid4().hex[:12]
    session = None
    if not args.no_knowledge:
        try:
            session = SessionLocal()
        except Exception as exc:  # 数据库不可用时退化为无知识作答
            print(f"知识库不可用，本轮降级为无知识作答：{exc.__class__.__name__}")
    try:
        records, summary = run_cases(
            loaded.cases,
            run_id=run_id,
            run_tag=args.tag or args.dataset,
            session=session,
            max_output_tokens=args.max_tokens,
            model=args.model or None,
            use_skills=not args.no_skills,
        )
    finally:
        if session is not None:
            session.close()
    summary["run_id"] = run_id
    summary["skipped"] = loaded.skipped

    attempts_path = Path(args.attempts)
    if args.no_append:
        write_jsonl(attempts_path, records)
    else:
        append_jsonl(attempts_path, records)

    # 题库本身的缺口（缺字段/缺答案被跳过）单独落一份，复盘报告会读它
    sidecar = path.parent / "last_load.json"
    sidecar.write_text(
        json.dumps(
            {
                "dataset": args.dataset,
                "file": str(path),
                "used": len(loaded.cases),
                "skipped": loaded.skipped,
                "reasons": loaded.reasons,
                "at": datetime.now().isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    report = render_report(
        dataset=args.dataset, file=path, loaded=loaded, summary=summary, records=records
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")

    if args.summary_json:
        payload = dict(summary)
        payload["dataset"] = args.dataset
        payload["file"] = str(path)
        payload["tag"] = args.tag or args.dataset
        payload["skills_enabled"] = not args.no_skills
        target = Path(args.summary_json)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"题数 {summary['total']}｜准确率 {summary['accuracy'] * 100:.1f}%｜"
        f"知识库命中 {summary.get('kb_hit_rate', 0) * 100:.0f}%｜排盘失败 {summary.get('chart_failed', 0)}｜"
        f"未作答 {summary['parse_failed']}｜跳过 {loaded.skipped}｜P50 {summary['p50_ms']}ms"
    )
    print(f"报告：{output}")
    print(f"累计错例集：{attempts_path}（追加模式）")
    print("下一步：python -m scripts.bench_stats   # 看每道题错了几次")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
